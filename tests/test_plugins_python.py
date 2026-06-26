"""Tests for plugins/python.py — extractors used by language-agnostic guards."""

import sys
sys.path.insert(0, ".")

from plugins.python import (
    python_extract_function_blocks,
    python_extract_missing_docs,
)


# ── function_blocks ──

def test_extract_single_function():
    code = "def hello():\n    return 42\n"
    blocks = python_extract_function_blocks(code)
    assert len(blocks) == 1
    assert blocks[0]["name"] == "hello"
    assert blocks[0]["length"] == 2


def test_extract_skips_private():
    code = "def _helper():\n    pass\n\ndef public():\n    pass\n"
    blocks = python_extract_function_blocks(code)
    assert len(blocks) == 1
    assert blocks[0]["name"] == "public"


def test_extract_async_function():
    code = "async def fetch():\n    return await something()\n"
    blocks = python_extract_function_blocks(code)
    assert len(blocks) == 1
    assert blocks[0]["name"] == "fetch"


def test_extract_multiple_functions():
    code = (
        "def foo():\n    return 1\n\n"
        "def bar():\n    x = 1\n    return x\n\n"
        "def baz():\n    pass\n"
    )
    blocks = python_extract_function_blocks(code)
    assert len(blocks) == 3
    assert [b["name"] for b in blocks] == ["foo", "bar", "baz"]


def test_extract_function_with_inner_logic():
    """Indented inner blocks don't break outer function boundary detection."""
    code = (
        "def outer():\n"
        "    x = 1\n"
        "    if x > 0:\n"
        "        inner = x * 2\n"
        "    return x\n"
    )
    blocks = python_extract_function_blocks(code)
    assert len(blocks) == 1
    assert blocks[0]["name"] == "outer"
    assert blocks[0]["start_line"] == 0  # 0-indexed
    assert blocks[0]["length"] == 5


def test_extract_empty_source():
    blocks = python_extract_function_blocks("")
    assert blocks == []


def test_extract_no_functions():
    code = "x = 1\ny = 2\nprint(x + y)\n"
    blocks = python_extract_function_blocks(code)
    assert blocks == []


# ── missing_docs ──

def test_missing_docs_function_without_docstring():
    code = "def process():\n    return 42\n"
    missing = python_extract_missing_docs(code)
    assert len(missing) == 1
    assert missing[0]["name"] == "process"
    assert missing[0]["type"] == "function"


def test_missing_docs_function_with_docstring():
    code = 'def process():\n    """Processes data."""\n    return 42\n'
    missing = python_extract_missing_docs(code)
    assert len(missing) == 0


def test_missing_docs_function_with_single_quote_docstring():
    code = "def process():\n    '''Processes data.'''\n    return 42\n"
    missing = python_extract_missing_docs(code)
    assert len(missing) == 0


def test_missing_docs_class_without_docstring():
    code = "class User:\n    pass\n"
    missing = python_extract_missing_docs(code)
    assert len(missing) == 1
    assert missing[0]["type"] == "class"


def test_missing_docs_skips_private():
    code = "def _helper():\n    return 1\n"
    missing = python_extract_missing_docs(code)
    assert len(missing) == 0


def test_missing_docs_multiline_signature():
    """Docstring check allows multi-line signatures before docstring."""
    code = (
        "def complex_fn(\n"
        "    a: int,\n"
        "    b: str,\n"
        "):\n"
        '    """Does complex stuff."""\n'
        "    return a\n"
    )
    missing = python_extract_missing_docs(code)
    assert len(missing) == 0


def test_missing_docs_mixed():
    code = (
        "def has_doc():\n"
        '    """Documented."""\n'
        "    pass\n\n"
        "def no_doc():\n"
        "    pass\n\n"
        "class MyClass:\n"
        '    """A class."""\n'
        "    pass\n"
    )
    missing = python_extract_missing_docs(code)
    assert len(missing) == 1
    assert missing[0]["name"] == "no_doc"


def test_missing_docs_empty():
    assert python_extract_missing_docs("") == []
