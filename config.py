"""CodeGuards config — loads .codeguards.yaml with smart defaults."""

import os
from pathlib import Path

import constants


DEFAULTS = {
    "ignored_dirs": [],
    "ignored_patterns": [],
    "guards": {
        "file_length": {"enabled": True, "max_prod": constants.MAX_PROD_LINES, "max_test": constants.MAX_TEST_LINES},
        "function_length": {"enabled": True, "max": constants.MAX_FN_LINES},
        "god_file": {"enabled": True, "max_public_items": constants.MAX_PUBLIC_ITEMS, "max_imports": constants.MAX_IMPORTS},
        "forbidden_phrases": {"enabled": True, "patterns": [
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
        ]},
        "glob_imports": {"enabled": True},
        "debug_statements": {"enabled": True},
        "commented_code": {"enabled": True, "min_lines": constants.MIN_COMMENTED_LINES},
        "magic_numbers": {"enabled": True},
        "duplicated_code": {"enabled": True, "n_gram_size": constants.N_GRAM_SIZE, "min_repeats": constants.MIN_REPEATS, "min_line_len": constants.MIN_LINE_LEN},
        "unsafe_patterns": {"enabled": True},
        "deep_nesting": {"enabled": True, "max_depth": constants.MAX_NEST_DEPTH},
        "parameter_count": {"enabled": True, "max_params": constants.MAX_PARAMS},
        "credentials": {"enabled": True, "patterns": [
            {"pattern": r"AKIA[0-9A-Z]{16}", "message": "AWS access key detected"},
            {"pattern": r"sk-[a-zA-Z0-9]{20,}", "message": "OpenAI API key detected"},
            {"pattern": r"ghp_[a-zA-Z0-9]{36}", "message": "GitHub token detected"},
        ]},
        "action_items": {"enabled": True, "require_issue": True},
        "hardcoded_values": {"enabled": True},
        "missing_docs": {"enabled": True},
        "swallowed_errors": {"enabled": True},
        "no_stubs": {"enabled": True},
        "missing_tests": {"enabled": True, "min_test_ratio": constants.MIN_TEST_RATIO},
        "responsibility_clusters": {"enabled": True, "max_domains": constants.MAX_DOMAINS},
        "fan_out": {"enabled": True, "max_dependencies": constants.MAX_DEPS},
        "structural_health": {"enabled": True, "min_score": constants.MIN_STRUCTURAL_SCORE},
        "growth_drift": {"enabled": True},
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
