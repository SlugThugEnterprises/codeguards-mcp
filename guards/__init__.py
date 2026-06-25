"""Plugin system — loads and orchestrates code guard checks."""

import importlib
import inspect
import os
import pkgutil
from pathlib import Path
from typing import Any, Callable

from . import generic
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
        """Register a guard check function."""
        self._guards.append({
            "name": name,
            "check_fn": check_fn,
            "languages": languages or [],
            "description": description,
            "file_extensions": file_extensions or set(),
        })

    @property
    def guards(self) -> list[dict]:
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
                print(f"Warning: failed to load plugin {f.name}: {e}")

    return registry


def run_checks(
    project_root: str,
    config: dict,
    registry: GuardRegistry,
    languages: list[str] | None = None,
) -> list[dict]:
    """Run all applicable guards against a project."""
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

    return violations


def check_missing_tests(project_root: str, config: dict, violations: list[dict]):
    """AI rarely writes tests — check that source modules have test files."""
    cfg = config.get("guards", {}).get("missing_tests", {})
    if not cfg.get("enabled", True):
        return

    root = Path(project_root)
    ext_to_test_paths = {
        ".rs":  ["tests/", "_test.rs"],
        ".py":  ["tests/", "_test.py", "test_"],
        ".js":  ["tests/", ".test.", "__tests__/"],
        ".ts":  ["tests/", ".test.", ".spec.", "__tests__/"],
        ".go":  ["_test.go"],
        ".rb":  ["_test.rb", "spec/"],
    }
    min_ratio = cfg.get("min_test_ratio", 0.3)  # 30% of source files should have tests

    # Count source files vs test files
    source_count = 0
    untested = []
    for sf in walk_source_files(project_root):
        sf_str = str(sf)
        for ext, markers in ext_to_test_paths.items():
            if sf.suffix != ext:
                continue
            source_count += 1
            basename = sf.stem
            parent_dir = sf.parent

            has_test = False
            for marker in markers:
                if marker.endswith("/"):
                    # Look for test dir in parent or sibling
                    test_files = list(parent_dir.glob(f"**/{marker}*{basename}*"))
                    if not test_files:
                        test_files = list(root.glob(f"{marker}*{basename}*"))
                    if test_files:
                        has_test = True
                        break
                else:
                    # Suffix match: foo.rs → foo_test.rs, test_foo.py
                    candidate = parent_dir / f"{marker.replace('_test.', '')}test_{basename}{ext}" if marker.startswith("test_") else \
                                parent_dir / f"{basename}{marker}"
                    if candidate.exists():
                        has_test = True
                        break
                    # Also check glob for __tests__/ variants
                    if any(parent_dir.glob(f"**/{marker.replace('.test.', '*')}{'*'}*{basename}*")):
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


_GENERIC_CHECKS = generic.ALL_GENERIC_CHECKS
