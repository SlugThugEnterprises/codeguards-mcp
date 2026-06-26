"""Tests for config.py — DEFAULTS payload, load_config, _deep_merge."""

import sys
sys.path.insert(0, ".")

from pathlib import Path
from config import DEFAULTS, load_config, _deep_merge


def test_defaults_has_all_guards():
    """Every guard expected by the system should be in DEFAULTS."""
    expected = {
        "file_length", "function_length", "god_file",
        "forbidden_phrases", "glob_imports", "debug_statements",
        "commented_code", "magic_numbers", "duplicated_code",
        "unsafe_patterns", "deep_nesting", "parameter_count",
        "credentials", "action_items", "hardcoded_values",
        "missing_docs", "swallowed_errors", "no_stubs",
        "missing_tests", "responsibility_clusters", "fan_out",
        "structural_health", "growth_drift",
    }
    guard_keys = set(DEFAULTS["guards"].keys())
    assert expected.issubset(guard_keys), (
        f"Missing keys: {expected - guard_keys}"
    )


def test_defaults_use_constants():
    """Ensure DEFAULTS pull threshold values from constants."""
    assert DEFAULTS["guards"]["file_length"]["max_prod"] > 0
    assert DEFAULTS["guards"]["file_length"]["max_test"] > 0
    assert DEFAULTS["guards"]["function_length"]["max"] > 0
    assert DEFAULTS["guards"]["god_file"]["max_public_items"] > 0
    assert DEFAULTS["guards"]["god_file"]["max_imports"] > 0
    assert DEFAULTS["guards"]["deep_nesting"]["max_depth"] > 0
    assert DEFAULTS["guards"]["parameter_count"]["max_params"] > 0
    assert DEFAULTS["guards"]["commented_code"]["min_lines"] > 0


def test_load_config_no_yaml_returns_defaults(tmp_path):
    """When no .codeguards.yaml exists, load_config returns DEFAULTS."""
    cfg = load_config(str(tmp_path))
    assert cfg is not None
    assert "guards" in cfg
    assert cfg["guards"]["file_length"]["enabled"] is True


def test_load_config_with_yaml_overrides(tmp_path):
    """User YAML values override DEFAULTS via deep merge."""
    yaml_path = tmp_path / ".codeguards.yaml"
    yaml_path.write_text("""
guards:
  file_length:
    max_prod: 100
  debug_statements:
    enabled: false
""")
    cfg = load_config(str(tmp_path))
    assert cfg["guards"]["file_length"]["max_prod"] == 100
    assert cfg["guards"]["debug_statements"]["enabled"] is False
    # Unchanged keys stay at defaults
    assert cfg["guards"]["file_length"]["enabled"] is True


def test_load_config_empty_yaml_returns_defaults(tmp_path):
    """Empty .codeguards.yaml still returns DEFAULTS."""
    yaml_path = tmp_path / ".codeguards.yaml"
    yaml_path.write_text("")
    cfg = load_config(str(tmp_path))
    assert cfg is not None
    assert "guards" in cfg


def test_load_config_no_project_root():
    """load_config without any project_root returns DEFAULTS."""
    cfg = load_config(None)
    assert cfg is not None
    assert "guards" in cfg


def test_deep_merge_shallow():
    """Top-level keys in override replace base values."""
    base = {"a": 1, "b": 2}
    override = {"b": 42}
    result = _deep_merge(base, override)
    assert result["a"] == 1
    assert result["b"] == 42


def test_deep_merge_nested():
    """Nested dicts are recursively merged, not replaced."""
    base = {"a": {"x": 1, "y": 2}, "b": 3}
    override = {"a": {"y": 99}}
    result = _deep_merge(base, override)
    assert result["a"]["x"] == 1   # preserved from base
    assert result["a"]["y"] == 99  # overridden
    assert result["b"] == 3       # untouched


def test_deep_merge_new_key():
    """Keys in override that don't exist in base are added."""
    base = {"a": 1}
    override = {"b": 2}
    result = _deep_merge(base, override)
    assert result["a"] == 1
    assert result["b"] == 2


def test_deep_merge_non_dict_override():
    """When both sides have a key but values aren't both dicts, override wins."""
    base = {"a": {"x": 1}, "b": [1, 2]}
    override = {"a": "replaced", "b": [3]}
    result = _deep_merge(base, override)
    assert result["a"] == "replaced"
    assert result["b"] == [3]


def test_deep_merge_triple_nested():
    """3+ level nesting: inner dicts are recursively merged."""
    base = {"a": {"b": {"c": 1, "d": 2}}}
    override = {"a": {"b": {"d": 99, "e": 3}}}
    result = _deep_merge(base, override)
    assert result["a"]["b"]["c"] == 1   # preserved
    assert result["a"]["b"]["d"] == 99  # overridden
    assert result["a"]["b"]["e"] == 3   # added
