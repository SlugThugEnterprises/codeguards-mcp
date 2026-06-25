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
import os
import sys
from pathlib import Path

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


def create_app(registry: GuardRegistry):
    """Create an MCP server application."""
    server = Server("codeguards")

    # Store registry on server instance
    server._guard_registry = registry

    @server.list_tools()
    async def list_tools():
        tools = [
            Tool(
                name="check_project",
                description="Run all applicable code guards against a project directory",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the project root",
                        },
                    },
                    "required": ["path"],
                },
            ),
            Tool(
                name="check_file",
                description="Run all applicable checks on a single file",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the file to check",
                        },
                        "project_root": {
                            "type": "string",
                            "description": "Project root (for config detection)",
                        },
                    },
                    "required": ["path"],
                },
            ),
            Tool(
                name="detect_languages",
                description="Detect what languages a project uses",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the project root",
                        },
                    },
                    "required": ["path"],
                },
            ),
            Tool(
                name="list_guards",
                description="List all available guard checks and which languages they apply to",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
        ]
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        if name == "check_project":
            path = arguments["path"]
            config = load_config(path)
            languages = detect_languages(path)
            violations = run_checks(path, config, registry, languages)
            return [TextContent(
                type="text",
                text=format_report(path, violations, languages, config),
            )]

        elif name == "check_file":
            file_path = arguments["path"]
            project_root = arguments.get("project_root", os.path.dirname(file_path))
            config = load_config(project_root)
            languages = detect_languages(project_root)

            # Read the file
            try:
                content = Path(file_path).read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                return [TextContent(type="text", text=f"Error reading {file_path}: {e}")]

            # Run all generic guards
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

            # Run plugin guards that match
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

            return [TextContent(
                type="text",
                text=format_report(file_path, violations, languages, config),
            )]

        elif name == "detect_languages":
            path = arguments["path"]
            languages = detect_languages(path)
            return [TextContent(
                type="text",
                text=json.dumps({"languages": languages, "detected_at": path}, indent=2),
            )]

        elif name == "list_guards":
            guards_info = []
            # Generic guards
            guards_info.append({
                "name": "file_length",
                "languages": "all",
                "description": "Files must not exceed max line count",
            })
            guards_info.append({
                "name": "function_length",
                "languages": "all",
                "description": "Functions must not exceed max line count",
            })
            guards_info.append({
                "name": "forbidden_phrases",
                "languages": "all",
                "description": "No weasel words or vague language",
            })
            guards_info.append({
                "name": "credentials",
                "languages": "all",
                "description": "No API keys or secrets in source",
            })
            guards_info.append({
                "name": "action_items",
                "languages": "all",
                "description": "TODO/FIXME must link to an issue",
            })
            guards_info.append({
                "name": "glob_imports",
                "languages": "all",
                "description": "No wildcard imports",
            })
            # Plugin guards
            for g in registry.guards:
                guards_info.append({
                    "name": g["name"],
                    "languages": g.get("languages", []),
                    "description": g.get("description", ""),
                })
            return [TextContent(
                type="text",
                text=json.dumps({"guards": guards_info}, indent=2),
            )]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    return server


def format_report(path: str, violations: list[dict], languages: list[str], config: dict) -> str:
    """Format violations into a readable report."""
    lines = []
    lines.append(f"CodeGuards Report — {path}")
    lines.append(f"Languages detected: {', '.join(languages) if languages else 'unknown'}")
    lines.append("")

    if not violations:
        lines.append("✓ All guards passed — no violations found.")
        return "\n".join(lines)

    # Group by guard
    by_guard: dict[str, list[dict]] = {}
    for v in violations:
        guard = v.get("guard", "unknown")
        by_guard.setdefault(guard, []).append(v)

    total = len(violations)
    lines.append(f"✗ {total} violation(s) found:")
    lines.append("")

    for guard_name, items in sorted(by_guard.items()):
        lines.append(f"  [{guard_name}] — {len(items)} violation(s)")
        for v in items[:10]:  # show first 10 per guard
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

    # Load plugins
    registry = load_plugins()

    if not HAS_MCP:
        print("Error: 'mcp' package not installed. Run: pip install mcp")
        sys.exit(1)

    if args.port:
        # HTTP SSE mode
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

        print(f"CodeGuards MCP server listening on port {args.port}")
        uvicorn.run(starlette_app, host="0.0.0.0", port=args.port)
    else:
        # stdio mode
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
