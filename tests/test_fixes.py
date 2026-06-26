"""Tests for fixes.py — actionable fix suggestions for every guard."""

import sys
sys.path.insert(0, ".")

from pathlib import Path
from fixes import (
    fix_file_length,
    fix_function_length,
    fix_god_file,
    fix_deep_nesting,
    fix_parameter_count,
    fix_swallowed_error,
    fix_no_stubs,
    fix_hardcoded_value,
    fix_missing_docs,
    fix_magic_number,
    fix_duplicated_code,
)


# ── fix_file_length ──

def test_fix_file_length_finds_boundaries():
    content = "\n".join(
        [f"fn func_{i}() {{ /* body */ }}" if i % 10 == 0 else "    let x = 1;"
         for i in range(300)]
    )
    result = fix_file_length(Path("lib.rs"), content, 300, 200)
    # Should produce something non-empty
    assert len(result) > 10
    assert "Split" in result or "split" in result.lower()


def test_fix_file_length_no_boundaries():
    # All one-liners — no blank lines or section breaks
    content = "\n".join(f"line {i}" for i in range(300))
    result = fix_file_length(Path("lib.rs"), content, 300, 200)
    assert len(result) > 5


# ── fix_function_length ──

def test_fix_function_length_normal():
    lines = ["fn long_fn() {"] + [f"    let x = {i};" for i in range(150)] + ["}"]
    content = "\n".join(lines)
    # start_line is 1-indexed
    result = fix_function_length(Path("lib.rs"), content, 1, len(lines) - 1, 50)
    assert "Extract" in result or "separate" in result


def test_fix_function_length_out_of_bounds():
    content = "fn short() {\n    x\n}\n"
    result = fix_function_length(Path("lib.rs"), content, 999, 5, 50)
    # Should return a sensible fallback message
    assert len(result) > 5


# ── fix_god_file ──

def test_fix_god_file_with_pub_items():
    content = "\n".join(
        f"pub fn {name}() {{ /* */ }}" for name in
        ["db_connect", "db_query", "http_get", "http_post", "auth_login", "auth_logout"]
    )
    result = fix_god_file(Path("lib.rs"), content, 6, 12)
    assert "cluster" in result.lower() or "db" in result.lower()


def test_fix_god_file_no_pub_items():
    content = "\n".join([f"fn helper_{i}() {{}}" for i in range(5)])
    result = fix_god_file(Path("lib.rs"), content, 5, 10)
    assert len(result) > 5


# ── fix_deep_nesting ──

def test_fix_deep_nesting():
    result = fix_deep_nesting(Path("lib.rs"), "content", 42, 8, 4)
    assert "early return" in result.lower() or "guard clause" in result.lower()


# ── fix_parameter_count ──

def test_fix_parameter_count():
    result = fix_parameter_count("process_data", 12, 6)
    assert "struct" in result.lower() or "builder" in result.lower()
    assert "process_data" in result


# ── fix_swallowed_error ──

def test_fix_swallowed_error():
    result = fix_swallowed_error("Err(_) => {}")
    assert "log" in result.lower() or "propagate" in result.lower()


# ── fix_no_stubs ──

def test_fix_no_stubs_todo():
    result = fix_no_stubs("todo!()")
    assert "Implement" in result or "deferred" in result.lower()


def test_fix_no_stubs_not_implemented():
    result = fix_no_stubs("// not implemented yet")
    assert "Implement" in result or "deferred" in result.lower()


def test_fix_no_stubs_other():
    result = fix_no_stubs("unimplemented!()")
    assert len(result) > 5


# ── fix_hardcoded_value ──

def test_fix_hardcoded_value():
    result = fix_hardcoded_value("86400", "let timeout = 86400;")
    assert "extract" in result.lower()
    assert "86400" in result


# ── fix_missing_docs ──

def test_fix_missing_docs():
    result = fix_missing_docs("function", "process_data")
    assert "doc" in result.lower()
    assert "process_data" in result


# ── fix_magic_number ──

def test_fix_magic_number():
    result = fix_magic_number(42)
    assert "42" in result
    assert "constant" in result.lower()


# ── fix_duplicated_code ──

def test_fix_duplicated_code():
    result = fix_duplicated_code(10, 3)
    assert "extract" in result.lower() or "shared" in result.lower()
