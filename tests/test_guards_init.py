"""Tests for guards/__init__.py — fix dispatch, post-processing, orchestration helpers."""

import sys
sys.path.insert(0, ".")

from pathlib import Path
from guards.__init__ import (
    _fn_name,
    _int_after,
    _generate_fix,
    enrich_with_fixes,
    check_missing_tests,
    _FIX_BY_GUARD,
)


# ── _fn_name ──

def test_fn_name_extracts_backticked():
    assert _fn_name({"message": "Function `process_data` is too long"}) == "process_data"


def test_fn_name_first_backtick():
    assert _fn_name({"message": "`foo` and `bar` are bad"}) == "foo"


def test_fn_name_no_backtick():
    assert _fn_name({"message": "no backticks here"}) == "item"


def test_fn_name_empty():
    assert _fn_name({}) == "item"


# ── _int_after ──

def test_int_after_extracts_number():
    assert _int_after({"message": "Nesting depth 8 exceeds max 4"}, "Nesting depth") == 8


def test_int_after_with_extra_text():
    assert _int_after({"message": "Magic number 86400 found at line 42"}, "Magic number") == 86400


def test_int_after_not_found():
    assert _int_after({"message": "no numbers after this"}, "missing") == 0


def test_int_after_empty():
    assert _int_after({}, "anything") == 0


# ── _generate_fix / _FIX_BY_GUARD ──

def test_generate_fix_unknown_guard():
    assert _generate_fix("nonexistent_guard", {}) is None


def test_generate_fix_known_guard_returns_string():
    result = _generate_fix("swallowed_errors", {
        "message": "Err(_) => {} — silently swallowed",
        "file": "src/lib.rs",
    })
    assert isinstance(result, str)
    assert len(result) > 5


def test_fix_by_guard_has_expected_keys():
    expected = {
        "function_length", "missing_tests", "deep_nesting",
        "parameter_count", "swallowed_errors", "no_stubs",
        "hardcoded_values", "missing_docs", "magic_numbers",
        "duplicated_code",
    }
    present = set(_FIX_BY_GUARD.keys())
    assert expected.issubset(present), f"Missing: {expected - present}"


def test_generate_fix_deep_nesting():
    result = _generate_fix("deep_nesting", {
        "message": "Nesting depth 6 exceeds max 4 — refactor with early returns",
        "file": "src/lib.rs",
        "line": 42,
    })
    assert isinstance(result, str)
    assert len(result) > 5


def test_generate_fix_parameter_count():
    result = _generate_fix("parameter_count", {
        "message": "Function `process` has 8 parameters (max 5) — consider grouping",
        "file": "src/lib.rs",
    })
    assert isinstance(result, str)
    assert "process" in result.lower() or "struct" in result.lower()


def test_generate_fix_missing_docs():
    result = _generate_fix("missing_docs", {
        "message": "Public function `load_config` has no doc comment",
    })
    assert isinstance(result, str)
    assert "load_config" in result or "doc" in result.lower()


def test_generate_fix_magic_numbers():
    result = _generate_fix("magic_numbers", {
        "message": "Magic number 86400 — extract to a named constant",
    })
    assert isinstance(result, str)
    assert len(result) > 5


def test_generate_fix_function_length():
    result = _generate_fix("function_length", {
        "message": "Function `big_fn` exceeds 50 lines (120)",
    })
    assert isinstance(result, str)
    assert "Split" in result or "Extract" in result


def test_generate_fix_missing_tests():
    result = _generate_fix("missing_tests", {
        "message": "Test coverage low",
        "untested_files": ["src/a.rs", "src/b.rs", "src/c.rs"],
    })
    assert result is not None and len(result) > 5


def test_generate_fix_missing_tests_no_files():
    result = _generate_fix("missing_tests", {})
    assert result is None


def test_generate_fix_hardcoded_values():
    result = _generate_fix("hardcoded_values", {
        "message": 'Hardcoded config value `https://prod.api` — Hardcoded URL',
        "file": "src/lib.rs",
    })
    assert isinstance(result, str)
    assert len(result) > 5


def test_generate_fix_no_stubs():
    result = _generate_fix("no_stubs", {
        "message": "todo!() — stub `todo!()` in production code",
    })
    assert isinstance(result, str)
    assert len(result) > 5


def test_generate_fix_duplicated_code():
    result = _generate_fix("duplicated_code", {
        "message": "Duplicated code block (repeated 3x, 5 lines each)",
    })
    assert isinstance(result, str)
    assert len(result) > 5


# ── enrich_with_fixes ──

def test_enrich_with_fixes_adds_fix(tmp_path):
    violations = [{
        "file": "src/lib.rs",
        "line": 42,
        "guard": "swallowed_errors",
        "message": "Err(_) => {} — silently swallowed",
    }]
    enrich_with_fixes(str(tmp_path), violations)
    assert "fix" in violations[0]
    assert isinstance(violations[0]["fix"], str)


def test_enrich_with_fixes_skips_existing_fix(tmp_path):
    violations = [{
        "file": "src/lib.rs",
        "line": 42,
        "guard": "swallowed_errors",
        "message": "Err(_) => {} — silently swallowed",
        "fix": "already has fix",
    }]
    enrich_with_fixes(str(tmp_path), violations)
    assert violations[0]["fix"] == "already has fix"


def test_enrich_with_fixes_filters_self_violations(tmp_path):
    """Guard-definition files should not trigger their own checks."""
    violations = [{
        "file": "guards/generic.py",
        "line": 100,
        "guard": "swallowed_errors",
        "message": "except Exception: pass",
    }]
    original_count = len(violations)
    enrich_with_fixes(str(tmp_path), violations)
    # Should be removed (self-referential false positive)
    assert len(violations) < original_count


def test_enrich_with_fixes_filters_test_violations(tmp_path):
    """Test file false positives for certain guards should be removed."""
    violations = [{
        "file": "tests/test_stuff.py",
        "line": 5,
        "guard": "swallowed_errors",
        "message": "except: pass  # intentional in test",
    }]
    enrich_with_fixes(str(tmp_path), violations)
    assert len(violations) == 0


# ── check_missing_tests ──

def test_missing_tests_disabled(tmp_path):
    violations = []
    config = {"guards": {"missing_tests": {"enabled": False}}}
    check_missing_tests(str(tmp_path), config, violations)
    assert violations == []


def test_missing_tests_no_source_files(tmp_path):
    violations = []
    config = {"guards": {"missing_tests": {"enabled": True, "min_test_ratio": 0.3}}}
    check_missing_tests(str(tmp_path), config, violations)
    assert violations == []


def test_missing_tests_with_untested_files(tmp_path):
    """Source files without matching test files should be flagged."""
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "src" / "lib.rs").write_text("pub fn lib() {}\n")
    (tmp_path / "src" / "utils.rs").write_text("pub fn util() {}\n")
    (tmp_path / "src" / "api.rs").write_text("pub fn api() {}\n")
    (tmp_path / "src" / "db.rs").write_text("pub fn db() {}\n")

    violations = []
    config = {"guards": {"missing_tests": {"enabled": True, "min_test_ratio": 0.3}}}
    check_missing_tests(str(tmp_path), config, violations)

    # 4 source files, 0 test files → ratio 0% < 30%
    assert len(violations) >= 1
    assert violations[0]["guard"] == "missing_tests"


def test_missing_tests_with_matching_tests(tmp_path):
    """Source files with matching test files should not be flagged."""
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "src" / "lib.rs").write_text("pub fn lib() {}\n")
    (tmp_path / "src" / "utils.rs").write_text("pub fn util() {}\n")

    # Create matching test file for lib.rs
    (tmp_path / "src" / "lib_test.rs").write_text(
        "#[test]\nfn test_lib() {}\n"
    )

    violations = []
    config = {"guards": {"missing_tests": {"enabled": True, "min_test_ratio": 0.3}}}
    check_missing_tests(str(tmp_path), config, violations)

    # 2 source files, 1 has test → 50% > 30% → no violation
    assert violations == []
