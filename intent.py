"""Architectural intent — declared contract that guards enforce against."""

import json
from pathlib import Path

INTENT_DIR = ".codeguards"
INTENT_FILE = "intent.json"
INTENT_SCHEMA_VERSION = 1


def get_intent_path(project_root: str) -> Path:
    """Path to intent JSON file for a project."""
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
    """Check if a project has declared intent."""
    return get_intent_path(project_root).exists()


GUARD_TO_RULE = {
    "debug_statements": "logging",
    "swallowed_errors": "error_handling",
    "no_stubs": "testing",
    "missing_docs": "documentation",
    "no_unwrap": "error_handling",
    "tracing_instrument": "tracing",
}


def check_intent_violation(guard_name: str, file_path: str, content: str,
                            intent: dict) -> str | None:
    """Cross-reference a file's content against declared intent."""
    rule_name = GUARD_TO_RULE.get(guard_name)
    if not rule_name:
        return None
    declared = intent.get("global", {}).get(rule_name, "")
    if not declared:
        return None
    return f"(Intent declared: '{declared}')"


def _format_global_rules(global_rules: dict) -> list[str]:
    """Format global rules section of intent summary."""
    lines = ["### Global Rules"]
    for key, val in global_rules.items():
        lines.append(f"- **{key}**: {val}")
    return lines


def _format_module_list(modules: list[dict]) -> list[str]:
    """Format module boundaries section of intent summary."""
    lines = ["", "### Module Boundaries"]
    for m in modules:
        lines.append(f"- **{m.get('name', '?')}** (`{m.get('path', '?')}`)")
        lines.append(f"  - Responsibility: {m.get('responsibility', '?')}")
        lines.append(f"  - Error strategy: {m.get('error_strategy', '?')}")
        lines.append(f"  - Logging: {m.get('logging', '?')}")
        lines.append(f"  - Testing: {m.get('testing', '?')}")
    return lines


def get_intent_summary(intent: dict) -> str:
    """Human-readable summary of declared intent for the AI to reference."""
    global_rules = intent.get("global", {})
    modules = intent.get("modules", [])

    lines = ["## Declared Architectural Intent", ""]
    lines.extend(_format_global_rules(global_rules))

    if modules:
        lines.extend(_format_module_list(modules))

    return "\n".join(lines)


def intent_context_for_guard(guard_name: str, intent: dict) -> str:
    """Context for violations in a declared module."""
    return ""
