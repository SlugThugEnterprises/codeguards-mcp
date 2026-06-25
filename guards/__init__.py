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

    return violations


_GENERIC_CHECKS = generic.ALL_GENERIC_CHECKS
