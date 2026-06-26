"""Python-specific plugin — registers extractors that let generic guards
work correctly on ``.py`` files without language-agnostic guards
ever branching on file extension themselves.

Currently contributes:
  - ``function_blocks`` extractor: given a Python source file, returns
    ``[{"name", "start_line", "length"}]`` for every top-level ``def``.
  - ``missing_docs`` extractor: returns ``[{"name", "type", "line"}]``
    for every public ``def`` / ``class`` lacking a docstring.
"""

import re
from pathlib import Path


_PY_DEF_RE = re.compile(
    r"^(?P<indent>\s*)(?:async\s+)?def\s+(?P<name>\w+)\s*\(",
    re.MULTILINE,
)


def python_extract_function_blocks(content: str) -> list[dict]:
    """Return one entry per Python function/block: ``name``, ``start_line`` (1-indexed)
    and ``length`` (line count). Skips private (``_``-prefixed) names.

    Block extent is computed by indentation: the block ends at the first
    non-blank line whose indent is ``<=`` the def's own indent.
    """
    lines = content.split("\n")
    blocks: list[dict] = []
    for m in _PY_DEF_RE.finditer(content):
        indent_str = m.group("indent")
        name = m.group("name")
        if name.startswith("_"):
            continue
        base_indent = len(indent_str)
        start_line = content[:m.start()].count("\n")
        end_line = start_line + 1
        for j in range(end_line, len(lines)):
            stripped = lines[j].strip()
            if stripped == "" or stripped.startswith("#"):
                continue
            indent = len(lines[j]) - len(lines[j].lstrip())
            if indent <= base_indent and stripped not in ("", "..."):
                break
            end_line = j
        blocks.append({
            "name": name,
            "start_line": start_line,
            "length": end_line - start_line + 1,
        })
    return blocks


# No (?P<>) capture groups here — kept simple because callers use group(1)/group(2).
_PY_PUB_RE = re.compile(r"^\s*def\s+(\w+)|^\s*class\s+(\w+)", re.MULTILINE)


def python_extract_missing_docs(content: str) -> list[dict]:
    """Return ``[{"name", "type", "line"}]`` for every public ``def`` or
    ``class`` in ``content`` that lacks a docstring on the lines following
    its declaration.

    Skips private names (underscore-prefixed). Allows up to 10 lines of
    signature continuation (lines ending in ``(`` or ``,``) before the
    docstring check.
    """
    lines = content.split("\n")
    missing: list[dict] = []
    for i, line in enumerate(lines):
        m = _PY_PUB_RE.match(line)
        if not m:
            continue
        func_name = m.group(1) or m.group(2)
        if func_name and func_name.startswith("_"):
            continue

        has_doc = False
        for j in range(i + 1, min(i + 10, len(lines))):
            stripped = lines[j].strip()
            if stripped == "" or stripped.startswith("#"):
                continue
            if (stripped.endswith("(") or stripped.endswith(",")
                    or stripped == ")" or stripped.startswith(")")):
                continue
            if stripped.startswith('"""') or stripped.startswith("'''"):
                has_doc = True
            break
        if not has_doc:
            kind = "class" if m.group(2) else "function"
            missing.append({"name": func_name, "type": kind, "line": i})
    return missing


def register(registry) -> None:
    """Register Python extractors with the plugin registry.

    Generic guards in ``guards/generic.py`` will pick these up automatically
    when they see a ``.py`` file — no extension branching in the core.
    """
    registry.register_extractor(
        "function_blocks", {".py"}, python_extract_function_blocks
    )
    registry.register_extractor(
        "missing_docs", {".py"}, python_extract_missing_docs
    )
