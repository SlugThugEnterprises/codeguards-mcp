"""Tests for planning.py — ARCHITECTURE.md and PROJECT_PLAN.md generation."""

import sys
sys.path.insert(0, ".")

from pathlib import Path
from planning import (
    _split_frontmatter,
    create_architecture,
    load_architecture,
    create_plan,
    update_task,
    get_pending_tasks,
)


SAMPLE_INTENT = {
    "description": "An antidetect browser automation framework.",
    "global": {
        "error_handling": "Propagate errors via Result<>. No .unwrap().",
        "logging": "Use tracing with structured fields.",
        "testing": "All public fns must have unit tests.",
    },
    "modules": [
        {
            "name": "core",
            "path": "src/core",
            "responsibility": "Domain models and business logic",
            "error_strategy": "Return Result with custom error types",
            "logging": "tracing::instrument on all public fns",
            "testing": "Unit tests in tests/core/",
            "dependencies": [],
        },
        {
            "name": "api",
            "path": "src/api",
            "responsibility": "HTTP handlers and middleware",
            "error_strategy": "Convert errors to HTTP status codes",
            "logging": "Request/response logging with correlation IDs",
            "testing": "Integration tests in tests/api/",
            "dependencies": ["core"],
        },
    ],
}


# ── _split_frontmatter ──

def test_split_frontmatter_with_fm():
    content = "---\nkey: value\n---\n\n# Body text\n"
    fm, body = _split_frontmatter(content)
    assert fm == {"key": "value"}
    assert "# Body text" in body


def test_split_frontmatter_without_fm():
    content = "# Just a markdown file\n\nNo frontmatter here.\n"
    fm, body = _split_frontmatter(content)
    assert fm == {}
    assert body == content


def test_split_frontmatter_invalid_yaml():
    content = "---\nkey: [unclosed\n---\n\nbody\n"
    fm, body = _split_frontmatter(content)
    assert fm == {}
    assert "body" in body


def test_split_frontmatter_empty():
    fm, body = _split_frontmatter("")
    assert fm == {}
    assert body == ""


# ── create_architecture ──

def test_create_architecture_writes_file(tmp_path):
    path = create_architecture(str(tmp_path), SAMPLE_INTENT)
    assert Path(path).exists()
    content = Path(path).read_text()
    assert "Architecture Overview" in content
    assert "antidetect" in content
    assert "core" in content
    assert "api" in content


def test_create_architecture_frontmatter_has_modules(tmp_path):
    path = create_architecture(str(tmp_path), SAMPLE_INTENT)
    fm, _ = _split_frontmatter(Path(path).read_text())
    assert "modules" in fm
    assert "core" in fm["modules"]
    assert "api" in fm["modules"]
    assert "allowed_dependencies" in fm
    assert fm["allowed_dependencies"]["api"] == ["core"]


def test_create_architecture_no_modules(tmp_path):
    minimal = {"description": "Simple.", "global": {}}
    path = create_architecture(str(tmp_path), minimal)
    assert Path(path).exists()
    content = Path(path).read_text()
    assert "No modules declared" in content


def test_create_architecture_string_dependencies(tmp_path):
    """dependencies can be a comma-separated string."""
    intent = {
        "description": "Test",
        "global": {},
        "modules": [{
            "name": "db",
            "path": "src/db",
            "responsibility": "Data layer",
            "error_strategy": "Result",
            "logging": "tracing",
            "testing": "unit tests",
            "dependencies": "core, cache",
        }],
    }
    path = create_architecture(str(tmp_path), intent)
    fm, _ = _split_frontmatter(Path(path).read_text())
    assert fm["allowed_dependencies"]["db"] == ["core", "cache"]


# ── load_architecture ──

def test_load_architecture_exists(tmp_path):
    create_architecture(str(tmp_path), SAMPLE_INTENT)
    fm = load_architecture(str(tmp_path))
    assert fm is not None
    assert "modules" in fm


def test_load_architecture_no_file(tmp_path):
    assert load_architecture(str(tmp_path)) is None


# ── create_plan ──

def test_create_plan_writes_file(tmp_path):
    path = create_plan(str(tmp_path), SAMPLE_INTENT)
    assert Path(path).exists()
    content = Path(path).read_text()
    assert "Project Plan" in content
    assert "Task Progress" in content


def test_create_plan_has_frontmatter_with_phases(tmp_path):
    path = create_plan(str(tmp_path), SAMPLE_INTENT)
    content = Path(path).read_text()
    fm, _ = _split_frontmatter(content)
    assert "phases" in fm
    assert len(fm["phases"]) == 2  # one per module
    # All tasks start as pending
    for phase in fm["phases"]:
        for task in phase.get("tasks", []):
            assert task["status"] == "pending"


def test_create_plan_with_explicit_phases(tmp_path):
    custom = [{
        "id": "01",
        "goal": "Write the thing",
        "status": "in_progress",
        "effort": "large",
        "description": "Build it.",
        "tasks": [
            {"id": "T1.1", "description": "Part A", "file": "a.rs",
             "checks": ["no_unwrap"], "status": "completed"},
            {"id": "T1.2", "description": "Part B", "file": "b.rs",
             "checks": ["file_length"], "status": "pending"},
        ],
    }]
    path = create_plan(str(tmp_path), SAMPLE_INTENT, phases=custom)
    content = Path(path).read_text()
    assert "Write the thing" in content
    # 1 of 2 tasks completed
    assert "1/2 tasks completed" in content


def test_create_plan_no_modules(tmp_path):
    minimal = {"global": {}}
    path = create_plan(str(tmp_path), minimal)
    assert Path(path).exists()
    content = Path(path).read_text()
    assert "No phases" in content


# ── update_task ──

def test_update_task_completes(tmp_path):
    create_plan(str(tmp_path), SAMPLE_INTENT)
    result = update_task(str(tmp_path), "T1.1", "completed")
    assert result is True
    # Re-read and verify the task is now completed
    content = (Path(tmp_path) / ".planning" / "PROJECT_PLAN.md").read_text()
    fm, _ = _split_frontmatter(content)
    task_statuses = {}
    for phase in fm["phases"]:
        for task in phase["tasks"]:
            task_statuses[task["id"]] = task["status"]
    assert task_statuses["T1.1"] == "completed"


def test_update_task_nonexistent_plan(tmp_path):
    result = update_task(str(tmp_path), "T1.1", "completed")
    assert result is False


def test_update_task_nonexistent_task_id(tmp_path):
    create_plan(str(tmp_path), SAMPLE_INTENT)
    result = update_task(str(tmp_path), "T99.99", "completed")
    assert result is False


# ── get_pending_tasks ──

def test_get_pending_tasks_all_pending(tmp_path):
    create_plan(str(tmp_path), SAMPLE_INTENT)
    pending = get_pending_tasks(str(tmp_path))
    assert len(pending) == 6  # 2 modules × 3 tasks each


def test_get_pending_tasks_after_completion(tmp_path):
    create_plan(str(tmp_path), SAMPLE_INTENT)
    update_task(str(tmp_path), "T1.1", "completed")
    update_task(str(tmp_path), "T1.2", "completed")
    pending = get_pending_tasks(str(tmp_path))
    assert len(pending) == 4  # 6 total - 2 completed


def test_get_pending_tasks_no_plan(tmp_path):
    assert get_pending_tasks(str(tmp_path)) == []


def test_get_pending_tasks_no_frontmatter(tmp_path):
    plan_dir = tmp_path / ".planning"
    plan_dir.mkdir()
    (plan_dir / "PROJECT_PLAN.md").write_text("# No frontmatter\n")
    assert get_pending_tasks(str(tmp_path)) == []
