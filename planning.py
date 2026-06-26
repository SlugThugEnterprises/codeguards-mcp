"""Project planning — structured architecture + phased task plans.

Creates .planning/ARCHITECTURE.md and .planning/PROJECT_PLAN.md
with YAML frontmatter that CodeGuards tools can enforce against.
"""

import re
from pathlib import Path
from string import Template

import yaml


PLANNING_DIR = ".planning"
ARCHITECTURE_FILE = "ARCHITECTURE.md"
PLAN_FILE = "PROJECT_PLAN.md"


# ── Architecture ──

ARCHITECTURE_TEMPLATE = Template("""## Architecture Overview

$overview

## Modules

$module_details

## Dependencies

$dependency_details

## Enforcement Rules

- Modules must not import from modules outside their declared dependency list
- Each module's directory must be under the declared path
- Code in each module must pass its specific enforce checks
""")


def _split_frontmatter(content: str) -> tuple[dict, str]:
    """Split a document into (frontmatter_dict, body). Frontmatter is the YAML
    block between the first pair of ``---`` markers. Returns ({}, content) if
    no frontmatter present."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", content, re.DOTALL)
    if not match:
        return {}, content
    fm_raw = match.group(1)
    try:
        fm = yaml.safe_load(fm_raw) or {}
    except yaml.YAMLError:
        fm = {}
    body = content[match.end():]
    return (fm, body)


def create_architecture(path: str, intent: dict) -> str:
    """Create or update ARCHITECTURE.md from declared intent."""
    plan_dir = Path(path) / PLANNING_DIR
    plan_dir.mkdir(parents=True, exist_ok=True)

    modules = intent.get("modules", [])
    global_rules = intent.get("global", {})

    # Build machine-readable frontmatter via proper YAML.
    allowed_deps: dict[str, list[str]] = {}
    for m in modules:
        name = m.get("name", "?")
        deps = m.get("dependencies", []) or []
        if isinstance(deps, str):
            deps = [d.strip() for d in deps.split(",") if d.strip()]
        allowed_deps[name] = deps

    fm = {
        "modules": [m.get("name", "?") for m in modules],
        "layers": [m.get("name", "?") for m in modules],
        "allowed_dependencies": allowed_deps,
        "enforce": list(global_rules.keys()),
    }

    # Build human-readable body via string substitution.
    overview = intent.get("description", "No description provided.")
    module_details = []
    for m in modules:
        module_details.append(
            f"### {m.get('name', '?')}\n"
            f"- **Path:** `{m.get('path', '?')}`\n"
            f"- **Responsibility:** {m.get('responsibility', '?')}\n"
            f"- **Error strategy:** {m.get('error_strategy', 'not declared')}\n"
            f"- **Logging:** {m.get('logging', 'not declared')}\n"
            f"- **Testing:** {m.get('testing', 'not declared')}"
        )
    dep_details = [f"- **{k}:** {v}" for k, v in global_rules.items()]

    body = ARCHITECTURE_TEMPLATE.substitute(
        overview=overview,
        module_details="\n\n".join(module_details) if module_details
                       else "No modules declared.",
        dependency_details="\n".join(dep_details) if dep_details
                           else "No global rules declared.",
    )

    arch_path = plan_dir / ARCHITECTURE_FILE
    with open(arch_path, "w") as f:
        f.write("---\n")
        yaml.safe_dump(fm, f, default_flow_style=False, sort_keys=False,
                       allow_unicode=True)
        f.write("---\n\n")
        f.write(body)
    return str(arch_path)


def load_architecture(path: str) -> dict | None:
    """Parse ARCHITECTURE.md frontmatter into a dict."""
    arch_file = Path(path) / PLANNING_DIR / ARCHITECTURE_FILE
    if not arch_file.exists():
        return None
    content = arch_file.read_text()
    fm, _ = _split_frontmatter(content)
    return fm or None


# ── Project Plan ──

PLAN_BODY_TEMPLATE = Template("""# Project Plan

$plan_body

---

## Task Progress

$completed_count/$total_count tasks completed
""")


def create_plan(path: str, intent: dict, phases: list[dict] | None = None) -> str:
    """Create or update PROJECT_PLAN.md with phases and tasks."""
    plan_dir = Path(path) / PLANNING_DIR
    plan_dir.mkdir(parents=True, exist_ok=True)

    if phases is None:
        modules = intent.get("modules", [])
        phases = []
        for i, m in enumerate(modules):
            name = m.get("name", "?")
            mod_path = m.get("path", "")
            phases.append({
                "id": f"{i + 1:02d}",
                "goal": f"Implement {name} module",
                "status": "pending",
                "effort": "medium",
                "description": (
                    f"Build the {name} module: "
                    f"{m.get('responsibility', '?')}"
                ),
                "tasks": [
                    {
                        "id": f"T{i + 1}.1",
                        "description": f"Create {name} data structures",
                        "file": mod_path,
                        "checks": ["no_unwrap"],
                        "status": "pending",
                    },
                    {
                        "id": f"T{i + 1}.2",
                        "description": f"Implement {name} business logic",
                        "file": mod_path,
                        "checks": ["file_length", "function_length"],
                        "status": "pending",
                    },
                    {
                        "id": f"T{i + 1}.3",
                        "description": f"Write {name} tests",
                        "file": mod_path,
                        "checks": ["tracing_instrument"],
                        "status": "pending",
                    },
                ],
            })

    # Build phase markdown.
    phase_blocks: list[str] = []
    all_tasks: list[dict] = []
    for p in phases:
        tasks = p.get("tasks", [])
        all_tasks.extend(tasks)
        task_rows = []
        task_details = []
        for t in tasks:
            mark = "[x]" if t.get("status") == "completed" else "[ ]"
            task_rows.append(
                f"| {t['id']} | {t['description'][:50]} | {mark} |"
            )
            task_details.append(
                f"### {t['id']}: {t['description']}\n"
                f"- **File:** `{t.get('file', '?')}`\n"
                f"- **Checks:** {', '.join(t.get('checks', []))}\n"
                f"- **Status:** {t.get('status', 'pending')}"
            )
        phase_blocks.append(
            f"## Phase {p['id']}: {p['goal']}\n\n"
            f"**Status:** {p.get('status', 'pending')}  \n"
            f"**Est. effort:** {p.get('effort', 'medium')}\n\n"
            f"{p.get('description', '')}\n\n"
            f"| Task | File/Scope | Status |\n"
            f"|------|-----------|--------|\n"
            + ("\n".join(task_rows) if task_rows else "| - | No tasks | - |")
            + "\n\n"
            + ("\n\n".join(task_details) if task_details
               else "No tasks defined.")
        )

    plan_body = "\n\n".join(phase_blocks) if phase_blocks else "No phases."
    completed = sum(1 for t in all_tasks if t.get("status") == "completed")
    total = len(all_tasks)
    body = PLAN_BODY_TEMPLATE.substitute(
        plan_body=plan_body,
        completed_count=completed,
        total_count=total,
    )

    # Build machine-readable YAML frontmatter (no string-replace trickery).
    fm_phases = [
        {
            "id": p["id"],
            "goal": p["goal"],
            "status": p.get("status", "pending"),
            "tasks": [
                {"id": t["id"], "status": t.get("status", "pending"),
                 "description": t.get("description", "")}
                for t in p.get("tasks", [])
            ],
        }
        for p in phases
    ]

    plan_path = plan_dir / PLAN_FILE
    with open(plan_path, "w") as f:
        f.write("---\n")
        yaml.safe_dump({"phases": fm_phases}, f, default_flow_style=False,
                       sort_keys=False, allow_unicode=True)
        f.write("---\n\n")
        f.write(body)
    return str(plan_path)


def update_task(path: str, task_id: str, status: str = "completed") -> bool:
    """Mark a task as completed/pending by editing YAML frontmatter + body.

    Reads the plan, parses YAML safely, mutates the in-memory dict, then
    rewrites the file using YAML serialization. No string-replace trickery.
    """
    plan_file = Path(path) / PLANNING_DIR / PLAN_FILE
    if not plan_file.exists():
        return False
    content = plan_file.read_text()

    fm, body = _split_frontmatter(content)
    if not fm or "phases" not in fm:
        return False

    updated = False
    for phase in fm.get("phases", []) or []:
        for task in phase.get("tasks", []) or []:
            if task.get("id") == task_id:
                task["status"] = status
                updated = True

    if not updated:
        return False

    new_content = (
        "---\n"
        + yaml.safe_dump({"phases": fm["phases"]},
                         default_flow_style=False, sort_keys=False,
                         allow_unicode=True)
        + "---\n\n"
        + body
    )
    plan_file.write_text(new_content)
    return True


def get_pending_tasks(path: str) -> list[dict]:
    """Get all pending tasks from PROJECT_PLAN.md by parsing YAML safely."""
    plan_file = Path(path) / PLANNING_DIR / PLAN_FILE
    if not plan_file.exists():
        return []

    content = plan_file.read_text()
    fm, _ = _split_frontmatter(content)
    if not fm:
        return []

    pending: list[dict] = []
    for phase in fm.get("phases", []) or []:
        for task in phase.get("tasks", []) or []:
            if task.get("status") == "pending":
                pending.append({
                    "id": task.get("id", "?"),
                    "description": task.get("description", "?"),
                })
    return pending
