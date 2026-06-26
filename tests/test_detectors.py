"""Tests for detectors.py — language detection, file walking, glob generation."""

import sys
sys.path.insert(0, ".")

from pathlib import Path
from detectors import (
    detect_languages,
    relevant_file_globs,
    walk_source_files,
    IGNORED_DIRS,
)


# ── detect_languages ──

def test_detect_rust(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]\n")
    langs = detect_languages(str(tmp_path))
    assert "rust" in langs


def test_detect_python_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    langs = detect_languages(str(tmp_path))
    assert "python" in langs


def test_detect_python_requirements(tmp_path):
    (tmp_path / "requirements.txt").write_text("pytest\n")
    langs = detect_languages(str(tmp_path))
    assert "python" in langs


def test_detect_node(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    langs = detect_languages(str(tmp_path))
    assert "node" in langs


def test_detect_go(tmp_path):
    (tmp_path / "go.mod").write_text("module example")
    langs = detect_languages(str(tmp_path))
    assert "go" in langs


def test_detect_multiple(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]\n")
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    langs = detect_languages(str(tmp_path))
    assert "rust" in langs
    assert "python" in langs


def test_detect_fallback_by_source(tmp_path):
    """When no marker files exist, fall back to scanning source extensions."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.rs").write_text("fn main() {}")
    (tmp_path / "src" / "lib.rs").write_text("pub fn lib() {}")
    langs = detect_languages(str(tmp_path))
    assert "rust" in langs


def test_detect_none(tmp_path):
    """Empty directory without source files returns empty."""
    langs = detect_languages(str(tmp_path))
    assert langs == []


def test_detect_not_a_dir():
    langs = detect_languages("/nonexistent/path/12345")
    assert langs == []


# ── relevant_file_globs ──

def test_globs_rust():
    globs = relevant_file_globs(["rust"])
    assert "**/*.rs" in globs


def test_globs_python():
    globs = relevant_file_globs(["python"])
    assert "**/*.py" in globs


def test_globs_multiple():
    globs = relevant_file_globs(["rust", "python"])
    assert "**/*.rs" in globs
    assert "**/*.py" in globs


def test_globs_unknown_language():
    globs = relevant_file_globs(["brainfuck"])
    assert globs == []


# ── walk_source_files ──

def test_walk_finds_py_files(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')")
    (tmp_path / "utils.py").write_text("def util(): pass\n")
    files = walk_source_files(str(tmp_path), extensions={".py"})
    paths = [f.name for f in files]
    assert "main.py" in paths
    assert "utils.py" in paths


def test_walk_skips_ignored_dirs(tmp_path):
    """Files inside IGNORED_DIRS should be skipped."""
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "module.pyc").write_text("")  # suffix .pyc not in extension set
    (tmp_path / "__pycache__" / "cached.py").write_text("# cached")
    (tmp_path / "main.py").write_text("print('hello')")
    files = walk_source_files(str(tmp_path), extensions={".py"})
    names = [f.name for f in files]
    assert "main.py" in names
    assert "cached.py" not in names  # inside IGNORED_DIRS


def test_walk_skips_non_code_extensions(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')")
    (tmp_path / "README.md").write_text("# Project")
    (tmp_path / "data.json").write_text("{}")
    files = walk_source_files(str(tmp_path), extensions={".py"})
    names = [f.name for f in files]
    assert "main.py" in names
    assert "README.md" not in names
    assert "data.json" not in names


def test_walk_without_extensions_uses_defaults(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')")
    (tmp_path / "Cargo.toml").write_text("[package]\n")  # not a code extension
    files = walk_source_files(str(tmp_path))
    names = [f.name for f in files]
    assert "main.py" in names


def test_ignored_dirs_is_frozenset():
    assert isinstance(IGNORED_DIRS, frozenset)


def test_ignored_dirs_contains_expected():
    assert "__pycache__" in IGNORED_DIRS
    assert "node_modules" in IGNORED_DIRS
    assert ".git" in IGNORED_DIRS
    assert "target" in IGNORED_DIRS
