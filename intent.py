"""Architectural intent — declared contract that guards enforce against."""

import json
import os
from pathlib import Path
from typing import Any


INTENT_DIR = ".codeguards"
INTENT_FILE = "intent.json"
INTENT_SCHEMA_VERSION = 1


def get_intent_path(project_root: str) -> Path:
    return Path(project_root) / INTENT_DIR / INTENT_FILE


def load_intent(project_root: str) -> dict | None:
    """Load declared architectural intent, or None if not yet declared."""
    path = get_intent_path(project_root)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def save_intent(project_root: str, intent: dict) -> Path:
    """Save architectural intent, creating .codeguards/ if needed."""
    dir_path = Path(project_root) / INTENT_DIR
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / INTENT_FILE

    intent["_schema_version"] = INTENT_SCHEMA_VERSION

    with open(path, "w") as f:
        json.dump(intent, f, indent=2)

    return path


def has_intent(project_root: str) -> bool:
    return get_intent_path(project_root).exists()


def check_intent_violation(guard_name: str, file_path: str, content: str,
                            intent: dict) -> str | None:
    """Cross-reference a file's content against declared intent.
    Returns a violation message if intent was violated, or None if clean.
    """
    global_rules = intent.get("global", {})

    # Map guard to the global rule it checks
    GUARD_TO_RULE = {
        "debug_statements": "logging",
        "swallowed_errors": "error_handling",
        "no_stubs": "testing",
        "missing_docs": "documentation",
        "no_unwrap": "error_handling",
        "tracing_instrument": "tracing",
    }

    rule_name = GUARD_TO_RULE.get(guard_name)
    if not rule_name:
        return None

    declared = global_rules.get(rule_name, "")
    if not declared:
        return None

    return f"(Intent declared: '{declared}')"


def get_intent_summary(intent: dict) -> str:
    """Human-readable summary of declared intent for the AI to reference."""
    global_rules = intent.get("global", {})
    modules = intent.get("modules", [])

    lines = ["## Declared Architectural Intent", ""]
    lines.append("### Global Rules")
    for key, val in global_rules.items():
        lines.append(f"- **{key}**: {val}")

    if modules:
        lines.append("")
        lines.append("### Module Boundaries")
        for m in modules:
            lines.append(f"- **{m.get('name', '?')}** (`{m.get('path', '?')}`)")
            lines.append(f"  - Responsibility: {m.get('responsibility', '?')}")
            lines.append(f"  - Error strategy: {m.get('error_strategy', '?')}")
            lines.append(f"  - Logging: {m.get('logging', '?')}")
            lines.append(f"  - Testing: {m.get('testing', '?')}")

    return "\n".join(lines)


def intent_context_for_guard(guard_name: str, intent: dict) -> str:
    """When a guard fires on a file that belongs to a declared module,
    include the module's declared intent in the violation context."""

    module_paths = {}
    for m in intent.get("modules", []):
        module_paths[m.get("path", "")] = m

    return ""  # Will be enriched when we know the file's module
