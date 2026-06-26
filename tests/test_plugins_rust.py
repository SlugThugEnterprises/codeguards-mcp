"""Tests for plugins/rust.py — per-language guards and missing_docs extractor."""

import sys
sys.path.insert(0, ".")

from pathlib import Path
from plugins.rust import (
    check_no_unwrap,
    check_tracing_instrument,
    rust_extract_missing_docs,
    register,
)


# ── check_no_unwrap ──

def test_no_unwrap_clean():
    violations = check_no_unwrap(
        Path("lib.rs"),
        "fn process() -> Result<()> {\n    Ok(())\n}\n",
        {},
    )
    assert violations == []


def test_no_unwrap_violation():
    violations = check_no_unwrap(
        Path("lib.rs"),
        'fn process() { let x = some_option.unwrap(); }\n',
        {},
    )
    assert len(violations) >= 1
    assert "unwrap" in violations[0]["message"]


def test_no_unwrap_expect_violation():
    violations = check_no_unwrap(
        Path("lib.rs"),
        'fn process() { let x = some_option.expect("boom"); }\n',
        {},
    )
    assert len(violations) >= 1
    assert "expect" in violations[0]["message"]


def test_no_unwrap_unchecked_violation():
    violations = check_no_unwrap(
        Path("lib.rs"),
        "fn process() { let x = ptr.unwrap_unchecked(); }\n",
        {},
    )
    assert len(violations) >= 1


def test_no_unwrap_skips_cfg_test():
    """Code inside #[cfg(test)] module should be ignored."""
    code = (
        "#[cfg(test)]\n"
        "mod tests {\n"
        "    use super::*;\n"
        '    #[test]\n'
        "    fn test_it() {\n"
        "        let x = Some(42).unwrap();\n"
        "    }\n"
        "}\n"
    )
    violations = check_no_unwrap(Path("lib.rs"), code, {})
    assert violations == []


def test_no_unwrap_skips_comments():
    code = '// We could use .unwrap() here but won\'t\nfn safe() -> Result<()> { Ok(()) }\n'
    violations = check_no_unwrap(Path("lib.rs"), code, {})
    assert violations == []


# ── check_tracing_instrument ──

def test_tracing_instrument_clean():
    code = (
        "#[tracing::instrument]\n"
        "pub async fn process() -> Result<()> {\n"
        "    Ok(())\n"
        "}\n"
    )
    violations = check_tracing_instrument(Path("lib.rs"), code, {})
    assert violations == []


def test_tracing_instrument_shorthand():
    code = (
        "#[instrument]\n"
        "pub async fn process() -> Result<()> {\n"
        "    Ok(())\n"
        "}\n"
    )
    violations = check_tracing_instrument(Path("lib.rs"), code, {})
    assert violations == []


def test_tracing_instrument_violation():
    code = (
        "pub async fn fetch_data() -> Result<Vec<u8>> {\n"
        "    Ok(vec![])\n"
        "}\n"
    )
    violations = check_tracing_instrument(Path("lib.rs"), code, {})
    assert len(violations) >= 1
    assert "fetch_data" in violations[0]["message"]


def test_tracing_instrument_skips_test_fn():
    code = "pub async fn test_foo() -> Result<()> { Ok(()) }\n"
    violations = check_tracing_instrument(Path("lib.rs"), code, {})
    assert violations == []


def test_tracing_instrument_skips_main():
    code = "pub async fn main() -> Result<()> { Ok(()) }\n"
    violations = check_tracing_instrument(Path("lib.rs"), code, {})
    assert violations == []


def test_tracing_instrument_skips_run():
    code = "pub async fn run() -> Result<()> { Ok(()) }\n"
    violations = check_tracing_instrument(Path("lib.rs"), code, {})
    assert violations == []


def test_tracing_instrument_private_fn():
    """Non-pub async functions should NOT require #[tracing::instrument]."""
    code = "async fn internal() -> Result<()> { Ok(()) }\n"
    violations = check_tracing_instrument(Path("lib.rs"), code, {})
    assert violations == []


# ── rust_extract_missing_docs ──

def test_missing_docs_clean():
    code = (
        "/// A public function.\n"
        "pub fn documented() -> i32 { 42 }\n"
    )
    missing = rust_extract_missing_docs(code)
    assert missing == []


def test_missing_docs_violation_fn():
    code = "pub fn undocumented() -> i32 { 42 }\n"
    missing = rust_extract_missing_docs(code)
    assert len(missing) == 1
    assert missing[0]["name"] == "undocumented"
    assert missing[0]["type"] == "fn"


def test_missing_docs_violation_struct():
    code = "pub struct User {\n    pub id: u64,\n}\n"
    missing = rust_extract_missing_docs(code)
    assert len(missing) == 1
    assert missing[0]["name"] == "User"
    assert missing[0]["type"] == "struct"


def test_missing_docs_violation_enum():
    code = "pub enum Status {\n    Active,\n    Inactive,\n}\n"
    missing = rust_extract_missing_docs(code)
    assert len(missing) == 1
    assert missing[0]["type"] == "enum"


def test_missing_docs_violation_trait():
    code = "pub trait Handler {\n    fn handle(&self) -> Result<()>;\n}\n"
    missing = rust_extract_missing_docs(code)
    assert len(missing) == 1
    assert missing[0]["type"] == "trait"


def test_missing_docs_violation_mod():
    code = "pub mod database;\n"
    missing = rust_extract_missing_docs(code)
    assert len(missing) == 1
    assert missing[0]["type"] == "mod"


def test_missing_docs_skips_common_names():
    """new, default, run, main are skipped even without docs."""
    code = "pub fn new() -> Self { Self {} }\npub fn default() -> Self { Self {} }\n"
    missing = rust_extract_missing_docs(code)
    assert missing == []


def test_missing_docs_attribute_between_doc_and_item():
    """#[derive(...)] and similar attributes between doc comment and item are allowed."""
    code = (
        "/// A documented struct with derives.\n"
        "#[derive(Debug, Clone)]\n"
        "pub struct Config {\n"
        "    pub name: String,\n"
        "}\n"
    )
    missing = rust_extract_missing_docs(code)
    assert missing == []


def test_missing_docs_with_doc_attribute():
    code = (
        '#[doc = "An untagged enum."]\n'
        "pub enum Untagged {\n"
        "    A,\n"
        "    B,\n"
        "}\n"
    )
    missing = rust_extract_missing_docs(code)
    assert missing == []


def test_missing_docs_empty():
    assert rust_extract_missing_docs("") == []


def test_missing_docs_private_items():
    """Private items (no 'pub') should not be flagged."""
    code = "fn helper() -> i32 { 42 }\nstruct Internal { x: i32 }\n"
    missing = rust_extract_missing_docs(code)
    assert missing == []


# ── register ──

def test_register_populates_guards_and_extractors():
    """After register(), the registry should have Rust guards + extractors."""

    class FakeRegistry:
        def __init__(self):
            self.guards = []
            self.extractors = {}

        def register_guard(self, name, check_fn, languages, description):
            self.guards.append({"name": name, "languages": languages})

        def register_extractor(self, capability, extensions, fn):
            self.extractors[capability] = extensions

    reg = FakeRegistry()
    register(reg)
    guard_names = [g["name"] for g in reg.guards]
    assert "no_unwrap" in guard_names
    assert "tracing_instrument" in guard_names
    assert "missing_docs" in reg.extractors
    assert ".rs" in reg.extractors["missing_docs"]
