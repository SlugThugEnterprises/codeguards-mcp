"""Plugin system — guards (per-language checks) and extractors (capability providers).

The ``GuardRegistry`` is the single source of truth for plugin contributions.
Two kinds of contributions:

  - **Guards** — per-language checks with their own violation format, fired
    for every matching file. Example: Rust's ``no_unwrap``.
  - **Extractors** — capability providers for language-agnostic guards.
    A generic guard (``guards/generic.py``) consults
    ``get_extractor(capability, ext)`` to ask "how do I find X in <lang>?"
    and the plugin answers. Example: Python's ``function_blocks`` extractor
    tells ``check_function_length`` where Python ``def`` blocks start/end.

The registry is the process-wide singleton ``_global_registry``, populated
by ``load_plugins()``. Tests can populate it manually before calling generic
checks (no module-level work needed otherwise).
"""

import importlib.util
import logging
from pathlib import Path
from typing import Callable


_log = logging.getLogger("codeguards.plugins")


class GuardRegistry:
    """Registry of plugin contributions.

    Plugins interact via ``register_guard`` (full per-language check)
    and ``register_extractor`` (capability provider for a generic check).
    Generic guards in ``guards/generic.py`` consult ``get_extractor``.
    """

    def __init__(self) -> None:
        self._guards: list[dict] = []
        # capability → { file_ext → extractor_fn }
        self._extractors: dict[str, dict[str, Callable]] = {}

    def register_guard(
        self,
        name: str,
        check_fn: Callable,
        languages: list[str] | None = None,
        description: str = "",
        file_extensions: set[str] | None = None,
    ) -> None:
        """Register a per-language guard check that fires on every file."""
        self._guards.append({
            "name": name,
            "check_fn": check_fn,
            "languages": languages or [],
            "description": description,
            "file_extensions": set(file_extensions or []),
        })

    def register_extractor(
        self,
        capability: str,
        file_extensions: set[str],
        extractor_fn: Callable,
    ) -> None:
        """Register a language-specific extractor for a named capability.

        Called by plugins to expose per-language parsing helpers. Generic
        guards look these up via ``get_extractor`` instead of branching on
        file extension themselves — that keeps the core language-agnostic.
        """
        for ext in file_extensions:
            self._extractors.setdefault(capability, {})[ext] = extractor_fn

    def get_extractor(self, capability: str, file_ext: str) -> Callable | None:
        """Look up the extractor for ``capability`` on ``file_ext``, or None."""
        return self._extractors.get(capability, {}).get(file_ext)

    @property
    def capabilities(self) -> set[str]:
        """Set of capability names any plugin has registered an extractor for."""
        return set(self._extractors.keys())

    @property
    def guards(self) -> list[dict]:
        return list(self._guards)


# Module-level singleton. Populated by ``load_plugins()`` and read by the
# generic guards in ``guards/generic.py``. Tests can replace it manually
# via ``_set_global_registry`` if they need a custom plugin set.
_global_registry: GuardRegistry = GuardRegistry()


def get_global_registry() -> GuardRegistry:
    """The active plugin registry. Read by generic checks. Populated by
    ``load_plugins()`` at server startup, or by tests that want to verify
    specific plugin behaviors."""
    return _global_registry


def _set_global_registry(registry: GuardRegistry) -> None:
    """Test/injection hook: swap in a registry without going through
    ``load_plugins()``. Not exported to plugin authors — for internal use."""
    global _global_registry
    _global_registry = registry


def load_plugins() -> GuardRegistry:
    """Discover ``plugins/*.py`` and run each module's ``register()`` against
    a fresh registry. The populated registry is also stashed in the
    module-level singleton so generic checks can look up extractors without
    needing a registry parameter.

    Returns the populated registry (back-compat with prior API).
    """
    registry = GuardRegistry()
    plugins_dir = Path(__file__).resolve().parent
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
            _log.warning("failed to load plugin %s: %s", f.name, e)
    _set_global_registry(registry)
    return registry
