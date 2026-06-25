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
    path = arguments["path"]
    config = load_config(path)
    languages = detect_languages(path)
    violations = run_checks(path, config, registry, languages)
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


# Dispatch table — adding a tool = one function + one dict entry
TOOL_HANDLERS: dict[str, Callable] = {
    "check_project": handle_check_project,
    "check_file": handle_check_file,
    "detect_languages": handle_detect_languages,
    "list_guards": handle_list_guards,
    "declare_intent": handle_declare_intent,
    "save_baseline": handle_save_baseline,
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
