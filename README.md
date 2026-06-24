# CodeGuards

**Code governance as an MCP server.** Any AI agent (Claude Code, Hermes, Codex, Cursor, etc.) connects to it and enforces code quality rules — without duplicating test crates in every project.

## How it works

```
AI agent writes code → calls check_project() → gets violations back → fixes them
```

The server auto-detects what languages your project uses (Rust, Python, JS, etc.) and runs the matching guards. Generic guards run on everything.

## Quick start

```bash
# Install
pip install mcp pyyaml

# Run (stdio mode — for local MCP clients)
python server.py

# Or run as HTTP server (for remote agents)
python server.py --port 8000
```

## Register with Hermes

```bash
hermes mcp add codeguards --command "python C:/Users/Sly/codeguards-mcp/server.py"
```

## Register with Claude Code

```bash
claude mcp add codeguards --command "python /path/to/codeguards-mcp/server.py"
```

## Per-project config

Place a `.codeguards.yaml` in your project root to customize rules:

```yaml
guards:
  file_length:
    max_prod: 300    # Your project allows longer files
  forbidden_phrases:
    patterns:
      - { pattern: "\\bTODO\\b", message: "link to an issue" }
```

If no `.codeguards.yaml` is found, sensible defaults apply.

## Available guards

### Generic (all languages)

| Guard | What it checks | Default |
|---|---|---|
| `file_length` | Production files ≤200 lines, test ≤500 | configurable |
| `function_length` | Functions ≤50 lines | configurable |
| `forbidden_phrases` | No "for now", "temporary", "should", "clean", etc. | configurable |
| `credentials` | No API keys, tokens, or secrets in source | configurable |
| `action_items` | TODO/FIXME/HACK must link to an issue (#123) | configurable |
| `glob_imports` | No `use foo::*` or `from bar import *` | configurable |

### Language plugins

| Guard | Languages | What it checks |
|---|---|---|
| `rust::no_unwrap` | Rust | No `.unwrap()`/`.expect()` in library code |
| `rust::tracing_instrument` | Rust | Public async functions need `#[tracing::instrument]` |

## Adding a plugin

Drop a `.py` file in the `plugins/` directory:

```python
def register(plugin_system):
    plugin_system.register_guard(
        name="my_check",
        check_fn=my_check_function,
        languages=["python"],
        description="Your description here",
    )
```

The check function receives `(path: Path, content: str, config: dict)` and returns a list of violation dicts.
