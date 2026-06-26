"""Tests for server.py — sandbox, handlers, formatting, dispatch table."""

import json
import os
import sys
import asyncio
sys.path.insert(0, ".")

import pytest
from pathlib import Path

from server import (
    _is_safe_project_path,
    _SANDBOX_DENY_TOKENS,
    _SANDBOX_DENY_PREFIXES,
    format_report,
    TOOL_DEFINITIONS,
    TOOL_HANDLERS,
    create_app,
    handle_probe,
    handle_list_guards,
    handle_detect_languages,
    handle_declare_intent,
    handle_save_baseline,
    handle_check_project,
    handle_check_file,
    handle_plan,
    handle_update_task,
    handle_list_tasks,
)


# ──────────────────────────────────────────────
# _is_safe_project_path — sandbox
# ──────────────────────────────────────────────

def test_sandbox_valid_path(tmp_path):
    ok, resolved = _is_safe_project_path(str(tmp_path))
    assert ok is True
    assert resolved == str(tmp_path.resolve())


def test_sandbox_nonexistent_path(tmp_path):
    ok, msg = _is_safe_project_path(str(tmp_path / "nonexistent"))
    assert ok is False
    assert "does not exist" in msg


def test_sandbox_denies_aws_credentials(tmp_path):
    (tmp_path / ".aws").mkdir()
    ok, msg = _is_safe_project_path(str(tmp_path / ".aws"))
    assert ok is False
    assert "credential" in msg.lower() or ".aws" in msg


def test_sandbox_denies_ssh(tmp_path):
    (tmp_path / ".ssh").mkdir()
    ok, msg = _is_safe_project_path(str(tmp_path / ".ssh"))
    assert ok is False


def test_sandbox_denies_proc():
    """Kernel filesystem paths should be rejected."""
    ok, msg = _is_safe_project_path("/proc/cpuinfo")
    assert ok is False


def test_sandbox_denies_sys():
    ok, msg = _is_safe_project_path("/sys/class")
    assert ok is False


def test_sandbox_denies_dev():
    ok, msg = _is_safe_project_path("/dev/null")
    assert ok is False


def test_sandbox_denies_kube(tmp_path):
    (tmp_path / ".kube").mkdir()
    ok, msg = _is_safe_project_path(str(tmp_path / ".kube"))
    assert ok is False


def test_sandbox_path_with_aws_in_name(tmp_path):
    """A path like 'my-aws-app' does NOT contain the token '.aws'
    (dot-prefixed). The sandbox correctly allows it."""
    (tmp_path / "my-aws-app").mkdir()
    ok, _ = _is_safe_project_path(str(tmp_path / "my-aws-app"))
    assert ok is True


def test_sandbox_deny_tokens_is_tuple():
    assert isinstance(_SANDBOX_DENY_TOKENS, tuple)


def test_sandbox_deny_prefixes_is_tuple():
    assert isinstance(_SANDBOX_DENY_PREFIXES, tuple)


def test_sandbox_deny_tokens_contains_expected():
    assert ".aws" in _SANDBOX_DENY_TOKENS
    assert ".ssh" in _SANDBOX_DENY_TOKENS
    assert ".kube" in _SANDBOX_DENY_TOKENS


# ──────────────────────────────────────────────
# format_report
# ──────────────────────────────────────────────

def test_format_report_empty():
    result = format_report("/my/project", [], ["rust"], {"guards": {}})
    assert "All guards passed" in result
    assert "/my/project" in result


def test_format_report_with_violations():
    violations = [
        {"file": "src/lib.rs", "line": 42, "guard": "file_length",
         "message": "File exceeds 200 lines (350)"},
        {"file": "src/main.rs", "line": 10, "guard": "magic_numbers",
         "message": "Magic number 86400"},
    ]
    result = format_report("/my/project", violations, ["rust"], {"guards": {}})
    assert "2 violation(s) found" in result
    assert "file_length" in result
    assert "magic_numbers" in result
    assert "src/lib.rs:42" in result


def test_format_report_groups_by_guard():
    violations = [
        {"file": "a.rs", "line": 1, "guard": "god_file",
         "message": "msg1"},
        {"file": "b.rs", "line": 1, "guard": "god_file",
         "message": "msg2"},
        {"file": "c.rs", "line": 1, "guard": "no_stubs",
         "message": "msg3"},
    ]
    result = format_report("/p", violations, ["rust"], {"guards": {}})
    assert "3 violation(s) found" in result
    assert "[god_file]" in result
    assert "[no_stubs]" in result


def test_format_report_truncates_long_lists():
    """If a guard has >10 violations, only first 10 are shown."""
    violations = [
        {"file": f"src/file_{i}.rs", "line": i, "guard": "file_length",
         "message": f"msg {i}"}
        for i in range(15)
    ]
    result = format_report("/p", violations, ["rust"], {"guards": {}})
    assert "15 violation(s) found" in result
    assert "... and 5 more" in result


def test_format_report_unknown_language():
    result = format_report("/p", [], [], {"guards": {}})
    assert "unknown" in result


# ──────────────────────────────────────────────
# TOOL_DEFINITIONS and TOOL_HANDLERS
# ──────────────────────────────────────────────

def test_all_handlers_have_definitions():
    """Every handler in TOOL_HANDLERS must have a Tool definition."""
    handler_names = set(TOOL_HANDLERS.keys())
    definition_names = {t.name for t in TOOL_DEFINITIONS}
    missing = handler_names - definition_names
    assert not missing, f"Missing tool definitions for: {missing}"


def test_all_definitions_have_handlers():
    """Every Tool definition must have a handler."""
    handler_names = set(TOOL_HANDLERS.keys())
    definition_names = {t.name for t in TOOL_DEFINITIONS}
    extra = definition_names - handler_names
    assert not extra, f"Extra tool definitions without handlers: {extra}"


def test_tool_definitions_count():
    assert len(TOOL_DEFINITIONS) == len(TOOL_HANDLERS)


# ──────────────────────────────────────────────
# handle_probe (no file I/O)
# ──────────────────────────────────────────────

def test_handle_probe_basic():
    """Probe handler should work without any file I/O."""
    result = asyncio.run(handle_probe(None, {
        "description": "Build a task tracker",
    }))
    text = result[0].text
    assert "The Real Goal" in text
    assert "Scope" in text
    assert "Preferences" in text


def test_handle_probe_with_competitor():
    result = asyncio.run(handle_probe(None, {
        "description": "Build a task tracker",
        "competitor": "Jira",
    }))
    text = result[0].text
    assert "Jira" in text
    assert "Research" in text


# ──────────────────────────────────────────────
# handle_list_guards (no file I/O)
# ──────────────────────────────────────────────

class FakeRegistry:
    def __init__(self):
        self.guards = []


def test_handle_list_guards():
    reg = FakeRegistry()
    reg.guards.append({
        "name": "no_unwrap",
        "languages": ["rust"],
        "description": "No .unwrap() in library code",
    })
    result = asyncio.run(handle_list_guards(reg, {}))
    data = json.loads(result[0].text)
    assert "guards" in data
    names = [g["name"] for g in data["guards"]]
    assert "file_length" in names
    assert "no_unwrap" in names


def test_handle_list_guards_empty_registry():
    reg = FakeRegistry()
    result = asyncio.run(handle_list_guards(reg, {}))
    data = json.loads(result[0].text)
    # Built-in guards should be present (at least file_length)
    names = [g["name"] for g in data["guards"]]
    assert "file_length" in names
    assert "god_file" in names


# ──────────────────────────────────────────────
# handle_detect_languages
# ──────────────────────────────────────────────

def test_handle_detect_languages(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]\n")
    result = asyncio.run(handle_detect_languages(None, {"path": str(tmp_path)}))
    data = json.loads(result[0].text)
    assert "rust" in data["languages"]


def test_handle_detect_languages_sandbox_rejects(tmp_path):
    result = asyncio.run(handle_detect_languages(None, {
        "path": str(tmp_path / "nonexistent"),
    }))
    assert "Refused" in result[0].text


# ──────────────────────────────────────────────
# handle_declare_intent + check_project integration
# ──────────────────────────────────────────────

SAMPLE_MODULES = [
    {
        "name": "core",
        "path": "src/core",
        "responsibility": "Business logic",
        "error_strategy": "Result",
        "logging": "tracing",
        "testing": "unit tests",
    },
]

SAMPLE_GLOBAL = {
    "error_handling": "Propagate via Result",
    "logging": "tracing",
}


def test_handle_declare_intent(tmp_path):
    registry = FakeRegistry()
    result = asyncio.run(handle_declare_intent(registry, {
        "path": str(tmp_path),
        "modules": SAMPLE_MODULES,
        "global": SAMPLE_GLOBAL,
    }))
    text = result[0].text
    assert "Architectural intent saved" in text
    assert (tmp_path / ".codeguards" / "intent.json").exists()


def test_handle_declare_intent_sandbox_rejects(tmp_path):
    registry = FakeRegistry()
    result = asyncio.run(handle_declare_intent(registry, {
        "path": str(tmp_path / "nonexistent"),
        "modules": SAMPLE_MODULES,
        "global": SAMPLE_GLOBAL,
    }))
    assert "Refused" in result[0].text


def test_handle_check_project_no_intent(tmp_path):
    """When no intent declared, check_project asks to probe first."""
    registry = FakeRegistry()
    result = asyncio.run(handle_check_project(registry, {"path": str(tmp_path)}))
    text = result[0].text
    assert "don't know what you're building" in text.lower() or "probe" in text.lower()


def test_handle_check_project_with_intent_and_violations(tmp_path):
    """With intent declared and a file violating guards."""
    from intent import save_intent

    # Declare intent
    save_intent(str(tmp_path), {
        "modules": SAMPLE_MODULES,
        "global": SAMPLE_GLOBAL,
    })

    # Create a file that violates file_length
    (tmp_path / "src").mkdir()
    long_file = "\n".join(f"line {i}" for i in range(500))
    (tmp_path / "src" / "big.rs").write_text(long_file)

    registry = FakeRegistry()
    result = asyncio.run(handle_check_project(registry, {"path": str(tmp_path)}))
    text = result[0].text
    assert "CodeGuards Report" in text
    # Should find file_length violation (500 lines > 200 max)
    assert "violation" in text.lower()


# ──────────────────────────────────────────────
# handle_plan + update_task + list_tasks
# ──────────────────────────────────────────────

def test_handle_plan_no_intent(tmp_path):
    registry = FakeRegistry()
    result = asyncio.run(handle_plan(registry, {"path": str(tmp_path)}))
    text = result[0].text
    assert "No architectural intent" in text


def test_handle_plan_with_intent(tmp_path):
    from intent import save_intent
    save_intent(str(tmp_path), {
        "modules": SAMPLE_MODULES,
        "global": SAMPLE_GLOBAL,
    })

    registry = FakeRegistry()
    result = asyncio.run(handle_plan(registry, {"path": str(tmp_path)}))
    text = result[0].text
    assert "Planning created" in text
    assert ".planning" in text
    assert (tmp_path / ".planning" / "ARCHITECTURE.md").exists()
    assert (tmp_path / ".planning" / "PROJECT_PLAN.md").exists()


def test_handle_update_task_and_list(tmp_path):
    """Integration: plan → update task → list tasks."""
    from intent import save_intent
    save_intent(str(tmp_path), {
        "modules": SAMPLE_MODULES,
        "global": SAMPLE_GLOBAL,
    })

    registry = FakeRegistry()

    # First, create a plan
    asyncio.run(handle_plan(registry, {"path": str(tmp_path)}))

    # Mark first task complete
    result = asyncio.run(handle_update_task(registry, {
        "path": str(tmp_path),
        "task_id": "T1.1",
        "status": "completed",
    }))
    assert "marked as completed" in result[0].text

    # List tasks — should have 2 pending
    result = asyncio.run(handle_list_tasks(registry, {"path": str(tmp_path)}))
    text = result[0].text
    assert "pending" in text


def test_handle_update_task_nonexistent(tmp_path):
    registry = FakeRegistry()
    result = asyncio.run(handle_update_task(registry, {
        "path": str(tmp_path),
        "task_id": "T99.99",
    }))
    assert "not found" in result[0].text


def test_handle_list_tasks_empty(tmp_path):
    registry = FakeRegistry()
    result = asyncio.run(handle_list_tasks(registry, {"path": str(tmp_path)}))
    text = result[0].text
    assert "No pending tasks" in text


# ──────────────────────────────────────────────
# handle_save_baseline
# ──────────────────────────────────────────────

def test_handle_save_baseline_empty_project(tmp_path):
    registry = FakeRegistry()
    result = asyncio.run(handle_save_baseline(registry, {"path": str(tmp_path)}))
    text = result[0].text
    assert "Structural baseline saved" in text


def test_handle_save_baseline_with_files(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "lib.rs").write_text(
        "use crate::db::User;\npub fn process() {}\n"
    )
    registry = FakeRegistry()
    result = asyncio.run(handle_save_baseline(registry, {"path": str(tmp_path)}))
    text = result[0].text
    assert "Structural baseline saved" in text


# ──────────────────────────────────────────────
# handle_check_file
# ──────────────────────────────────────────────

def test_handle_check_file_sandbox_rejects(tmp_path):
    registry = FakeRegistry()
    result = asyncio.run(handle_check_file(registry, {
        "path": str(tmp_path / "nonexistent.rs"),
    }))
    text = result[0].text
    assert "Refused" in text or "does not exist" in text


def test_handle_check_file_clean(tmp_path):
    (tmp_path / "small.rs").write_text("fn small() { let x = 1; }\n")
    registry = FakeRegistry()
    result = asyncio.run(handle_check_file(registry, {
        "path": str(tmp_path / "small.rs"),
        "project_root": str(tmp_path),
    }))
    text = result[0].text
    assert "CodeGuards Report" in text


def test_handle_check_file_with_plugin_guard(tmp_path):
    """Plugin guards from the registry should be invoked on matching files."""
    (tmp_path / "lib.rs").write_text('fn bad() { some_option.unwrap(); }\n')
    registry = FakeRegistry()
    # Add a real guard that should trigger on .unwrap()
    from plugins.rust import check_no_unwrap
    registry.guards.append({
        "name": "no_unwrap",
        "languages": ["rust"],
        "file_extensions": {".rs"},
        "check_fn": check_no_unwrap,
    })
    result = asyncio.run(handle_check_file(registry, {
        "path": str(tmp_path / "lib.rs"),
        "project_root": str(tmp_path),
    }))
    text = result[0].text
    assert "CodeGuards Report" in text
    # no_unwrap should flag .unwrap()
    assert "no_unwrap" in text or "unwrap" in text.lower()


# ──────────────────────────────────────────────
# Sandbox integration — shared across handlers
# ──────────────────────────────────────────────

def test_sandbox_rejects_bad_paths_for_sandboxed_handlers(tmp_path):
    """All handlers that call _is_safe_project_path should reject bad paths."""
    bad_path = str(tmp_path / "nonexistent_dir" / "nonexistent_file")
    registry = FakeRegistry()

    # check_project
    result = asyncio.run(handle_check_project(registry, {"path": bad_path}))
    assert "Refused" in result[0].text

    # save_baseline
    result = asyncio.run(handle_save_baseline(registry, {"path": bad_path}))
    assert "Refused" in result[0].text

    # plan
    result = asyncio.run(handle_plan(registry, {"path": bad_path}))
    assert "Refused" in result[0].text

    # update_task
    result = asyncio.run(handle_update_task(registry, {"path": bad_path, "task_id": "T1"}))
    assert "Refused" in result[0].text

    # list_tasks
    result = asyncio.run(handle_list_tasks(registry, {"path": bad_path}))
    assert "Refused" in result[0].text


# ──────────────────────────────────────────────
# create_app
# ──────────────────────────────────────────────

def test_create_app_returns_server():
    """Smoke test that create_app returns a valid MCP server."""
    try:
        from server import HAS_MCP
        if not HAS_MCP:
            pytest.skip("MCP not installed")
    except Exception:
        pytest.skip("Cannot check HAS_MCP")

    registry = FakeRegistry()
    server = create_app(registry)
    assert server is not None
    assert hasattr(server, '_guard_registry')


# ──────────────────────────────────────────────
# format_report edge cases
# ──────────────────────────────────────────────

def test_format_report_violations_without_fix_field():
    """format_report renders file, line, and message — fix field is not
    included in the report (fixes are attached via enrich_with_fixes, not
    displayed by format_report)."""
    violations = [{
        "file": "src/lib.rs", "line": 1, "guard": "file_length",
        "message": "File exceeds 200 lines (350)",
        "fix": "Split at line 200",
    }]
    result = format_report("/p", violations, ["rust"], {"guards": {}})
    # Message text IS included
    assert "File exceeds 200 lines" in result
    # fix text is NOT rendered by format_report
    assert "Split at line 200" not in result
