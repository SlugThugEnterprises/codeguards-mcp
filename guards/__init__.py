"""Orchestration — wires generic checks, structural checks, plugin guards,
and project-level checks together.

The plugin registry itself lives in the ``plugins`` package — that is the
single source of truth for GuardRegistry and load_plugins. This module
re-exports both for backward compatibility with code that imports from
``guards``. Generic guards in ``guards/generic.py`` consult
``plugins.get_global_registry()`` directly to discover per-language
extractors (e.g., Python's ``function_blocks`` strategy).
"""

import re
from pathlib import Path
from typing import Callable

from . import generic
from . import structural
from detectors import detect_languages, walk_source_files
from fixes import (
    fix_deep_nesting,
    fix_duplicated_code,
    fix_hardcoded_value,
    fix_magic_number,
    fix_missing_docs,
    fix_no_stubs,
    fix_parameter_count,
    fix_swallowed_error,
)

# Re-export: callers that do ``from guards import GuardRegistry, load_plugins``
# keep working unchanged. Authoritative definitions live in ``plugins``.
from plugins import GuardRegistry, load_plugins  # noqa: F401, F405


# Generic checks live in guards.generic — exposed here so run_checks can
# iterate them. The order is irrelevant; each runs against every source file.
_GENERIC_CHECKS: dict[str, Callable] = generic.ALL_GENERIC_CHECKS


def run_checks(
    project_root: str,
    config: dict,
    registry: GuardRegistry,
    languages: list[str] | None = None,
) -> list[dict]:
    """Run all applicable guards against a project — generic, structural, plugin, project-level.

    Note: ``registry`` is kept as a parameter for backward compat with the MCP
    server, but generic guards consult ``plugins.get_global_registry()``
    internally for extractors. If the registry is empty (no plugins), the
    generic guards fall back to their built-in language-agnostic strategies.
    """
    if languages is None:
        languages = detect_languages(project_root)

    guards_cfg = config.get("guards", {})
    violations: list[dict] = []

    source_files = walk_source_files(project_root)

    from detectors import is_third_party

    for sf in source_files:
        try:
            content = sf.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        third_party = is_third_party(sf, project_root, config)

        # Run generic guards always
        for name, check_fn in _GENERIC_CHECKS.items():
            if name not in guards_cfg:
                continue
            # If the file is third-party code, exclude it from code quality checks
            # but do NOT exclude it from dependency risk reviews (credentials, unsafe_patterns)
            if third_party and name not in ("credentials", "unsafe_patterns"):
                continue
            try:
                violations.extend(check_fn(sf, content, guards_cfg[name]))
            except Exception as e:
                violations.append({
                    "file": str(sf),
                    "line": 0,
                    "message": f"Guard {name} error: {e}",
                    "guard": "error",
                })

        # Run structural checks: responsibility clusters, fan-out, layer enforcement
        if not third_party:
            for sname, sfn in structural.STRUCTURAL_CHECKS.items():
                scfg = guards_cfg.get(sname, {})
                if not scfg.get("enabled", True):
                    continue
                try:
                    violations.extend(sfn(sf, content, scfg))
                except Exception as e:
                    violations.append({
                        "file": str(sf), "line": 0,
                        "message": f"Structural guard {sname} error: {e}",
                        "guard": "error",
                    })

        # Run plugin guards that match this file's language
        if not third_party:
            for guard in registry.guards:
                guard_langs = guard.get("languages", [])
                guard_exts = guard.get("file_extensions", set())
                if guard_exts and sf.suffix not in guard_exts:
                    continue
                if guard_langs and not any(l in languages for l in guard_langs):
                    continue

                guard_name = guard["name"]
                try:
                    violations.extend(guard["check_fn"](sf, content, guards_cfg.get(guard_name, {})))
                except Exception as e:
                    violations.append({
                        "file": str(sf),
                        "line": 0,
                        "message": f"Guard {guard_name} error: {e}",
                        "guard": "error",
                    })

    # Project-level checks
    check_missing_tests(project_root, config, violations)
    violations.extend(structural.check_growth_drift(project_root))

    # Enrich violations with fix suggestions from project intent
    enrich_with_fixes(project_root, violations)

    return violations


def check_missing_tests(project_root: str, config: dict, violations: list[dict]):
    """AI rarely writes tests — check that source modules have test files."""
    cfg = config.get("guards", {}).get("missing_tests", {})
    if not cfg.get("enabled", True):
        return

    root = Path(project_root)
    ext_to_test_exts = {
        ".rs":  ["_test.rs"],
        ".py":  ["_test.py", "test_"],
        ".go":  ["_test.go"],
        ".rb":  ["_test.rb"],
    }
    ext_to_test_dir_patterns = {
        ".rs":  ["tests/"],
        ".py":  ["tests/"],
        ".js":  ["tests/", "__tests__/"],
        ".ts":  ["tests/", "__tests__/"],
        ".go":  ["tests/"],
        ".rb":  ["spec/"],
    }
    min_ratio = cfg.get("min_test_ratio", 0.3)
    source_count = 0
    untested: list = []

    from detectors import is_third_party

    for sf in walk_source_files(project_root):
        if is_third_party(sf, project_root, config):
            continue
        ext = sf.suffix
        if ext not in ext_to_test_exts:
            continue
        source_count += 1
        basename = sf.stem
        parent_dir = sf.parent
        has_test = False

        # Check test file extensions: foo_rs → foo_test.rs, test_foo.py
        for marker in ext_to_test_exts.get(ext, []):
            if marker.startswith("test_"):
                candidate = parent_dir / f"{marker}{basename}{ext}"
            else:
                candidate = parent_dir / f"{basename}{marker}"
            if candidate.exists():
                has_test = True
                break

        # Check test dir patterns
        if not has_test:
            for dir_pattern in ext_to_test_dir_patterns.get(ext, []):
                test_dir = parent_dir / dir_pattern
                if test_dir.is_dir() and any(test_dir.iterdir()):
                    has_test = True
                    break

        if not has_test:
            untested.append(sf)

    if source_count > 3 and untested:
        ratio = (source_count - len(untested)) / source_count
        if ratio < min_ratio:
            violations.append({
                "file": "",
                "line": 0,
                "message": f"Test coverage: {len(untested)}/{source_count} source files have no matching test ({ratio:.0%}, target {min_ratio:.0%})",
                "guard": "missing_tests",
                "principle": "Testing",
                "untested_files": [str(u.relative_to(root)) for u in untested[:20]],
            })


def enrich_with_fixes(project_root: str, violations: list[dict]):
    """Post-process: filter false positives, add fix suggestions, cross-reference intent."""
    from intent import load_intent, check_intent_violation
    intent = load_intent(project_root)

    for v in list(violations):
        guard = v.get("guard", "")
        f = v.get("file", "")

        # Guard definition files contain regex patterns that trigger their own checks
        if any(x in f for x in ("generic.py", "structural.py")) and guard in (
            "no_stubs", "swallowed_errors", "unsafe_patterns"
        ):
            violations.remove(v)
            continue

        # Test files contain intentional patterns that would be false positives
        fp = Path(f)
        if any(p == "tests" for p in fp.parts) or fp.name.startswith("test_"):
            if guard in ("no_stubs", "swallowed_errors", "unsafe_patterns",
                          "credentials", "hardcoded_values", "responsibility_clusters",
                          "glob_imports", "action_items", "duplicated_code",
                          "god_file", "structural_health"):
                violations.remove(v)
                continue

        # Cross-reference against declared intent
        if intent and v.get("file"):
            intent_msg = check_intent_violation(guard, v.get("file", ""), "", intent)
            if intent_msg:
                v["message"] = f"{v['message']} {intent_msg}"

        # Add fix suggestions if not already present — single source of text:
        # the fix text is owned by ``fixes.py``. The dispatch table below
        # adapts per-guard the minimal violation-context → fix-function args.
        if "fix" not in v:
            fix = _generate_fix(guard, v)
            if fix:
                v["fix"] = fix


# ──────────────────────────────────────────────
# Fix-suggestion dispatch — single source of text: fixes.py.
# Each entry extracts the args the corresponding fix function needs from
# the violation dict (best-effort regex over v.message); falls back to
# generic text if the data isn't present.
# ──────────────────────────────────────────────

def _fn_name(v: dict) -> str:
    """Pull the first backticked identifier from v.message."""
    m = re.search(r"`([a-zA-Z_]\w*)`", v.get("message", ""))
    return m.group(1) if m else "item"


def _int_after(v: dict, label: str) -> int:
    """First integer appearing after ``label`` in v.message."""
    m = re.search(rf"{re.escape(label)}[^\d]*(\d+)", v.get("message", ""))
    return int(m.group(1)) if m else 0


def _generate_fix(guard: str, v: dict) -> str | None:
    """Resolve a fix suggestion for ``guard`` from the dispatch table.

    Returns ``None`` when the guard has no registered helper. Exceptions
    from individual helpers are swallowed so a malformed violation message
    can't poison the rest of the report.
    """
    fn = _FIX_BY_GUARD.get(guard)
    if fn is None:
        return None
    try:
        return fn(v)
    except Exception:
        return None


_FIX_BY_GUARD: dict[str, Callable[[dict], str | None]] = {
    # No matching helpers in fixes.py — keep the existing generic text.
    "function_length": lambda v: (
        "Split into smaller functions. Extract the largest logical sub-blocks "
        "into named functions that describe what they compute."
    ),
    "missing_tests": lambda v: (
        f"Create test files for these untested modules. Write the first "
        f"failing test before implementing: "
        f"{', '.join((v.get('untested_files') or [])[:3])}"
        if v.get("untested_files") else None
    ),
    # Each of these has a corresponding ``fixes.fix_*`` helper — dispatch
    # to it so the wording lives in one place.
    "deep_nesting": lambda v: fix_deep_nesting(
        Path(v.get("file", "")), "",
        v.get("line", 0),
        _int_after(v, "Nesting depth"),
        _int_after(v, "exceeds max"),
    ),
    "parameter_count": lambda v: fix_parameter_count(
        _fn_name(v),
        _int_after(v, "has"),
        _int_after(v, "max"),
    ),
    "swallowed_errors": lambda v: fix_swallowed_error(
        v.get("message", "")[:200]
    ),
    "no_stubs": lambda v: fix_no_stubs(v.get("message", "")[:200]),
    "hardcoded_values": lambda v: fix_hardcoded_value(
        v.get("message", "")[:200],
        v.get("file", ""),
    ),
    "missing_docs": lambda v: fix_missing_docs("function", _fn_name(v)),
    "magic_numbers": lambda v: fix_magic_number(_int_after(v, "Magic number")),
    "duplicated_code": lambda v: fix_duplicated_code(
        _int_after(v, "lines"), _int_after(v, "x"),
    ),
}
