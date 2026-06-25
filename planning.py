"""Project planning — structured architecture + phased task plans.

Creates .planning/ARCHITECTURE.md and .planning/PROJECT_PLAN.md
with YAML frontmatter that CodeGuards tools can enforce against.
"""

import os
import re
from datetime import datetime
from pathlib import Path


PLANNING_DIR = ".planning"
ARCHITECTURE_FILE = "ARCHITECTURE.md"
PLAN_FILE = "PROJECT_PLAN.md"


# ── Architecture ──

ARCHITECTURE_TEMPLATE = """---
# Machine-readable architecture spec
# CodeGuards tools use this to enforce module boundaries and dependencies
modules: {}
layers: {}
allowed_dependencies: {}
enforce: []
---

# Architecture Overview

{overview}

## Modules

{module_details}

## Dependencies

{dependency_details}

## Enforcement Rules

- Modules must not import from modules outside their declared dependency list
- Each module's directory must be under the declared path
- Code in each module must pass its specific enforce checks
"""


def create_architecture(path: str, intent: dict) -> str:
    """Create or update ARCHITECTURE.md from declared intent."""
    plan_dir = Path(path) / PLANNING_DIR
    plan_dir.mkdir(parents=True, exist_ok=True)

    modules = intent.get("modules", [])
    global_rules = intent.get("global", {})

    # Build machine-readable frontmatter
    module_map = {}
    layer_map = {}
    deps_map = {}

    for m in modules:
        name = m.get("name", "unknown")
        mod_path = m.get("path", "")
        module_map[name] = {
            "dir": mod_path,
            "resp": m.get("responsibility", ""),
            "deps": [],
        }
        layer_map[name] = {"deps": []}

    machine_yaml = f"modules: {list(module_map.keys())}\n"
    machine_yaml += f"layers: {list(layer_map.keys())}\n"
    machine_yaml += f"enforce: {list(global_rules.keys())}\n"

    # Human-readable overview
    overview = intent.get("description", "No description provided.")

    module_details = []
    for m in modules:
        name = m.get("name", "?")
        resp = m.get("responsibility", "?")
        mod_path = m.get("path", "?")
        mod_lines = [
            f"### {name}",
            f"- **Path:** `{mod_path}`",
            f"- **Responsibility:** {resp}",
            f"- **Error strategy:** {m.get('error_strategy', 'not declared')}",
            f"- **Logging:** {m.get('logging', 'not declared')}",
            f"- **Testing:** {m.get('testing', 'not declared')}",
        ]
        module_details.append("\n".join(mod_lines))

    dep_details = []
    for key, val in global_rules.items():
        dep_details.append(f"- **{key}:** {val}")

    arch_path = plan_dir / ARCHITECTURE_FILE
    content = ARCHITECTURE_TEMPLATE.format(
        overview=overview,
        module_details="\n\n".join(module_details) if module_details else "No modules declared.",
        dependency_details="\n".join(dep_details) if dep_details else "No global rules declared.",
    )
    # Inject machine frontmatter as YAML block
    content = f"---\n{machine_yaml}---\n\n" + content.split("---", 2)[-1].strip()

    arch_path.write_text(content)
    return str(arch_path)


def load_architecture(path: str) -> dict | None:
    """Parse ARCHITECTURE.md frontmatter into a dict."""
    arch_file = Path(path) / PLANNING_DIR / ARCHITECTURE_FILE
    if not arch_file.exists():
        return None
    content = arch_file.read_text()

    # Extract YAML frontmatter (between --- markers)
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return None

    yaml_block = match.group(1)
    result = {}
    for line in yaml_block.strip().split("\n"):
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            value = [v.strip().strip("'\"") for v in value.strip("[]").split(",") if v.strip()]
        result[key] = value
    return result


# ── Project Plan ──

PLAN_TEMPLATE = """---
# Machine-readable project plan
# Phases and tasks that CodeGuards tools can validate and check off
phases: []
---

# Project Plan

{plan_body}

---

## Task Progress

{tasks_body}
"""

PHASE_TEMPLATE = """
## Phase {id}: {goal}

**Status:** {status}  
**Est. effort:** {effort}

{description}

| Task | File/Scope | Status |
|------|-----------|--------|
{tasks_table}

{tasks_detail}
"""


def create_plan(path: str, intent: dict, phases: list[dict] | None = None) -> str:
    """Create or update PROJECT_PLAN.md with phases and tasks."""
    plan_dir = Path(path) / PLANNING_DIR
    plan_dir.mkdir(parents=True, exist_ok=True)

    if not phases:
        modules = intent.get("modules", [])
        # Auto-generate phases from declared modules
        phases = [{
            "id": "01",
            "goal": f"Implement {m.get('name', '?')} module",
            "status": "pending",
            "effort": "medium",
            "description": f"Build the {m.get('name', '?')} module: {m.get('responsibility', '?')}",
            "tasks": [
                {
                    "id": f"T{i+1}",
                    "description": f"Create {m.get('name', '?')} data structures",
                    "file": m.get('path', ''),
                    "checks": ["no_unwrap"],
                    "status": "pending",
                },
                {
                    "id": f"T{i+2}",
                    "description": f"Implement {m.get('name', '?')} business logic",
                    "file": m.get('path', ''),
                    "checks": ["file_length", "function_length"],
                    "status": "pending",
                },
                {
                    "id": f"T{i+3}",
                    "description": f"Write {m.get('name', '?')} tests",
                    "file": m.get('path', ''),
                    "checks": ["tracing_instrument"],
                    "status": "pending",
                },
            ]
        } for i, m in enumerate(modules)]

    plan_body = []
    tasks_body = []

    # Machine-readable frontmatter
    phase_list = [{"id": p["id"], "goal": p["goal"]} for p in phases]

    machine_yaml = f"phases: {phase_list}\n"

    for p in phases:
        task_rows = []
        task_details = []
        for t in p.get("tasks", []):
            status_mark = "[x]" if t.get("status") == "completed" else "[ ]"
            task_rows.append(f"| {t['id']} | {t['description'][:50]} | {status_mark} |")
            task_details.append(f"### {t['id']}: {t['description']}")
            task_details.append(f"- **File:** `{t.get('file', '?')}`")
            task_details.append(f"- **Checks:** {', '.join(t.get('checks', []))}")
            task_details.append(f"- **Status:** {t.get('status', 'pending')}")
            task_details.append("")

        plan_body.append(PHASE_TEMPLATE.format(
            id=p["id"], goal=p["goal"], status=p.get("status", "pending"),
            effort=p.get("effort", "medium"),
            description=p.get("description", ""),
            tasks_table="\n".join(task_rows) if task_rows else "| - | No tasks | - |",
            tasks_detail="\n".join(task_details) if task_details else "No tasks defined.",
        ))

        all_tasks = []
        for p in phases:
            all_tasks.extend(p.get("tasks", []))
        completed = sum(1 for t in all_tasks if t.get("status") == "completed")
        total = len(all_tasks)
        tasks_body.append(f"**{completed}/{total} tasks completed**")

    content = PLAN_TEMPLATE.format(
        plan_body="\n".join(plan_body),
        tasks_body="\n".join(tasks_body),
    )
    content = f"---\n{machine_yaml}---\n\n" + content.split("---", 2)[-1].strip()

    plan_path = plan_dir / PLAN_FILE
    plan_path.write_text(content)
    return str(plan_path)


def update_task(path: str, task_id: str, status: str = "completed") -> bool:
    """Mark a task as completed/pending in PROJECT_PLAN.md."""
    plan_file = Path(path) / PLANNING_DIR / PLAN_FILE
    if not plan_file.exists():
        return False

    content = plan_file.read_text()
    # Update task status in the YAML frontmatter
    # This is basic — a proper YAML parser would be better but this works
    updated = content.replace(
        f'"id": "{task_id}", "status": "pending"',
        f'"id": "{task_id}", "status": "{status}"',
    )
    if updated == content:
        # Try another format
        updated = content.replace(
            f"'id': '{task_id}', 'status': 'pending'",
            f"'id': '{task_id}', 'status': '{status}'",
        )
    if updated == content:
        return False

    plan_file.write_text(updated)
    return True


def get_pending_tasks(path: str) -> list[dict]:
    """Get all pending tasks from PROJECT_PLAN.md."""
    plan_file = Path(path) / PLANNING_DIR / PLAN_FILE
    if not plan_file.exists():
        return []

    content = plan_file.read_text()
    pending = []
    for match in re.finditer(r"\{[^}]+\}", content):
        block = match.group()
        if '"status": "pending"' in block or "'status': 'pending'" in block:
            task = {}
            id_m = re.search(r'"id":\s*"(\w+)"', block)
            desc_m = re.search(r'"description":\s*"([^"]+)"', block)
            if id_m:
                task["id"] = id_m.group(1)
            if desc_m:
                task["description"] = desc_m.group(1)
            if task:
                pending.append(task)
    return pending
