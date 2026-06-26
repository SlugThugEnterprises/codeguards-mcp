# CodeGuards

**Code governance for AI coding agents.** An MCP server that enforces code
quality rules against the architecture your project declared — so your AI
*plans before it builds*.

CodeGuards is the front-half that asks what you're building and the back-half
that holds your code to that decision.

---

## How it works

**The enforce-order is enforced.** This is the part that matters:

```
User describes what to build
    ↓
1. probe                ←  AI asks plain-English questions about goal, scope, preferences
                          (or about a competitor the user mentioned)
2. declare_intent       ←  AI commits to architecture (modules, dependencies, error/log/test strategies)
                          → writes .codeguards/intent.json
3. plan                 ←  AI materializes architecture + phased tasks
                          → writes .planning/ARCHITECTURE.md     (machine-enforceable YAML)
                          → writes .planning/PROJECT_PLAN.md     (phased tasks, each tagged with checks)
4. update_task          ←  AI marks tasks complete as it builds
5. check_project        ←  AI runs all guards against the whole project
```

`check_project` **refuses to run without intent.json present.** This prevents
the AI from drifting into "fix later" code without a stated direction. The
enforcement is server-side, not a polite suggestion.

### What the AI gets back

When `check_project` runs, every guard in the registry fires for every source
file. Each violation carries:

- **The rule that caught it** (e.g. `parameter_count`)
- **Where** (file:line)
- **Why** (e.g. "Function `add` has 10 parameters; max is 5")
- **A fix suggestion** drawn from `fixes.py` (e.g. "Extract the data dict into a properties class")
- **Intent cross-reference** when the rule maps to declared intent (e.g.
  `swallowed_errors` ↔ `error_handling` from `intent.json`)

### Validated end-to-end

Installed from GitHub onto a stranger's machine via OpenCode. Ran a full
audit on a Python + JS + HTML codebase with **zero language plugins matching
the project** — and generic heuristics still caught real issues, the AI
applied fixes from `fixes.py`, and `check_project` re-confirmed clean.

That is the platform guarantee: **generic layer works without plugin
coverage.** Plugins add depth, not the on-ramp.

---

## Install

```bash
pip install mcp pyyaml
```

That's it for stdio mode (the default — Claude Code, Hermes, OpenCode).

**For HTTP SSE mode (`--port`), you also need:**

```bash
pip install starlette uvicorn
```

These are only imported when `--port` is set; stdio users don't pay the cost.

---

## Run

The MCP server speaks stdio (default) or HTTP SSE (`--port`):

```bash
# stdio — for local MCP clients (Claude Code, Hermes, OpenCode, etc.)
python server.py

# SSE — for remote agents / HTTP-aware clients (needs starlette+uvicorn above)
python server.py --port 8000
# clients connect to http://<host>:8000/sse
```

---

## Verified MCP clients

| Client  | Mode  | Verified | Install |
|---------|-------|----------|---------|
| Claude Code | stdio | yes | `claude mcp add codeguards --command "python /path/to/server.py"` |
| Hermes      | stdio | yes | `hermes mcp add codeguards --command "python /path/to/server.py"` |
| OpenCode    | stdio | yes | registered via OpenCode's MCP config |

**Any stdio MCP client works.** The conversation above is generic MCP.
The friendship validation came from OpenCode specifically; Claude Code and
Hermes are listed in `server.py`'s docstring. Codex / Cursor are not
verified — drop me a note if you run it on either.

---

## Tools (10 total)

`server.py` exposes ten MCP tools. The pipeline above uses five; the rest
are observers / diagnostics.

| Tool | What it does |
|------|--------------|
| `probe` | Asks plain-English questions before code is written. Optionally accepts `competitor` to scaffold a comparison. |
| `declare_intent` | Writes `intent.json` (modules, deps, error/log/test strategies). Required before `check_project`. |
| `plan` | Writes `.planning/ARCHITECTURE.md` and `.planning/PROJECT_PLAN.md` with YAML frontmatter. Refuses without intent. |
| `update_task` | Marks tasks complete / in-progress / pending in `PROJECT_PLAN.md`. |
| `list_tasks` | Shows pending tasks. |
| `check_project` | Runs **all** enabled guards against the full project. Refuses without intent. |
| `check_file` | Runs enabled guards against a single file. |
| `detect_languages` | Lists languages detected in the project. |
| `list_guards` | Lists all available guards and the languages they apply to. |
| `save_baseline` | Snapshots current structural metrics for growth-drift detection. |

---

## What the planning artifacts look like

`declare_intent` + `plan` produce three files (per project):

| File | Owned by | Read by |
|------|----------|---------|
| `.codeguards/intent.json` | project, git-tracked | guards |
| `.planning/ARCHITECTURE.md` | project, git-tracked | `check_layer_enforcement` reads YAML frontmatter (`allowed_dependencies`) |
| `.planning/PROJECT_PLAN.md` | project, git-tracked | `update_task`, `list_tasks` read YAML frontmatter (`phases[].tasks[]`) |

The YAML frontmatter is the **machine-enforceable shape** of the
plan. The markdown body beneath it is the **human-readable** shape. They are
written together and stay in sync.

---

## Built-in guards

The `list_guards` tool reports **21 entries**: 18 generic + 1 project-level +
2 language plugins. There are also **5 structural guards** that fire as part
of `check_project` but aren't enumerated by `list_guards`. Generic layer is
what catches most things when no plugin matches — that's the friend-session
proof point.

### Generic (per-file, in `guards/generic.py`) — 18

| Guard | Catches |
|-------|---------|
| `file_length` | Production files over the configured line cap |
| `function_length` | Functions over the configured line cap |
| `god_file` | Too many public items / imports (SRP signal) |
| `forbidden_phrases` | Weasel words (`for now`, `temporary`, `should`, `clean`, …) |
| `glob_imports` | Wildcard imports (`use foo::*`, `from bar import *`) |
| `debug_statements` | `println!` / `console.log` / `print()` left in production |
| `commented_code` | Dead code blocks in comments |
| `magic_numbers` | Unexplained numeric literals |
| `duplicated_code` | Copy-paste code blocks |
| `unsafe_patterns` | `eval` / `exec` / `unsafe` blocks |
| `deep_nesting` | Nesting depth over the configured cap |
| `parameter_count` | Functions over the configured parameter cap |
| `credentials` | API keys / tokens / secrets in source |
| `action_items` | `TODO` / `FIXME` / `HACK` without an issue link |
| `hardcoded_values` | Raw URLs / IPs / ports as literals |
| `missing_docs` | Public items without docstrings |
| `swallowed_errors` | Empty `catch` / `except` blocks |
| `no_stubs` | `todo!` / `unimplemented!` macros in production |

### Structural (multi-file, in `guards/structural.py`) — 5

| Guard | Catches |
|-------|---------|
| `responsibility_clusters` | Files importing too widely — drift toward communication hubs |
| `fan_out` | A module with too many direct dependencies |
| `layer_enforcement` | Module imports outside the `allowed_dependencies` declared in `ARCHITECTURE.md` |
| `structural_health` | Composite score from baselines and growth-drift |
| `growth_drift` | (internal — driven by `save_baseline`) |

### Project-level (whole-project analysis) — 1

| Guard | Catches |
|-------|---------|
| `missing_tests` | Source files without matching test files (per-language test dirs) |

Runs once per `check_project` call (not per file) and is reported under the
same `missing_tests` name.

### Language plugins — 2 (Rust today; others are templates below)

| Guard | Languages | Catches |
|-------|-----------|---------|
| `no_unwrap` | Rust | `.unwrap()` / `.expect()` in library code |
| `tracing_instrument` | Rust | Public async fns missing `#[tracing::instrument]` |

---

## Configuration

Drop a `.codeguards.yaml` in your project root. Every value has a default —
override only what you care about. Use **CodeGuards' own self-config** as
a realistic example:

```yaml
# .codeguards.yaml — CodeGuards self-config (its own project)
guards:
  file_length:
    max_prod: 800    # orchestrator files legitimately touch many modules
    max_test: 600
  function_length:
    max: 60
  parameter_count:
    max_params: 7
  fan_out:
    max_dependencies: 30
  god_file:
    max_public_items: 25
    max_imports: 40
  deep_nesting:
    max_depth: 15
  # Quieter by default — opts into generic heuristics selectively.
  forbidden_phrases: { enabled: false }
  missing_docs:      { enabled: false }
  missing_tests:     { min_test_ratio: 0.0 }
  magic_numbers:     { enabled: false }
  structural_health: { enabled: false }
  responsibility_clusters: { enabled: false }
  duplicated_code:   { enabled: false }
```

If `.codeguards.yaml` is absent, sensible defaults apply.

---

## Intent overrides enforcement

`intent.json` reclassifies violations **as expected** when the project
explicitly declares the condition.

Example — the friend-validation codebase had 522 `magic_numbers` violations
that were *actually property prices / sqft / zip codes*. With
`intent.json` declaring domain data, those stay flagged as
`acceptable_per_intent` rather than forcing the AI to "fix" them.

The mechanism: `guards/__init__.py::enrich_with_fixes` cross-references
violations against `intent.py::GUARD_TO_RULE` (a 6-entry fixed map:
`debug_statements↔logging`, `swallowed_errors↔error_handling`,
`no_stubs↔testing`, `missing_docs↔documentation`, `no_unwrap↔error_handling`,
`tracing_instrument↔tracing`).

---

## Writing a plugin

The plugin system has **two kinds of contributions** to the
`GuardRegistry`:

1. **Guards** — per-language checks with their own violation logic.
2. **Extractors** — capability providers that the *generic* layer
   consults. E.g. "Python: how do I find function blocks?" — answer
   registered once and `check_function_length` uses it transparently.

```python
# plugins/python.py — TEMPLATE (no Python plugin ships yet; only rust.py today)
from plugins import GuardRegistry


def register(registry: GuardRegistry) -> None:
    registry.register_guard(
        name="no_print_in_lib",
        check_fn=_no_print_in_lib,
        languages=["python"],
        description="No print() in library code",
    )

    # Capability provider — generic guards call this via get_extractor("function_blocks", ext)
    # when they encounter a .py file. Without an extractor, generic guards fall back
    # to language-agnostic regex (still works, just less precise).
    registry.register_extractor(
        capability="function_blocks",
        file_extensions={".py"},
        extractor_fn=_python_function_blocks,  # returns list of (name, start, end)
    )
```

Plugin discovery: at server startup, `plugins/*.py` is scanned and each
module's `register(registry)` is called. No global pollution —
each project's plugin registration goes into its own `plugins/`.

Generic guards that need language-specific parsing **fall back to
language-agnostic regex** if no extractor is registered. They still work —
they just miss edge cases. That's why plugins are **depth**, not the
on-ramp.

---

## Sandbox

Every MCP path argument is validated before file I/O:

**Denied on sight** (resolved path):

- Credential stores: `~/.aws`, `~/.ssh`, `~/.kube`, `~/.docker`, `~/.npmrc`,
  `~/.netrc`, `~/.pypirc`, `~/.git-credentials`, `~/.gitconfig`
- Kernel / system: `/proc`, `/sys`, `/dev`, `/boot`, `/var/log`, `/var/run`
- Non-existent paths

`..` and symlinks are resolved *first*, so `/tmp/escape/../../etc` cannot
bypass the deny-list. See `server.py::_is_safe_project_path` and
`tests/test_server.py::test_sandbox_denies_aws_credentials` for the test
that pins this behavior.

---

## Project layout

```
codeguards-mcp/
├── server.py              # MCP server, 10 tools, sandbox
├── planning.py            # ARCHITECTURE.md & PROJECT_PLAN.md writers
├── intent.py              # intent.json contract & GUARD_TO_RULE
├── config.py              # .codeguards.yaml loader
├── constants.py           # default thresholds
├── detectors.py           # language detection, source-file walker
├── import_analyzer.py     # AST-aware import graphs (used by layer_enforcement)
├── fixes.py               # text generators for "fix" suggestions on violations
├── guards/
│   ├── generic.py         # 18 language-agnostic per-file checks
│   └── structural.py      # 5 multi-file / structural checks
├── plugins/
│   ├── __init__.py        # GuardRegistry (singleton) + loader
│   └── rust.py            # no_unwrap, tracing_instrument
├── sample_code/           # small fixtures for testing guards by hand
│   ├── profile.rs
│   └── mouse.rs
└── tests/                 # pytest
```

---

## Roadmap

- **v0.1.0 (current)** — what you just read. Validated on a stranger's
  repo via OpenCode.
- **v0.1.1** — hotfixes (in progress).
- **v0.2** — architecture-decision-as-source-of-truth, vocabulary-bounded
  rules, project-scoped session checks. Spec is parked at
  [`docs/design_v0.2.md`](docs/design_v0.2.md). Implementation begins
  after v0.1.1 ships.

---

## Tests

```bash
pip install -e .[dev]
pytest tests/
```

The full suite covers: sandbox boundaries, intent overload,
`probe → declare_intent → plan → check_project` end-to-end, Rust plugin
behavior, fan-out / responsibility clusters / layer enforcement, import
analyzer on multi-file dependency graphs, and dogfood — CodeGuards running
against its own codebase.

---

## Philosophy, briefly

> Every system that decides "this code is correct" works in two halves:
> a front-half that says what correctness **means**, and a back-half that
> **enforces** it. Most tools only have a back-half — they infer rules
> from what's there. CodeGuards has both: the AI + user agree on the goal
> (intent), agree on the architecture (architecture / plan), and every
> guard that fires is **measuring the code against that agreement**.
>
> Right now the goal is small (`intent.json`). In v0.2, the goal moves
> into `ARCHITECTURE.md` and becomes the project's long-term memory —
> surviving across AI sessions, model swaps, and the gradual decay of
> first-week clarity.

— see [`docs/design_v0.2.md`](docs/design_v0.2.md) for the full v0.2
direction.
