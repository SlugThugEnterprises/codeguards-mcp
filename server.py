#!/usr/bin/env python3
"""CodeGuards MCP Server — code governance tools for any AI agent.

Usage:
    python server.py              # stdio mode (for local MCP clients)
    python server.py --port 8000  # HTTP SSE mode (for remote clients)

Register with Hermes:
    hermes mcp add codeguards --command "python /path/to/server.py"
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Callable

from config import load_config
from detectors import detect_languages
from guards import GuardRegistry, load_plugins, run_checks

try:
    from mcp.server import Server, NotificationOptions
    from mcp.server.models import InitializationOptions
    from mcp.types import Tool, TextContent
    import mcp.server.stdio
    HAS_MCP = True
except ImportError:
    HAS_MCP = False


# ──────────────────────────────────────────────
# Tool handlers — one async function per tool
# Each can be imported and tested independently
# ──────────────────────────────────────────────

async def handle_check_project(registry: GuardRegistry, arguments: dict) -> list[TextContent]:
    from intent import has_intent
    path = arguments["path"]
    if not has_intent(path):
        return [TextContent(type="text", text=(
            "I don't know what you're building yet.\n\n"
            "Before I can check code, I need to understand the goal. "
            "Run `probe` first to help me ask the right questions — "
            "then `declare_intent` to commit to a direction.\n\n"
            "Writing code without understanding what you need is "
            "how 129 files of wrong architecture happen."
        ))]
    config = load_config(path)
    languages = detect_languages(path)
    violations = run_checks(path, config, registry, languages)

    # Cross-reference against architecture spec
    from planning import load_architecture
    arch = load_architecture(path)
    if arch:
        modules = arch.get("modules", [])
        if modules and isinstance(modules, list):
            violations.append({
                "file": str(Path(path) / ".planning" / "ARCHITECTURE.md"),
                "line": 1,
                "guard": "architecture",
                "principle": "Architecture",
                "message": f"Project scope: {len(modules)} module(s): {', '.join(modules)}",
            })

    return [TextContent(type="text", text=format_report(path, violations, languages, config))]


async def handle_check_file(registry: GuardRegistry, arguments: dict) -> list[TextContent]:
    file_path = arguments["path"]
    project_root = arguments.get("project_root", os.path.dirname(file_path))
    config = load_config(project_root)
    languages = detect_languages(project_root)

    try:
        content = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return [TextContent(type="text", text=f"Error reading {file_path}: {e}")]

    from guards.generic import ALL_GENERIC_CHECKS
    violations = []
    for guard_name, check_fn in ALL_GENERIC_CHECKS.items():
        guard_cfg = config.get("guards", {}).get(guard_name, {})
        try:
            violations.extend(check_fn(Path(file_path), content, guard_cfg))
        except Exception as e:
            violations.append({
                "file": file_path, "line": 0,
                "message": f"Guard {guard_name} error: {e}",
                "guard": "error",
            })

    for guard in registry.guards:
        guard_langs = guard.get("languages", [])
        if guard_langs and not any(l in languages for l in guard_langs):
            continue
        try:
            violations.extend(guard["check_fn"](Path(file_path), content, {}))
        except Exception as e:
            violations.append({
                "file": file_path, "line": 0,
                "message": f"Guard {guard['name']} error: {e}",
                "guard": "error",
            })

    return [TextContent(type="text", text=format_report(file_path, violations, languages, config))]


async def handle_detect_languages(registry: GuardRegistry, arguments: dict) -> list[TextContent]:
    path = arguments["path"]
    languages = detect_languages(path)
    return [TextContent(type="text", text=json.dumps({"languages": languages, "detected_at": path}, indent=2))]


async def handle_list_guards(registry: GuardRegistry, arguments: dict) -> list[TextContent]:
    guard_descriptions = [
        ("file_length", "Files must not exceed max line count"),
        ("function_length", "Functions must not exceed max line count"),
        ("god_file", "Too many public items or imports — SRP violation"),
        ("forbidden_phrases", "No weasel words or vague language"),
        ("glob_imports", "No wildcard imports"),
        ("debug_statements", "No println/console.log in production code"),
        ("commented_code", "No dead code in comments"),
        ("magic_numbers", "No unexplained numeric literals"),
        ("duplicated_code", "No copy-paste code blocks"),
        ("unsafe_patterns", "No eval/exec/unsafe blocks"),
        ("deep_nesting", "Max 3 nesting levels"),
        ("parameter_count", "Max 5 function parameters"),
        ("credentials", "No API keys or secrets in source"),
        ("action_items", "TODO/FIXME must link to an issue"),
        ("hardcoded_values", "No raw URLs/IPs/ports as literals"),
        ("missing_docs", "Public items need docstrings"),
        ("swallowed_errors", "No empty catch/except blocks"),
        ("no_stubs", "No todo!/unimplemented! in production"),
        ("missing_tests", "Source files must have matching test files"),
    ]
    guards_info = [{"name": n, "languages": "all", "description": d} for n, d in guard_descriptions]
    for g in registry.guards:
        guards_info.append({
            "name": g["name"],
            "languages": g.get("languages", []),
            "description": g.get("description", ""),
        })
    return [TextContent(type="text", text=json.dumps({"guards": guards_info}, indent=2))]


async def handle_declare_intent(registry: GuardRegistry, arguments: dict) -> list[TextContent]:
    from intent import save_intent, get_intent_summary
    project_path = arguments["path"]
    intent_data = {
        "modules": arguments.get("modules", []),
        "global": arguments.get("global", {}),
    }
    save_path = save_intent(project_path, intent_data)
    summary = get_intent_summary(intent_data)
    return [TextContent(type="text", text=(
        f"Architectural intent saved to {save_path}\n\n"
        f"{summary}\n\n"
        "Guards will now enforce code quality against this declaration. "
        "If code violates your declared intent, violations will include "
        "the specific rule you declared."
    ))]


async def handle_save_baseline(registry: GuardRegistry, arguments: dict) -> list[TextContent]:
    from guards.structural import save_structural_baseline
    project_path = arguments["path"]
    baseline = save_structural_baseline(project_path)
    return [TextContent(type="text", text=(
        f"Structural baseline saved with {len(baseline)} files. "
        f"Future checks will detect growth drift from this snapshot."
    ))]


async def handle_probe(registry: GuardRegistry, arguments: dict) -> list[TextContent]:
    """Help the AI figure out the right questions before writing code."""
    description = arguments.get("description", "")
    competitor = arguments.get("competitor", "")

    questions = []
    questions.append("# Probe: What to understand before writing a line of code\n")

    if competitor:
        questions.append(f"## Research: {competitor}")
        questions.append(
            f"You mentioned something like {competitor}. I don't know that product inside out — "
            f"but here's what I need to understand from you before I can help design something:\n"
        )

    questions.append("## 1. The Real Goal")
    questions.append("- What problem are you trying to solve? (describe it without mentioning technology)")
    questions.append("- Who has this problem? Just you? A team? Customers?")
    questions.append("- Is this for personal use, a product you'll sell, or just to see if it can be done?")

    questions.append("")
    questions.append("## 2. What Exists vs What's Different")
    questions.append("- What do you use now, and what does it do wrong?")
    questions.append("- What's the thing that makes your idea different?")
    questions.append("- If you could change ONE thing about existing tools, what would it be?")

    questions.append("")
    questions.append("## 3. Scope")
    questions.append("- Are you prototyping (prove it works) or building for production (ship it)?")
    questions.append("- How much time do you want to spend on this?")
    questions.append("- What does 'done' look like — when would you call this a success?")

    questions.append("")
    questions.append("## 4. Preferences (no right answers)")
    questions.append("- Do you prefer tools that are established and boring, or new and cutting edge?")
    questions.append("- Do you care about how the code looks, or just that it works?")
    questions.append("- Do you want something you can maintain yourself, or set-and-forget?")
    questions.append("- Is there a language or technology you specifically want to use — or avoid?")

    if competitor:
        questions.append("")
        questions.append("## Suggested next step")
        questions.append(
            f"I can look up what {competitor} actually offers and compare options "
            f"once you answer a few of these. Want me to research it?"
        )

    return [TextContent(type="text", text="\n".join(questions))]


async def handle_plan(registry: GuardRegistry, arguments: dict) -> list[TextContent]:
    """Generate a structured project plan from declared intent."""
    from intent import load_intent
    from planning import create_architecture, create_plan, get_pending_tasks
    path = arguments["path"]

    intent = load_intent(path)
    if not intent:
        return [TextContent(type="text", text=(
            "No architectural intent declared. Run `probe` first to help me understand "
            "what you need, then `declare_intent` to commit to a direction."
        ))]

    # Create architecture doc
    arch_path = create_architecture(path, intent)

    # Create project plan
    plan_path = create_plan(path, intent)

    pending = get_pending_tasks(path)
    pending_msg = f"\n{pending[0]['id']}: {pending[0]['description']}\n" if pending else ""

    return [TextContent(type="text", text=(
        f"Planning created:\n"
        f"- {arch_path}\n"
        f"- {plan_path}\n"
        f"\nNext task: {pending_msg}"
    ))]


async def handle_update_task(registry: GuardRegistry, arguments: dict) -> list[TextContent]:
    """Mark a task complete or update its status."""
    from planning import update_task, get_pending_tasks
    path = arguments["path"]
    task_id = arguments["task_id"]
    status = arguments.get("status", "completed")

    if update_task(path, task_id, status):
        pending = get_pending_tasks(path)
        msg = f"Task {task_id} marked as {status}."
        if pending:
            msg += f"\nNext pending task: {pending[0]['id']} — {pending[0]['description']}"
        else:
            msg += "\nAll tasks complete. Run `plan` to generate the next phase."
        return [TextContent(type="text", text=msg)]
    return [TextContent(type="text", text=f"Task {task_id} not found in plan.")]


async def handle_list_tasks(registry: GuardRegistry, arguments: dict) -> list[TextContent]:
    """Show pending tasks."""
    from planning import get_pending_tasks
    path = arguments["path"]
    pending = get_pending_tasks(path)
    if not pending:
        return [TextContent(type="text", text="No pending tasks. All caught up!")]
    lines = [f"{len(pending)} pending task(s):\n"]
    for t in pending:
        lines.append(f"  [ ] {t.get('id', '?')}: {t.get('description', '?')}")
    return [TextContent(type="text", text="\n".join(lines))]


# Dispatch table — adding a tool = one function + one dict entry
TOOL_HANDLERS: dict[str, Callable] = {
    "check_project": handle_check_project,
    "check_file": handle_check_file,
    "detect_languages": handle_detect_languages,
    "list_guards": handle_list_guards,
    "declare_intent": handle_declare_intent,
    "save_baseline": handle_save_baseline,
    "probe": handle_probe,
    "plan": handle_plan,
    "update_task": handle_update_task,
    "list_tasks": handle_list_tasks,
}

TOOL_DEFINITIONS: list[Tool] = [
    Tool(
        name="check_project",
        description="Run all applicable code guards against a project directory",
        inputSchema={"type": "object", "properties": {
            "path": {"type": "string", "description": "Path to the project root"},
        }, "required": ["path"]},
    ),
    Tool(
        name="check_file",
        description="Run all applicable checks on a single file",
        inputSchema={"type": "object", "properties": {
            "path": {"type": "string", "description": "Path to the file to check"},
            "project_root": {"type": "string", "description": "Project root (for config detection)"},
        }, "required": ["path"]},
    ),
    Tool(
        name="detect_languages",
        description="Detect what languages a project uses",
        inputSchema={"type": "object", "properties": {
            "path": {"type": "string", "description": "Path to the project root"},
        }, "required": ["path"]},
    ),
    Tool(
        name="list_guards",
        description="List all available guard checks and which languages they apply to",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="declare_intent",
        description="Declare architectural intent before writing code. Records module boundaries, error strategy, logging, testing, and tracing plans. Guards enforce against this declaration.",
        inputSchema={"type": "object", "properties": {
            "path": {"type": "string", "description": "Path to the project root"},
            "modules": {"type": "array", "description": "Module definitions",
                "items": {"type": "object", "properties": {
                    "name": {"type": "string"},
                    "path": {"type": "string"},
                    "responsibility": {"type": "string"},
                    "error_strategy": {"type": "string"},
                    "logging": {"type": "string"},
                    "testing": {"type": "string"},
                }},
            },
            "global": {"type": "object", "description": "Global rules",
                "properties": {
                    "error_handling": {"type": "string"},
                    "logging": {"type": "string"},
                    "tracing": {"type": "string"},
                    "testing": {"type": "string"},
                    "architecture": {"type": "string"},
                },
            },
        }, "required": ["path", "modules", "global"]},
    ),
    Tool(
        name="save_baseline",
        description="Snapshot current structural health as baseline for growth drift detection",
        inputSchema={"type": "object", "properties": {
            "path": {"type": "string", "description": "Path to the project root"},
        }, "required": ["path"]},
    ),
    Tool(
        name="probe",
        description="Before writing code: ask probing questions to understand what the user actually needs. No tech questions — focus on goal, problem, scope, and preferences. Call this before declare_intent when starting something new.",
        inputSchema={"type": "object", "properties": {
            "description": {"type": "string", "description": "What the user wants to build (plain language)"},
            "competitor": {"type": "string", "description": "Optional: a product or tool the user mentioned as reference"},
        }, "required": ["description"]},
    ),
    Tool(
        name="plan",
        description="Generate structured project plan from declared intent. Creates .planning/ARCHITECTURE.md and .planning/PROJECT_PLAN.md with machine-enforceable YAML frontmatter.",
        inputSchema={"type": "object", "properties": {
            "path": {"type": "string", "description": "Project root path"},
        }, "required": ["path"]},
    ),
    Tool(
        name="update_task",
        description="Mark a task as completed or update its status.",
        inputSchema={"type": "object", "properties": {
            "path": {"type": "string", "description": "Project root path"},
            "task_id": {"type": "string", "description": "Task ID (e.g. T1, T2)"},
            "status": {"type": "string", "description": "Status: completed, pending, in_progress"},
        }, "required": ["path", "task_id"]},
    ),
    Tool(
        name="list_tasks",
        description="Show pending tasks from the project plan.",
        inputSchema={"type": "object", "properties": {
            "path": {"type": "string", "description": "Project root path"},
        }, "required": ["path"]},
    ),
]


def create_app(registry: GuardRegistry):
    """Create an MCP server application with dispatch table."""
    server = Server("codeguards")
    server._guard_registry = registry

    @server.list_tools()
    async def list_tools():
        return TOOL_DEFINITIONS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        handler = TOOL_HANDLERS.get(name)
        if not handler:
            return [TextContent(type="text", text=f"Unknown tool: {name}. Available: {', '.join(sorted(TOOL_HANDLERS))}")]
        return await handler(registry, arguments)

    return server


def format_report(path: str, violations: list[dict], languages: list[str], config: dict) -> str:
    """Format violations into a readable report."""
    lines = []
    lines.append(f"CodeGuards Report — {path}")
    lines.append(f"Languages detected: {', '.join(languages) if languages else 'unknown'}")
    lines.append("")

    if not violations:
        lines.append("All guards passed.")
        return "\n".join(lines)

    by_guard: dict[str, list[dict]] = {}
    for v in violations:
        guard = v.get("guard", "unknown")
        by_guard.setdefault(guard, []).append(v)

    total = len(violations)
    lines.append(f"{total} violation(s) found:")
    lines.append("")

    for guard_name, items in sorted(by_guard.items()):
        lines.append(f"  [{guard_name}] {len(items)} violation(s)")
        for v in items[:10]:
            file = v.get("file", "?")
            line = v.get("line", 0)
            msg = v.get("message", "")
            lines.append(f"    {file}:{line}  {msg}")
        if len(items) > 10:
            lines.append(f"    ... and {len(items) - 10} more")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="CodeGuards MCP Server")
    parser.add_argument("--port", type=int, default=0, help="HTTP SSE port (0 = stdio mode)")
    args = parser.parse_args()

    log = logging.getLogger("codeguards")
    registry = load_plugins()

    if not HAS_MCP:
        log.error("'mcp' package not installed. Run: pip install mcp")
        sys.exit(1)

    if args.port:
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Mount, Route
        import uvicorn

        app = create_app(registry)
        sse = SseServerTransport("/messages/")

        async def handle_sse(request):
            async with sse.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                await app.run(streams[0], streams[1], app.create_initialization_options())

        starlette_app = Starlette(
            routes=[
                Route("/sse", endpoint=handle_sse),
                Mount("/messages/", app=sse.handle_post_message),
            ]
        )
        log.info("CodeGuards MCP server listening on port %d", args.port)
        uvicorn.run(starlette_app, host="0.0.0.0", port=args.port)
    else:
        app = create_app(registry)

        async def run_stdio():
            async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
                await app.run(
                    read_stream,
                    write_stream,
                    app.create_initialization_options(),
                )

        import asyncio
        asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
