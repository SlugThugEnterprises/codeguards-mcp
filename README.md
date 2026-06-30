# CodeGuards

**Architecture contracts for AI-assisted software development.**

CodeGuards is an MCP server that makes AI coding agents plan before they build,
records the agreed design as project files, and checks future code against that
contract so the architecture does not drift as the conversation gets longer.

The goal is not to make the model "smarter." The goal is to give the model a
stable source of truth outside the chat context:

```text
User and AI agree on architecture
        ↓
CodeGuards writes that intent to disk
        ↓
AI writes code
        ↓
CodeGuards checks the code against the agreed contract
        ↓
AI fixes drift before it spreads
```

A normal linter asks, "Does this code match a generic rule?"

CodeGuards asks, "Does this code still match the architecture this project chose?"

---

## The problem

AI coding agents are usually good at the first few prompts of a project. They
can discuss architecture, choose modules, set testing expectations, and start in
a coherent direction.

The failure mode appears later:

```text
Prompt 1:   Use a service layer.
Prompt 12:  Add authentication.
Prompt 31:  Add billing.
Prompt 58:  Add reporting.
Prompt 90:  The AI bypasses the service layer because it is faster.
```

That is architectural drift. The design decision still exists somewhere in chat
history, but the agent no longer has a compact, enforceable contract in front of
it.

CodeGuards externalizes that contract.

---

## Product identity

CodeGuards is best understood as an **architecture contract system**, not just a
quality-rule MCP.

It helps an AI agent:

1. ask the user high-impact planning questions,
2. declare the intended architecture,
3. materialize that intent into project files,
4. enforce the resulting contract during future code changes,
5. report violations with context rooted in the project's own decisions.

The important distinction:

| Documentation | Architecture contract |
|---|---|
| Describes what exists | Defines what must remain true |
| Read by humans | Read by humans and tools |
| Easy for agents to forget | Re-loaded on every check |
| Usually passive | Enforced by guards |

---

## MCP workflow

The enforce-order is deliberate:

```text
User describes what to build
    ↓
1. probe
   AI asks plain-English questions about goal, scope, constraints, and design preferences
    ↓
2. declare_intent
   AI commits to architecture, modules, dependency expectations, error strategy,
   logging, tracing, and testing direction
   → writes .codeguards/intent.json
    ↓
3. plan
   AI materializes the architecture and implementation plan
   → writes .planning/ARCHITECTURE.md
   → writes .planning/PROJECT_PLAN.md
    ↓
4. update_task / list_tasks
   AI tracks implementation progress against the plan
    ↓
5. check_project
   CodeGuards runs all enabled guards against the project
```

`check_project` refuses to run without `.codeguards/intent.json`. That prevents
"fix it later" coding without a declared direction.

---

## The project files CodeGuards creates

`declare_intent` and `plan` create project-local files. These are meant to be
committed with the project so the next AI agent, teammate, or coding session sees
the same expectations.

| File | Purpose | Read by |
|---|---|---|
| `.codeguards/intent.json` | Raw declared intent from the planning step | guards, report enrichment |
| `.planning/ARCHITECTURE.md` | Human-readable and machine-readable architecture contract | structural and contract checks |
| `.planning/PROJECT_PLAN.md` | Phased implementation plan with task state | `update_task`, `list_tasks` |

`ARCHITECTURE.md` is the key file. The markdown body explains the design to
humans. The YAML frontmatter is the machine interface.

Current generated frontmatter is intentionally small:

```yaml
modules:
  - api
  - service
  - repository
layers:
  - api
  - service
  - repository
allowed_dependencies:
  api:
    - service
  service:
    - repository
  repository: []
enforce:
  - error_handling
  - logging
  - testing
  - tracing
```

The design direction is to make this contract richer over time, using sections
such as `architecture_profile`, `layers`, `modules`, `constraints`, and
`quality_goals`.

Example target shape:

```yaml
project:
  type: web_api

architecture_profile:
  name: layered
  derived_constraints:
    - controllers_use_services
    - domain_has_no_infrastructure_imports

layers:
  api:
    may_import:
      - application
    decision: Controllers communicate through application services.
  application:
    may_import:
      - domain
    decision: Business workflows depend inward on domain concepts.
  domain:
    may_import: []
    decision: Domain logic is independent of frameworks and databases.

quality_goals:
  testing:
    require_tests: true
  observability:
    require_structured_logging: true
    require_tracing: true
  dependency_freshness:
    policy: latest_stable
    allow_prerelease: false
```

The contract is not meant to be sacred. Projects evolve. The intended flow is to
update the contract deliberately when architecture changes, not accidentally drift
away from it during unrelated feature work.

---

## What violations should tell the AI

A useful violation is not just:

```text
Rule failed.
```

It should explain the design decision being violated:

```text
Violation:
api/orders.py imports repository/sql.py directly.

Derived from:
.planning/ARCHITECTURE.md → layers.api.may_import

Decision:
API code must communicate through application services, not repositories.

Fix:
Move the database call behind an application service and import that service instead.
```

That feedback loop is the core value of CodeGuards. The AI gets a reason tied to
the project contract, not a disconnected rule number.

---

## What exists today

The current implementation already provides the enforce-order pipeline and a set
of core guards.

Implemented:

- MCP server over stdio, with optional HTTP SSE mode.
- `probe → declare_intent → plan → check_project` workflow.
- `.codeguards/intent.json` creation and required-before-check enforcement.
- `.planning/ARCHITECTURE.md` and `.planning/PROJECT_PLAN.md` generation.
- Generic source checks for common AI coding problems.
- Structural checks for fan-out, responsibility clusters, layer enforcement,
  structural health, and growth drift.
- Project-level `missing_tests` check.
- Rust guards for `.unwrap()` / `.expect()` and missing tracing instrumentation.
- Configurable thresholds through `.codeguards.yaml`.
- Path sandboxing for MCP file operations.

Still being sharpened:

- Treating `ARCHITECTURE.md` as the primary architecture contract input for all
  contract-derived checks.
- Rich architecture profiles such as layered, clean, and hexagonal.
- Contract-source reporting for every architecture violation.
- Core project-level checks such as dependency freshness.
- Better distinction between observed structure and intended structure.

This README describes the intended product direction and the current mechanics.
The near-term implementation target is to make the architecture contract the
first-class source of enforcement, not just a generated planning artifact.

---

## Install

```bash
pip install mcp pyyaml
```

For HTTP SSE mode, also install:

```bash
pip install starlette uvicorn
```

The HTTP dependencies are only imported when `--port` is used. Stdio mode is the
default for local MCP clients.

---

## Run

```bash
# stdio mode, for local MCP clients
python server.py

# HTTP SSE mode, for remote or HTTP-aware clients
python server.py --port 8000
# clients connect to http://<host>:8000/sse
```

---

## Verified MCP clients

| Client | Mode | Status | Example install |
|---|---|---|---|
| Claude Code | stdio | verified | `claude mcp add codeguards --command "python /path/to/server.py"` |
| Hermes | stdio | verified | `hermes mcp add codeguards --command "python /path/to/server.py"` |
| OpenCode | stdio | verified | registered through OpenCode MCP config |

Any stdio-capable MCP client should be able to call the server. Codex and Cursor
are design targets, but are not listed as verified here.

---

## MCP tools

`server.py` exposes ten MCP tools.

| Tool | Purpose |
|---|---|
| `probe` | Ask plain-English planning questions before code is written. |
| `declare_intent` | Save architecture intent to `.codeguards/intent.json`. Required before `check_project`. |
| `plan` | Generate `.planning/ARCHITECTURE.md` and `.planning/PROJECT_PLAN.md`. Refuses without intent. |
| `update_task` | Mark a task complete, pending, or in progress in `PROJECT_PLAN.md`. |
| `list_tasks` | Show pending tasks from the project plan. |
| `check_project` | Run enabled guards against the whole project. Refuses without intent. |
| `check_file` | Run enabled per-file checks against one file. |
| `detect_languages` | Detect project languages from marker files and source extensions. |
| `list_guards` | List available guards and the languages they apply to. |
| `save_baseline` | Snapshot structural metrics for later growth-drift detection. |

---

## Built-in guards

### Generic per-file guards

These run against source files and catch common AI-generated code problems.

| Guard | Catches |
|---|---|
| `file_length` | Production files over the configured line cap |
| `function_length` | Functions over the configured line cap |
| `god_file` | Too many public items or imports |
| `forbidden_phrases` | Vague terms such as `temporary`, `for now`, `maybe`, `clean` |
| `glob_imports` | Wildcard imports such as `use foo::*` or `from bar import *` |
| `debug_statements` | `println!`, `console.log`, or `print()` left in production code |
| `commented_code` | Dead code blocks left in comments |
| `magic_numbers` | Unexplained numeric literals |
| `duplicated_code` | Repeated copy-paste line blocks |
| `unsafe_patterns` | `eval`, `exec`, or Rust `unsafe` patterns |
| `deep_nesting` | Excessive nesting depth |
| `parameter_count` | Functions with too many parameters |
| `credentials` | API keys, tokens, and obvious secrets in source |
| `action_items` | `TODO`, `FIXME`, or `HACK` without issue tracking |
| `hardcoded_values` | Raw URLs, IPs, and ports as literals |
| `missing_docs` | Public items without docstrings or doc comments |
| `swallowed_errors` | Empty `catch` or `except` blocks |
| `no_stubs` | `todo!`, `unimplemented!`, or stub placeholders in production |

### Structural guards

These reason across imports and project structure.

| Guard | Catches |
|---|---|
| `responsibility_clusters` | Files touching too many concern domains |
| `fan_out` | Modules becoming coordination hubs through too many dependencies |
| `layer_enforcement` | Imports that violate configured layer rules |
| `structural_health` | Composite structure score based on fan-out and responsibility spread |
| `growth_drift` | Structural growth compared with a saved baseline |

### Project-level guards

These run once per project check, not once per source file.

| Guard | Catches |
|---|---|
| `missing_tests` | Source files without matching tests, below the configured test ratio |

Dependency freshness belongs in this category. It is a project contract rule, not
a per-file source lint.

### Language-specific guards

Rust support exists today.

| Guard | Language | Catches |
|---|---|---|
| `no_unwrap` | Rust | `.unwrap()`, `.expect()`, and `.unwrap_unchecked()` in library code |
| `tracing_instrument` | Rust | Public async functions missing `#[tracing::instrument]` |

---

## Configuration

Drop `.codeguards.yaml` in the project root to tune defaults.

```yaml
guards:
  file_length:
    max_prod: 800
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
  forbidden_phrases:
    enabled: false
  missing_docs:
    enabled: false
  missing_tests:
    min_test_ratio: 0.3
```

`.codeguards.yaml` is for guard configuration and thresholds. The architecture
contract belongs in `.planning/ARCHITECTURE.md`.

---

## Intent and violation context

`intent.json` lets violations be interpreted against declared project intent.

For example, a `swallowed_errors` violation can be reported with the declared
error-handling strategy, and a `no_unwrap` violation can point back to the
project's stated error-handling rule.

This is the same principle the architecture contract expands: violations should
carry project-specific context, not just generic lint text.

---

## Plugin system

Plugins add depth for specific languages. They are not the main architecture
contract mechanism.

The plugin registry supports two contribution types:

1. **Guards**: per-language checks with custom violation logic.
2. **Extractors**: parsing helpers used by generic guards, such as language-aware
   function block extraction.

Example shape:

```python
from plugins import GuardRegistry


def register(registry: GuardRegistry) -> None:
    registry.register_guard(
        name="no_print_in_lib",
        check_fn=_no_print_in_lib,
        languages=["python"],
        description="No print() in library code",
    )

    registry.register_extractor(
        capability="function_blocks",
        file_extensions={".py"},
        extractor_fn=_python_function_blocks,
    )
```

At server startup, CodeGuards loads installed files from its own `plugins/`
directory. Generic guards fall back to language-agnostic regex when no extractor
exists. Plugins improve precision, but the architecture contract is the core
product layer.

---

## Sandbox

Every MCP path argument is validated before file I/O.

Denied path segments:

- `.aws`
- `.ssh`
- `.kube`
- `.docker`
- `.npmrc`
- `.netrc`
- `.pypirc`
- `.git-credentials`
- `.gitconfig`

Denied system prefixes:

- `/proc`
- `/sys`
- `/dev`
- `/boot`
- `/var/log`
- `/var/run`

CodeGuards also refuses non-existent paths. Paths are resolved before checks, so
`..` traversal and symlink tricks cannot bypass the deny list.

---

## Project layout

```text
codeguards-mcp/
├── server.py              # MCP server, tool dispatch, path sandbox
├── planning.py            # ARCHITECTURE.md and PROJECT_PLAN.md generation
├── intent.py              # .codeguards/intent.json contract handling
├── config.py              # .codeguards.yaml defaults and deep merge
├── detectors.py           # language detection and source walking
├── import_analyzer.py     # import-domain and layer analysis
├── fixes.py               # fix suggestion text
├── guards/
│   ├── __init__.py        # guard orchestration and project-level checks
│   ├── generic.py         # language-agnostic source guards
│   └── structural.py      # multi-file structural guards
├── plugins/
│   ├── __init__.py        # plugin registry and loader
│   └── rust.py            # Rust-specific guards and extractors
└── pyproject.toml
```

---

## Roadmap

Near-term direction:

- Promote `.planning/ARCHITECTURE.md` from generated artifact to first-class
  architecture contract.
- Add an `ArchitectureContractGuard` that evaluates contract data rather than
  creating many one-off rules.
- Add architecture profiles such as layered, clean, and hexagonal.
- Make violations cite the exact contract section and design decision they come
  from.
- Add core project-level dependency freshness checks for package managers such as
  Cargo.
- Separate observed architecture from intended architecture so CodeGuards does
  not preserve accidental messes.
- Add explicit contract update flows for legitimate architecture changes.

Long-term identity:

> CodeGuards helps establish an architecture at project inception, records that
> architecture as an executable contract, and continuously verifies that
> AI-generated code does not drift away from the agreed design.
