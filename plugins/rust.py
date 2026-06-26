"""Rust-specific guards — enabled when Cargo.toml is detected."""

import re
from pathlib import Path

GUARD_NAME = "rust"
LANGUAGES = ["rust"]
EXTENSIONS = {".rs"}


def check_no_unwrap(path: Path, content: str, _cfg: dict) -> list[dict]:
    """No .unwrap(), .expect(), or .unwrap_unchecked() in library code."""
    violations = []
    unwrap_re = re.compile(r"\.unwrap\(")
    expect_re = re.compile(r"\.expect\(")
    unchecked_re = re.compile(r"\.unwrap_unchecked\(")

    in_test = False
    test_depth = 0

    for i, line in enumerate(content.split("\n")):
        if "#[cfg(test)]" in line:
            in_test = True
            test_depth = 0
        if in_test:
            test_depth += line.count("{") - line.count("}")
            if test_depth <= 0 and "}" in line:
                in_test = False
            continue
        trimmed = line.strip()
        if trimmed.startswith("//") or trimmed.startswith("///") or trimmed.startswith("/*"):
            continue

        for re_obj, name in [(unwrap_re, ".unwrap("), (expect_re, ".expect("), (unchecked_re, ".unwrap_unchecked(")]:
            if re_obj.search(line):
                violations.append({
                    "file": str(path),
                    "line": i + 1,
                    "message": f"forbidden call `{name}` in library code — use `?` or proper error handling",
                    "guard": "rust::no_unwrap",
                })
    return violations


def check_tracing_instrument(path: Path, content: str, _cfg: dict) -> list[dict]:
    """Public async functions should have #[tracing::instrument]."""
    violations = []
    lines = content.split("\n")
    fn_re = re.compile(r"^\s*(pub\s+)?async\s+fn\s+(\w+)")

    for i, line in enumerate(lines):
        m = fn_re.match(line)
        if not m:
            continue
        # Only flag public async functions (not internal helpers)
        if not m.group(1):
            continue
        fn_name = m.group(2)
        if fn_name.startswith("test") or fn_name == "run" or fn_name == "main":
            continue
        # Check if preceded by #[tracing::instrument]
        has_instrument = False
        for j in range(max(0, i - 5), i):
            prev = lines[j].strip()
            if prev.startswith("#[tracing::instrument") or prev.startswith("#[instrument"):
                has_instrument = True
                break
        if not has_instrument:
            violations.append({
                "file": str(path),
                "line": i + 1,
                "message": f"Public async function `{fn_name}` without #[tracing::instrument]",
                "guard": "rust::tracing_instrument",
            })
    return violations


_RUST_DOC_RE = re.compile(
    r"^\s*pub\s+(?:async\s+)?(?:unsafe\s+)?(fn|struct|enum|trait|mod)\s+(\w+)"
)


def rust_extract_missing_docs(content: str) -> list[dict]:
    """Return ``[{"name", "type", "line"}]`` for every public Rust item
    (``pub fn``, ``pub struct``, ``pub enum``, ``pub trait``, ``pub mod``)
    in ``content`` that does not have a preceding ``///``` doc comment.

    Allows for ``#[...]`` attributes (``#[derive(...)]``, ``#[cfg(...)]``)
    between the doc comment and the item itself.
    """
    lines = content.split("\n")
    missing: list[dict] = []
    for i, line in enumerate(lines):
        m = _RUST_DOC_RE.match(line)
        if not m:
            continue
        item_type, item_name = m.group(1), m.group(2)
        if item_name in ("new", "default", "run", "main"):
            continue

        has_doc = False
        for j in range(max(0, i - 5), i):
            prev = lines[j].strip()
            if prev.startswith("///") or prev.startswith("#[doc"):
                has_doc = True
                break
            if prev.startswith("#["):
                continue  # #[derive(...)] and similar — keep scanning
            if prev == "":
                continue
            break
        if not has_doc:
            missing.append({"name": item_name, "type": item_type, "line": i})
    return missing


def register(plugin_system):
    """Register all Rust guards + extractors."""
    plugin_system.register_guard(
        name="no_unwrap",
        check_fn=check_no_unwrap,
        languages=LANGUAGES,
        description="No .unwrap()/.expect() in library code",
    )
    plugin_system.register_guard(
        name="tracing_instrument",
        check_fn=check_tracing_instrument,
        languages=LANGUAGES,
        description="Public async functions must have #[tracing::instrument]",
    )
    plugin_system.register_extractor(
        "missing_docs", {".rs"}, rust_extract_missing_docs
    )
