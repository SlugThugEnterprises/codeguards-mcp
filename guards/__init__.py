"""Plugin system — loads and orchestrates code guard checks."""

import importlib
import inspect
import os
import pkgutil
from pathlib import Path
from typing import Any, Callable

from . import generic
from . import structural
from detectors import detect_languages, walk_source_files


class GuardRegistry:
    """Registry of available code guards across all plugins."""

    def __init__(self):
        self._guards: list[dict] = []

    def register_guard(
        self,
        name: str,
        check_fn: Callable,
        languages: list[str] | None = None,
        description: str = "",
        file_extensions: set[str] | None = None,
    ):
        """Register a guard check function from a plugin."""
        self._guards.append({
            "name": name,
            "check_fn": check_fn,
            "languages": languages or [],
            "description": description,
            "file_extensions": file_extensions or set(),
        })

    @property
    def guards(self) -> list[dict]:
        """All registered guards."""
        return list(self._guards)


def load_plugins() -> GuardRegistry:
    """Scan plugins/ directory and load all registered guards."""
    registry = GuardRegistry()

    plugins_dir = Path(__file__).resolve().parent.parent / "plugins"
    if plugins_dir.is_dir():
        # Load each .py file as a plugin
        for f in sorted(plugins_dir.glob("*.py")):
            if f.name == "__init__.py":
                continue
            mod_name = f"plugins.{f.stem}"
            try:
                spec = importlib.util.spec_from_file_location(mod_name, f)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    if hasattr(mod, "register"):
                        mod.register(registry)
            except Exception as e:
                import logging as _log
                _log.getLogger("codeguards.plugins").warning("failed to load plugin %s: %s", f.name, e)

    return registry


def run_checks(
    project_root: str,
    config: dict,
    registry: GuardRegistry,
    languages: list[str] | None = None,
) -> list[dict]:
    """Run all applicable guards against a project — generic, structural, plugin, project-level."""
    if languages is None:
        languages = detect_languages(project_root)

    guards_cfg = config.get("guards", {})
    violations = []

    source_files = walk_source_files(project_root)

    for sf in source_files:
        try:
            content = sf.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        # Run generic guards always
        for name, check_fn in _GENERIC_CHECKS.items():
            if name not in guards_cfg:
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
    untested = []

    for sf in walk_source_files(project_root):
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
                if test_dir.is_dir():
                    # Check for any test file with the basename or a matching pattern
                    if any(test_dir.iterdir()):
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
    """Post-process: add fix suggestions and intent cross-reference to violations."""
    from intent import load_intent, check_intent_violation

    intent = load_intent(project_root)

    for v in violations:
        guard = v.get("guard", "")

        # Filter self-referential violations
        f = v.get("file", "")
        if f.endswith((".py", ".rs")) and v.get("line", 0):
            import linecache
            line = (linecache.getline(f, v["line"]) or "")
            if 'r"' in line or "r'" in line:
                continue

        # Cross-reference against declared intent
        if intent and v.get("file"):
            intent_msg = check_intent_violation(guard, v.get("file", ""), "", intent)
            if intent_msg:
                v["message"] = f"{v['message']} {intent_msg}"

        # Add fix suggestions if not already present
        if "fix" not in v:
            fix = _generate_fix(guard, v)
            if fix:
                v["fix"] = fix


def _generate_fix(guard: str, v: dict) -> str | None:
    """Generate a fix suggestion based on guard type and violation context."""
    if guard == "function_length":
        line = v.get("line", 0)
        msg = v.get("message", "")
        return "Split into smaller functions. Extract the largest logical sub-blocks into named functions that describe what they compute."

    if guard == "deep_nesting":
        return "Refactor with early returns / guard clauses. Invert deep conditions and return early to flatten the happy path."

    if guard == "parameter_count":
        return "Group parameters into a struct, config object, or builder pattern."

    if guard == "swallowed_errors":
        return "Handle the error: log it, wrap it in your error type, or propagate it upward. Never silently discard errors."

    if guard == "no_stubs":
        return "Replace this stub with a real implementation, or add a link to the tracking issue."

    if guard == "hardcoded_values":
        return "Extract this value to a configuration constant, environment variable, or config file."

    if guard == "missing_docs":
        return "Add a doc comment explaining what this function does, its parameters, and return value."

    if guard == "magic_numbers":
        return "Extract this number to a named constant that explains what it represents."

    if guard == "duplicated_code":
        return "Extract the duplicated logic into a shared function. Identify what varies and make that the parameter."

    if guard == "missing_tests":
        untested = v.get("untested_files", [])
        if untested:
            return f"Create test files for these untested modules. Write the first failing test before implementing: {', '.join(untested[:3])}"

    return None


_GENERIC_CHECKS = generic.ALL_GENERIC_CHECKS
