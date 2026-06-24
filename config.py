"""CodeGuards config — loads .codeguards.yaml with smart defaults."""

import os
from pathlib import Path
from typing import Any

DEFAULTS = {
    "guards": {
        "file_length": {
            "enabled": True,
            "max_prod": 200,
            "max_test": 500,
        },
        "function_length": {
            "enabled": True,
            "max": 50,
        },
        "forbidden_phrases": {
            "enabled": True,
            "patterns": [
                {"pattern": r"\bfor now\b", "message": "use a definitive statement or remove"},
                {"pattern": r"\btemporary\b", "message": "use a definitive statement or remove"},
                {"pattern": r"\bmaybe\b", "message": "use a definitive statement or remove"},
                {"pattern": r"\bsoon\b", "message": "use a specific timeline or remove"},
                {"pattern": r"\beventually\b", "message": "use a specific plan or remove"},
                {"pattern": r"\bshould\b", "message": "use `must` or remove"},
                {"pattern": r"\bprefer\b", "message": "use a definitive statement or remove"},
                {"pattern": r"\bideally\b", "message": "use a definitive statement or remove"},
                {"pattern": r"\bbest effort\b", "message": "use a definitive statement or remove"},
                {"pattern": r"\bas needed\b", "message": "specify the condition or remove"},
                {"pattern": r"\bwhen necessary\b", "message": "specify the condition or remove"},
                {"pattern": r"\bif possible\b", "message": "specify the condition or remove"},
                {"pattern": r"\blow coupling\b", "message": "describe the concrete design instead"},
                {"pattern": r"\breadable\b", "message": "describe the concrete design instead"},
                {"pattern": r"\bclean\b", "message": "describe the concrete design instead"},
                {"pattern": r"\bsimple\b", "message": "describe the concrete design instead"},
            ],
        },
        "action_items": {
            "enabled": True,
            "require_issue": True,
            "allowed_pattern": r"//\s*(ACTION|TODO|FIXME|HACK)\(#\d+\):",
            "scan_pattern": r"//\s*(ACTION|TODO|FIXME|HACK)\b",
        },
        "credentials": {
            "enabled": True,
            "patterns": [
                {"pattern": r"AKIA[0-9A-Z]{16}", "message": "AWS access key detected"},
                {"pattern": r"sk-[a-zA-Z0-9]{20,}", "message": "OpenAI API key detected"},
                {"pattern": r"github_pat_[a-zA-Z0-9]{36}", "message": "GitHub PAT detected"},
                {"pattern": r"ghp_[a-zA-Z0-9]{36}", "message": "GitHub token detected"},
            ],
        },
        "glob_imports": {
            "enabled": True,
        },
    },
}


def load_config(project_root: str | None = None) -> dict:
    """Load .codeguards.yaml from project root, merging with defaults."""
    config = DEFAULTS

    if project_root:
        path = Path(project_root) / ".codeguards.yaml"
        if path.exists():
            import yaml
            with open(path) as f:
                user = yaml.safe_load(f) or {}
            config = _deep_merge(config, user)

    return config


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override into base (override wins)."""
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result
