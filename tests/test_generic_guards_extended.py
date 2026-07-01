"""Extended tests for guards/generic.py — guards not covered by test_generic_guards.py."""

import sys
sys.path.insert(0, ".")

from pathlib import Path
from guards.generic import (
    _is_test_path,
    _count_params,
    _brace_counter_function_lengths,
    check_god_file,
    check_unsafe_patterns,
    check_deep_nesting,
    check_parameter_count,
    check_action_items,
    check_hardcoded_values,
    check_missing_docs,
    check_duplicated_code,
)


# ── _is_test_path ──

def test_is_test_path_tests_dir():
    assert _is_test_path(Path("tests/test_foo.rs")) is True
    assert _is_test_path(Path("src/tests/mod.rs")) is True


def test_is_test_path_test_dir():
    assert _is_test_path(Path("test/test_foo.py")) is True


def test_is_test_path_prefix():
    assert _is_test_path(Path("test_config.py")) is True
    assert _is_test_path(Path("test_utils.rs")) is True


def test_is_test_path_suffix():
    assert _is_test_path(Path("foo_test.py")) is True
    assert _is_test_path(Path("foo_test.rs")) is True
    assert _is_test_path(Path("foo.test.ts")) is True
    assert _is_test_path(Path("foo.spec.js")) is True


def test_is_test_path_false():
    assert _is_test_path(Path("src/lib.rs")) is False
    assert _is_test_path(Path("main.py")) is False
    assert _is_test_path(Path("utils/helpers.ts")) is False


# ── _count_params ──

def test_count_params_empty():
    assert _count_params("") == 0


def test_count_params_single():
    assert _count_params("self") == 1


def test_count_params_multiple():
    assert _count_params("self, x, y") == 3


def test_count_params_with_generics():
    """Angle-bracketed generics should not split on commas inside them."""
    assert _count_params("self, items: Vec<String>") == 2


def test_count_params_with_defaults():
    assert _count_params("self, name: str = '', count: int = 0") == 3


def test_count_params_nested_generics():
    assert _count_params("self, map: HashMap<String, Vec<i32>>") == 2


# ── _brace_counter_function_lengths ──

def test_brace_counter_small_function():
    code = "fn small() {\n    let x = 1;\n}\n"
    violations = _brace_counter_function_lengths(Path("test.rs"), code, 50)
    assert violations == []


def test_brace_counter_long_function():
    lines = ["fn long() {"] + [f"    let x = {i};" for i in range(100)] + ["}"]
    code = "\n".join(lines)
    violations = _brace_counter_function_lengths(Path("test.rs"), code, 50)
    assert len(violations) >= 1


def test_brace_counter_nested_braces():
    """Nested blocks are counted correctly — function ends when outer brace closes."""
    code = (
        "fn outer() {\n"
        "    if true {\n"
        "        let x = 1;\n"
        "    }\n"
        "    for i in 0..10 {\n"
        "        let y = i;\n"
        "    }\n"
        "}\n"
    )
    violations = _brace_counter_function_lengths(Path("test.rs"), code, 50)
    assert violations == []


# ── check_god_file ──

def test_god_file_clean():
    code = "\n".join(f"use crate::db::{name};" for name in ["User", "Profile", "Session"])
    violations = check_god_file(
        Path("lib.rs"), code,
        {"enabled": True, "max_public_items": 15, "max_imports": 20},
    )
    assert violations == []


def test_god_file_too_many_imports():
    code = "\n".join(f"use crate::dep_{i}::Item;" for i in range(25))
    violations = check_god_file(
        Path("lib.rs"), code,
        {"enabled": True, "max_public_items": 15, "max_imports": 20},
    )
    assert len(violations) >= 1
    assert any("imports" in v["message"].lower() for v in violations)


def test_god_file_too_many_public():
    code = "\n".join(f"pub fn item_{i}() {{}}" for i in range(20))
    violations = check_god_file(
        Path("lib.rs"), code,
        {"enabled": True, "max_public_items": 15, "max_imports": 20},
    )
    assert len(violations) >= 1
    assert any("public" in v["message"].lower() for v in violations)


def test_god_file_disabled():
    violations = check_god_file(
        Path("lib.rs"), "",
        {"enabled": False},
    )
    assert violations == []


# ── check_unsafe_patterns ──

def test_unsafe_patterns_clean():
    violations = check_unsafe_patterns(
        Path("src/lib.rs"), "fn safe() { let x = 1; }\n",
        {"enabled": True},
    )
    assert violations == []


def test_unsafe_patterns_eval():
    violations = check_unsafe_patterns(
        Path("src/lib.rs"), 'x = eval("2 + 2")',
        {"enabled": True},
    )
    assert len(violations) >= 1
    assert "eval" in violations[0]["message"].lower()


def test_unsafe_patterns_unsafe_block():
    violations = check_unsafe_patterns(
        Path("src/lib.rs"), "unsafe { *ptr }\n",
        {"enabled": True},
    )
    assert len(violations) >= 1


def test_unsafe_patterns_skips_test_files():
    violations = check_unsafe_patterns(
        Path("tests/test_bad.rs"), 'eval("bad")',
        {"enabled": True},
    )
    assert violations == []


def test_unsafe_patterns_disabled():
    violations = check_unsafe_patterns(
        Path("src/lib.rs"), 'eval("bad")',
        {"enabled": False},
    )
    assert violations == []


# ── check_deep_nesting ──

def test_deep_nesting_clean():
    code = "fn flat() {\n    let x = 1;\n}\n"
    violations = check_deep_nesting(
        Path("lib.rs"), code,
        {"enabled": True, "max_depth": 4},
    )
    assert violations == []


def test_deep_nesting_violation():
    code = (
        "fn deeply_nested() {\n"
        "    if a {\n"
        "        if b {\n"
        "            if c {\n"
        "                if d {\n"
        "                    if e {\n"
        "                        let x = 1;\n"
        + "    }\n" * 5
    )
    violations = check_deep_nesting(
        Path("lib.rs"), code,
        {"enabled": True, "max_depth": 3},
    )
    assert len(violations) >= 1
    assert "Nesting depth" in violations[0]["message"]


def test_deep_nesting_disabled():
    violations = check_deep_nesting(
        Path("lib.rs"), "fn f() {\n    if a {\n        if b {\n            if c {\n                if d {\n                    if e {\n                        x\n    }}}}}\n",
        {"enabled": False},
    )
    assert violations == []


# ── check_parameter_count ──

def test_parameter_count_clean():
    code = "fn process(a: i32, b: i32, c: i32) -> i32 { a + b + c }\n"
    violations = check_parameter_count(
        Path("lib.rs"), code,
        {"enabled": True, "max_params": 5},
    )
    assert violations == []


def test_parameter_count_violation():
    code = "fn too_many(a: i32, b: i32, c: i32, d: i32, e: i32, f: i32, g: i32) {}\n"
    violations = check_parameter_count(
        Path("lib.rs"), code,
        {"enabled": True, "max_params": 5},
    )
    assert len(violations) >= 1
    assert "parameters" in violations[0]["message"].lower()


def test_parameter_count_with_generic_params():
    """Generics in angle brackets should not inflate the count."""
    code = "fn generic<T: Debug, U: Clone>(a: T, b: U) -> T { a }\n"
    violations = check_parameter_count(
        Path("lib.rs"), code,
        {"enabled": True, "max_params": 3},
    )
    assert violations == []  # 2 real params


def test_parameter_count_no_params():
    code = "fn no_args() -> i32 { 42 }\n"
    violations = check_parameter_count(
        Path("lib.rs"), code,
        {"enabled": True, "max_params": 3},
    )
    assert violations == []


def test_parameter_count_disabled():
    violations = check_parameter_count(
        Path("lib.rs"), "fn many(a, b, c, d, e, f) {}",
        {"enabled": False},
    )
    assert violations == []


# ── check_action_items ──

def test_action_items_clean():
    """Properly linked TODO is fine."""
    code = "// TODO(#123): Refactor this later\n"
    violations = check_action_items(
        Path("lib.rs"), code,
        {"enabled": True, "require_issue": True},
    )
    assert violations == []


def test_action_items_violation():
    """Unlinked TODO should be flagged."""
    code = "// TODO: fix this\n"
    violations = check_action_items(
        Path("lib.rs"), code,
        {"enabled": True, "require_issue": True},
    )
    assert len(violations) >= 1


def test_action_items_fixme():
    code = "// FIXME: this is broken\n"
    violations = check_action_items(
        Path("lib.rs"), code,
        {"enabled": True, "require_issue": True},
    )
    assert len(violations) >= 1


def test_action_items_hack():
    code = "// HACK: temporary workaround\n"
    violations = check_action_items(
        Path("lib.rs"), code,
        {"enabled": True, "require_issue": True},
    )
    assert len(violations) >= 1


def test_action_items_linked_todo():
    code = "// TODO(#456): implement\n"
    violations = check_action_items(
        Path("lib.rs"), code,
        {"enabled": True, "require_issue": True},
    )
    assert violations == []


def test_action_items_disabled():
    violations = check_action_items(
        Path("lib.rs"), "// TODO: broken",
        {"enabled": False},
    )
    assert violations == []


# ── check_hardcoded_values ──

def test_hardcoded_values_clean():
    code = "const API_URL: &str = \"https://api.example.com\";\n"
    violations = check_hardcoded_values(
        Path("src/lib.rs"), code,
        {"enabled": True},
    )
    assert violations == []


def test_hardcoded_values_url():
    code = 'let url = "https://api.production.example.com/v2/endpoint";\n'
    violations = check_hardcoded_values(
        Path("src/lib.rs"), code,
        {"enabled": True},
    )
    assert len(violations) >= 1


def test_hardcoded_values_ip():
    code = 'let host = "203.0.113.42";\n'
    violations = check_hardcoded_values(
        Path("src/lib.rs"), code,
        {"enabled": True},
    )
    assert len(violations) >= 1


def test_hardcoded_values_skips_private_ips():
    """127.x.x.x and 192.168.x.x are expected in local dev."""
    code = 'let host = "127.0.0.1";\nlet local = "192.168.1.1";\n'
    violations = check_hardcoded_values(
        Path("src/lib.rs"), code,
        {"enabled": True},
    )
    assert violations == []


def test_hardcoded_values_timeout():
    code = "let timeout = 30;\n"  # 30 seconds, >2 digits
    violations = check_hardcoded_values(
        Path("src/lib.rs"), code,
        {"enabled": True},
    )
    assert len(violations) >= 1


def test_hardcoded_values_skips_test_paths():
    violations = check_hardcoded_values(
        Path("tests/test_config.rs"), 'let url = "https://prod.example.com";',
        {"enabled": True},
    )
    assert violations == []


def test_hardcoded_values_disabled():
    violations = check_hardcoded_values(
        Path("src/lib.rs"), 'let url = "https://prod.example.com";',
        {"enabled": False},
    )
    assert violations == []


# ── check_missing_docs ──

def test_missing_docs_no_extractor():
    """When no plugin handles the extension, return empty (no crash)."""
    violations = check_missing_docs(
        Path("lib.xyzzy"), "pub fn foo() {}\n",
        {"enabled": True},
    )
    assert violations == []


def test_missing_docs_disabled():
    violations = check_missing_docs(
        Path("lib.rs"), "pub fn foo() {}\n",
        {"enabled": False},
    )
    assert violations == []


# ── check_duplicated_code ──

def test_duplicated_code_clean():
    code = "\n".join(f"    let x_{i} = compute({i});" for i in range(20))
    violations = check_duplicated_code(
        Path("lib.rs"), code,
        {"enabled": True, "n_gram_size": 5, "min_repeats": 2, "min_line_len": 10},
    )
    # All lines are different → no duplicates
    assert violations == []


def test_duplicated_code_violation():
    """Repeat the same 6-line block 3 times."""
    block = [
        "    let result = compute_something(x);",
        "    if result.is_err() { return Err(result.unwrap_err()); }",
        "    let value = result.unwrap();",
        "    store.save(key, value)?;",
        "    log::info!(\"saved {}\", key);",
        "    Ok(value)",
    ]
    code = "\n".join(block * 3)
    violations = check_duplicated_code(
        Path("lib.rs"), code,
        {"enabled": True, "n_gram_size": 5, "min_repeats": 2, "min_line_len": 10},
    )
    assert len(violations) >= 1
    assert "Duplicated" in violations[0]["message"]


def test_duplicated_code_short_lines_ignored():
    """Lines shorter than min_line_len are skipped, preventing duplicates."""
    code = "\n".join(["a"] * 20)  # all lines < 10 chars
    violations = check_duplicated_code(
        Path("lib.rs"), code,
        {"enabled": True, "n_gram_size": 5, "min_repeats": 2, "min_line_len": 10},
    )
    assert violations == []


def test_duplicated_code_too_few_lines():
    code = "let x = 1;\nlet y = 2;\n"
    violations = check_duplicated_code(
        Path("lib.rs"), code,
        {"enabled": True, "n_gram_size": 5, "min_repeats": 2, "min_line_len": 10},
    )
    assert violations == []


def test_duplicated_code_disabled():
    violations = check_duplicated_code(
        Path("lib.rs"), "let x = compute(1);\n" * 20,
        {"enabled": False},
    )
    assert violations == []


# ── check_entry_point_init ──

from guards.generic import check_entry_point_init


def test_entry_point_init_clean_rust():
    """Rust main with logging::init before tokio runtime."""
    code = (
        "fn main() {\n"
        "    logging::init(&config.log_level);\n"
        "    let rt = tokio::runtime::Runtime::new().unwrap();\n"
        "    rt.block_on(async { start().await });\n"
        "}\n"
    )
    violations = check_entry_point_init(
        Path("src/main.rs"), code,
        {"enabled": True, "required_calls": [
            {"pattern": "logging::init", "before": "tokio::runtime"},
        ]},
    )
    assert violations == [], f"Expected 0, got {violations}"


def test_entry_point_init_missing_init():
    """Rust main without logging::init — absence bug."""
    code = (
        "fn main() {\n"
        "    let rt = tokio::runtime::Runtime::new().unwrap();\n"
        "    rt.block_on(async { start().await });\n"
        "}\n"
    )
    violations = check_entry_point_init(
        Path("src/main.rs"), code,
        {"enabled": True, "required_calls": [
            {"pattern": "logging::init", "before": "tokio::runtime"},
        ]},
    )
    assert len(violations) >= 1
    assert "missing required initialization" in violations[0]["message"].lower()


def test_entry_point_init_wrong_order():
    """Init appears after service start — still a bug."""
    code = (
        "fn main() {\n"
        "    let rt = tokio::runtime::Runtime::new().unwrap();\n"
        "    rt.block_on(async { start().await });\n"
        "    logging::init(&config.log_level);\n"
        "}\n"
    )
    violations = check_entry_point_init(
        Path("src/main.rs"), code,
        {"enabled": True, "required_calls": [
            {"pattern": "logging::init", "before": "tokio::runtime"},
        ]},
    )
    assert len(violations) >= 1
    assert "AFTER" in violations[0]["message"]


def test_entry_point_init_skips_test_files():
    """Test files should not be checked."""
    code = "fn main() { tokio::runtime::new().unwrap(); }\n"
    violations = check_entry_point_init(
        Path("tests/main.rs"), code,
        {"enabled": True, "required_calls": [
            {"pattern": "logging::init", "before": "tokio"},
        ]},
    )
    assert violations == []


def test_entry_point_init_skips_non_entry_point():
    """Library code without main() should not be checked."""
    code = "pub fn helper() { let x = 1; }\n"
    violations = check_entry_point_init(
        Path("src/lib.rs"), code,
        {"enabled": True, "required_calls": [
            {"pattern": "logging::init", "before": "tokio"},
        ]},
    )
    assert violations == []


def test_entry_point_init_disabled():
    violations = check_entry_point_init(
        Path("src/main.rs"), "fn main() { tokio::runtime::new(); }",
        {"enabled": False, "required_calls": [
            {"pattern": "logging::init", "before": "tokio"},
        ]},
    )
    assert violations == []


def test_entry_point_init_no_config():
    """When no required_calls configured, should not flag anything."""
    code = "fn main() { tokio::runtime::new(); }"
    violations = check_entry_point_init(
        Path("src/main.rs"), code,
        {"enabled": True, "required_calls": []},
    )
    assert violations == []


def test_entry_point_init_python_clean():
    """Python main with logging.basicConfig before app.run."""
    code = (
        "def main():\n"
        "    logging.basicConfig(level=logging.INFO)\n"
        "    app.run(host='0.0.0.0', port=8000)\n"
    )
    violations = check_entry_point_init(
        Path("main.py"), code,
        {"enabled": True, "required_calls": [
            {"pattern": "logging.basicConfig", "before": "app.run"},
        ]},
    )
    assert violations == []


def test_entry_point_init_python_missing():
    code = "def main():\n    app.run(host='0.0.0.0', port=8000)\n"
    violations = check_entry_point_init(
        Path("main.py"), code,
        {"enabled": True, "required_calls": [
            {"pattern": "logging.basicConfig", "before": "app.run"},
        ]},
    )
    assert len(violations) >= 1
