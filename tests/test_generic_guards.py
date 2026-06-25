"""Tests for generic guards — each guard against known-good and known-bad inputs."""

import sys
sys.path.insert(0, ".")

from pathlib import Path
from guards.generic import (
    check_file_length,
    check_function_length,
    check_forbidden_phrases,
    check_credentials,
    check_glob_imports,
    check_debug_statements,
    check_commented_code,
    check_magic_numbers,
    check_swallowed_errors,
    check_no_stubs,
    check_duplicated_code,
)


# ── file_length ──

def test_file_length_clean(tmp_path):
    f = tmp_path / "mod.rs"
    f.write_text("\n".join(f"line {i}" for i in range(150)))
    content = f.read_text()
    violations = check_file_length(f, content, {"enabled": True, "max_prod": 200})
    assert len(violations) == 0, f"Expected 0, got {violations}"


def test_file_length_violation(tmp_path):
    f = tmp_path / "mod.rs"
    f.write_text("\n".join(f"line {i}" for i in range(300)))
    content = f.read_text()
    violations = check_file_length(f, content, {"enabled": True, "max_prod": 200})
    assert len(violations) >= 1


def test_file_length_test_file(tmp_path):
    """Test files use max_test threshold (not max_prod)."""
    f = tmp_path / "tests" / "mod.rs"
    f.parent.mkdir()
    f.write_text("\n".join(f"line {i}" for i in range(600)))
    content = f.read_text()
    # Should not trigger at 500 if we're below
    violations = check_file_length(f, content, {"enabled": True, "max_prod": 200, "max_test": 500})
    assert len(violations) >= 1  # 600 > 500


# ── function_length ──

def test_function_length_clean_rust():
    content = """
fn small() {
    let x = 1;
}
"""
    violations = check_function_length(Path("test.rs"), content, {"enabled": True, "max": 50})
    assert len(violations) == 0, f"Expected 0, got {violations}"


def test_function_length_violation_rust():
    lines = ["fn long() {"] + [f"    let x = {i};" for i in range(100)] + ["}"]
    content = "\n".join(lines)
    violations = check_function_length(Path("test.rs"), content, {"enabled": True, "max": 50})
    assert len(violations) >= 1


def test_function_length_clean_python():
    content = """
def small():
    x = 1
    return x
"""
    violations = check_function_length(Path("test.py"), content, {"enabled": True, "max": 50})
    assert len(violations) == 0, f"Expected 0, got {violations}"


def test_function_length_violation_python():
    lines = ["def long():"] + [f"    x = {i}" for i in range(100)]
    content = "\n".join(lines)
    violations = check_function_length(Path("test.py"), content, {"enabled": True, "max": 50})
    assert len(violations) >= 1


# ── forbidden_phrases ──

def test_forbidden_phrases_clean():
    violations = check_forbidden_phrases(
        Path("test.rs"), "fn run() { process() }",
        {"enabled": True, "patterns": [{"pattern": r"\bfor now\b", "message": "remove"}]}
    )
    assert len(violations) == 0


def test_forbidden_phrases_violation():
    violations = check_forbidden_phrases(
        Path("test.rs"), "// for now we skip validation",
        {"enabled": True, "patterns": [{"pattern": r"\bfor now\b", "message": "remove"}]}
    )
    assert len(violations) >= 1


# ── credentials ──

def test_credentials_clean():
    violations = check_credentials(
        Path("test.rs"), "const API_URL: &str = \"https://api.example.com\";",
        {"enabled": True, "patterns": [{"pattern": r"ghp_[a-zA-Z0-9]{36}", "message": "GitHub token"}]}
    )
    assert len(violations) == 0


def test_credentials_violation():
    violations = check_credentials(
        Path("test.rs"), "let token = \"ghp_abcdefghijklmnopqrstuvwxyz0123456789\";",
        {"enabled": True, "patterns": [{"pattern": r"ghp_[a-zA-Z0-9]{36}", "message": "GitHub token"}]}
    )
    assert len(violations) >= 1


# ── glob_imports ──

def test_glob_imports_clean():
    violations = check_glob_imports(
        Path("test.rs"), "use crate::db::Profile;",
        {"enabled": True}
    )
    assert len(violations) == 0


def test_glob_imports_violation():
    violations = check_glob_imports(
        Path("test.rs"), "use crate::models::*;",
        {"enabled": True}
    )
    assert len(violations) >= 1


# ── debug_statements ──

def test_debug_statements_clean():
    violations = check_debug_statements(
        Path("test.rs"), "tracing::info!(\"processing\");",
        {"enabled": True}
    )
    assert len(violations) == 0


def test_debug_statements_violation():
    violations = check_debug_statements(
        Path("test.rs"), "println!(\"debug: {}\", x);",
        {"enabled": True}
    )
    assert len(violations) >= 1


# ── swallowed_errors ──

def test_swallowed_errors_clean():
    violations = check_swallowed_errors(
        Path("test.rs"), "Err(e) => return Err(e.into()),",
        {"enabled": True}
    )
    assert len(violations) == 0


def test_swallowed_errors_violation():
    violations = check_swallowed_errors(
        Path("test.rs"), "Err(_) => {},  // silently swallowed",
        {"enabled": True}
    )
    assert len(violations) >= 1


# ── no_stubs ──

def test_no_stubs_clean():
    violations = check_no_stubs(
        Path("test.rs"), "fn process() -> Result<()> { Ok(()) }",
        {"enabled": True}
    )
    assert len(violations) == 0


def test_no_stubs_violation():
    violations = check_no_stubs(
        Path("test.rs"), "fn process() -> Result<()> { todo!() }",
        {"enabled": True}
    )
    assert len(violations) >= 1


# ── magic_numbers ──

def test_magic_numbers_clean():
    violations = check_magic_numbers(
        Path("test.rs"), "const MAX_RETRIES: u32 = 3;",
        {"enabled": True}
    )
    assert len(violations) == 0


def test_magic_numbers_violation():
    violations = check_magic_numbers(
        Path("test.rs"), "if x > 86400 {  // 24 hours in seconds",
        {"enabled": True}
    )
    assert len(violations) >= 1


# ── commented_code ──

def test_commented_code_clean():
    violations = check_commented_code(
        Path("test.rs"), "// This function processes data\nfn process() {}\n",
        {"enabled": True, "min_lines": 5}
    )
    assert len(violations) == 0


def test_commented_code_violation():
    violations = check_commented_code(
        Path("test.rs"), "// fn old_approach() {\n//     let x = 1;\n//     let y = 2;\n//     let z = 3;\n//     let w = 4;\n//     process(w);\n// }\n",
        {"enabled": True, "min_lines": 5}
    )
    assert len(violations) >= 1
