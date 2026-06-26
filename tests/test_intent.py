"""Tests for intent.py — save/load intent, violation checks, summaries."""

import json
import sys
sys.path.insert(0, ".")

from pathlib import Path
from intent import (
    get_intent_path,
    load_intent,
    save_intent,
    has_intent,
    check_intent_violation,
    get_intent_summary,
)


SAMPLE_INTENT = {
    "global": {
        "error_handling": "Propagate errors via Result<>. No .unwrap() in library code.",
        "logging": "Use tracing crate with structured fields.",
        "testing": "All public functions must have unit tests.",
    },
    "modules": [
        {
            "name": "core",
            "path": "src/core",
            "responsibility": "Domain models and business logic",
            "error_strategy": "Return Result with custom error types",
            "logging": "tracing::instrument on all public fns",
            "testing": "Unit tests in tests/core/",
        },
        {
            "name": "api",
            "path": "src/api",
            "responsibility": "HTTP handlers and middleware",
            "error_strategy": "Convert errors to HTTP status codes",
            "logging": "Request/response logging with correlation IDs",
            "testing": "Integration tests in tests/api/",
        },
    ],
}


# ── path helpers ──

def test_get_intent_path():
    p = get_intent_path("/my/project")
    assert p == Path("/my/project/.codeguards/intent.json")


# ── load_intent ──

def test_load_intent_no_file(tmp_path):
    assert load_intent(str(tmp_path)) is None


def test_load_intent_valid(tmp_path):
    intent_path = tmp_path / ".codeguards"
    intent_path.mkdir()
    (intent_path / "intent.json").write_text(json.dumps(SAMPLE_INTENT))
    loaded = load_intent(str(tmp_path))
    assert loaded is not None
    assert loaded["global"]["error_handling"] == SAMPLE_INTENT["global"]["error_handling"]


def test_load_intent_invalid_json(tmp_path):
    intent_path = tmp_path / ".codeguards"
    intent_path.mkdir()
    (intent_path / "intent.json").write_text("{invalid json")
    assert load_intent(str(tmp_path)) is None


# ── save_intent ──

def test_save_intent_creates_dir(tmp_path):
    path = save_intent(str(tmp_path), SAMPLE_INTENT)
    assert path.exists()
    saved = json.loads(path.read_text())
    assert saved["global"]["error_handling"] == SAMPLE_INTENT["global"]["error_handling"]
    assert saved["_schema_version"] == 1


def test_save_and_load_roundtrip(tmp_path):
    save_intent(str(tmp_path), SAMPLE_INTENT)
    loaded = load_intent(str(tmp_path))
    assert loaded is not None
    assert loaded["global"]["error_handling"] == SAMPLE_INTENT["global"]["error_handling"]
    assert len(loaded["modules"]) == 2


# ── has_intent ──

def test_has_intent_false(tmp_path):
    assert has_intent(str(tmp_path)) is False


def test_has_intent_true(tmp_path):
    intent_dir = tmp_path / ".codeguards"
    intent_dir.mkdir()
    (intent_dir / "intent.json").write_text("{}")
    assert has_intent(str(tmp_path)) is True


# ── check_intent_violation ──

def test_check_intent_violation_known_guard():
    result = check_intent_violation(
        "debug_statements", "src/lib.rs",
        'println!("debug");',
        SAMPLE_INTENT,
    )
    assert result is not None
    assert "Intent declared" in result


def test_check_intent_violation_unknown_guard():
    result = check_intent_violation(
        "file_length", "src/lib.rs",
        "content here",
        SAMPLE_INTENT,
    )
    assert result is None


def test_check_intent_violation_missing_rule():
    """Guard maps to a rule but intent doesn't have it."""
    intent_no_rule = {"global": {}}
    result = check_intent_violation(
        "debug_statements", "src/lib.rs",
        "code",
        intent_no_rule,
    )
    assert result is None


def test_check_intent_violation_no_global():
    result = check_intent_violation(
        "missing_docs", "src/lib.rs",
        "code",
        {"global": {}},
    )
    # missing_docs -> documentation rule, but no rule declared
    assert result is None


# ── get_intent_summary ──

def test_get_intent_summary_includes_global_rules():
    summary = get_intent_summary(SAMPLE_INTENT)
    assert "Declared Architectural Intent" in summary
    assert "Global Rules" in summary
    assert "error_handling" in summary
    assert "logging" in summary


def test_get_intent_summary_includes_modules():
    summary = get_intent_summary(SAMPLE_INTENT)
    assert "Module Boundaries" in summary
    assert "core" in summary
    assert "Domain models" in summary
    assert "api" in summary


def test_get_intent_summary_no_modules():
    minimal = {"global": {"error_handling": "Use Result"}}
    summary = get_intent_summary(minimal)
    assert "Declared Architectural Intent" in summary
    assert "Global Rules" in summary
    assert "Module Boundaries" not in summary
