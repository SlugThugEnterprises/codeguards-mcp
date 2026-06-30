# CodeGuards

**Dynamic architecture contracts for AI-assisted software development.**

CodeGuards is an MCP server that helps an AI coding agent plan with the user,
turn that plan into an enforceable architecture contract, and check future code
against that contract so the project does not drift as the conversation gets
longer.

It is not trying to be the linter people use. Linters, Clippy, formatters,
security scanners, and type checkers still matter. CodeGuards works one layer
upstream: it helps the agent get the structure right, then uses focused guard
checks to push the generated code toward the project's agreed direction before
normal tools get their turn.

```text
User explains what they want to build
        ↓
CodeGuards guides the planning conversation
        ↓
The AI writes an architecture contract for this project
        ↓
CodeGuards derives guard behavior from that contract
        ↓
The AI writes code
        ↓
CodeGuards checks whether the code still matches the user's plan
        ↓
The AI fixes drift and obvious quality issues before they spread
```

A normal linter asks, "Does this code match a generic rule?"

CodeGuards asks, "Does this code still match the architecture and constraints the
user chose for this project?"

---

## Why this exists

AI coding agents can usually start a project cleanly. They can discuss structure,
choose modules, sketch tests, and follow the user's preferences for the first set
of changes.

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

CodeGuards externalizes that contract and makes it executable.

---

## Product identity

CodeGuards is an **architecture contract system**, not a one-size-fits-all code
quality MCP.

It helps an AI agent:

1. ask high-impact planning questions,
2. capture the user's architecture and quality decisions,
3. materialize those decisions into project-local files,
4. derive guard behavior from the architecture contract,
5. return structured, actionable violations that point back to the user's plan.

The supporting lint-style checks are useful, but they are not the identity of the
project. They exist to reduce the amount of bad generated code that reaches the
normal toolchain.

For Rust, for example, the goal is not to replace `cargo clippy`. The goal is to
make the first AI-generated Clippy run less noisy by catching common agent habits
earlier: `.unwrap()` spam, missing tracing on async entry points, oversized files,
poor module boundaries, and drift from the architecture the user chose.

---

## Static rules vs. dynamic architecture contracts

| Static rule engine | CodeGuards architecture contract |
|---|---|
| Starts with generic rules | Starts with the user's goals and constraints |
| Same checks for every project | Guard behavior is derived from the project contract |
| Mostly reports style failures | Reports drift from agreed architecture |
| Easy for agents to treat as busywork | Tells the agent which design decision it violated |
| Passive documentation is optional | The contract is part of the build workflow |

CodeGuards can still run baseline guards: file size, function size, TODOs,
credentials, `unwrap`, tracing, tests, and structural heuristics. Those checks
are the floor. The differentiator is that the core guard behavior should be
shaped by what the user is actually building.

---

## The core idea: one contract guard, many derived constraints

CodeGuards should not create a pile of unrelated ad hoc checks for every project.
The right model is a core **ArchitectureContractGuard** that reads the project's
contract and enforces whatever constraints the user and AI established during
planning.

```text
.planning/ARCHITECTURE.md
        ↓
ArchitectureContractGuard
        ↓
Derived constraints for this project
        ↓
Violations explained by contract section and user decision
```

The constraints are not global opinions. They are decisions captured from the
planning session.

Examples:

| User/project decision | Derived enforcement behavior |
|---|---|
| "Use layered architecture" | API code may import services, but not repositories directly |
| "Domain must be framework-independent" | Domain modules may not import web, database, or infrastructure modules |
| "Use structured tracing" | Public async entry points must carry tracing instrumentation |
| "No direct SQL outside persistence" | SQL clients are allowed only in declared persistence modules |
| "This is a library, not an app" | Public API stability and docs matter more than CLI/runtime checks |
| "This is a prototype" | Some strict production constraints can be absent or weaker |

If the user never chooses a constraint, CodeGuards should not invent it as a
universal rule. If the user chooses it during planning, it becomes part of the
contract.

---

## MCP workflow

The enforce-order is deliberate:

```text
User describes what to build
    ↓
1. probe
   AI asks plain-English questions about goal, scope, architecture, risk,
   persistence, interfaces, observability, testing, and other high-impact choices
    ↓
2. declare_intent
   AI commits to the selected direction
   → writes .codeguards/intent.json
    ↓
3. plan
   AI materializes the architecture contract and implementation plan
   → writes .planning/ARCHITECTURE.md
   → writes .planning/PROJECT_PLAN.md
    ↓
4. update_task / list_tasks
   AI tracks implementation progress against the plan
    ↓
5. check_project
   CodeGuards runs baseline, structural, language-specific, and contract-derived checks
```

`check_project` refuses to run without `.codeguards/intent.json`. That prevents
"fix it later" coding without a declared direction.

---

## Project files

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
such as `project`, `architecture_profile`, `layers`, `modules`, `constraints`,
`quality_goals`, and `decisions`.

Example target shape:

```yaml
project:
  type: web_api
  stage: production

architecture_profile:
  name: layered
  rationale: Keep request handling, business workflow, and persistence separate.

layers:
  api:
    may_import:
      - application
    decision: API code talks to application services, not persistence directly.
  application:
    may_import:
      - domain
      - ports
    decision: Workflows coordinate domain behavior through declared ports.
  domain:
    may_import: []
    decision: Domain logic is independent of frameworks, storage, and transport.
  infrastructure:
    may_import:
      - ports
      - domain
    decision: Infrastructure implements ports and contains external integrations.

modules:
  auth:
    owns:
      - src/auth/**
    may_import:
      - domain
      - ports
    decision: Authentication logic is isolated from billing and reporting.
  billing:
    owns:
      - src/billing/**
    may_import:
      - domain
      - ports
    decision: Billing must not reach into auth internals.

constraints:
  no_direct_database_from_api:
    enabled: true
    decision: Request handlers must go through application services.
  domain_no_framework_imports:
    enabled: true
    decision: Domain code must stay portable and testable.
  structured_observability:
    enabled: true
    decision: Production workflows require traceable execution paths.

quality_goals:
  tests:
    unit_required: true
    integration_required_for:
      - persistence
      - external_api_clients
  docs:
    public_api_docs_required: true
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
.planning/ARCHITECTURE.md → constraints.no_direct_database_from_api

Decision:
Request handlers must go through application services.

Fix:
Move the database call behind an application service and import that service instead.
```

That feedback loop is the core value of CodeGuards. The AI gets a reason tied to
the project contract, not a disconnected rule number.

---

## What exists today

The current implementation already provides the enforce-order pipeline and a set
of useful baseline guards.

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

- Treating `ARCHITECTURE.md` as the primary architecture contract input for
  contract-derived checks.
- Implementing a core `ArchitectureContractGuard` that evaluates contract data.
- Rich architecture profiles such as layered, clean, and hexagonal.
- Contract-source reporting for every architecture violation.
- Better distinction between observed structure and intended structure.
- Deliberate contract update flows for legitimate architecture changes.

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

## Built-in guards today

These are the current baseline checks. They are useful on their own, but they are
not the full product vision. The product direction is for the core architecture
contract to decide which constraints matter for a specific project.

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

`.codeguards.yaml` is for guard configuration and thresholds. The project-specific
architecture contract belongs in `.planning/ARCHITECTURE.md`.

---

## Intent and violation context

`intent.json` lets violations be interpreted against declared project intent.

For example, a `swallowed_errors` violation can be reported with the declared
error-handling strategy, and a `no_unwrap` violation can point back to the
project's stated error-handling rule.

The architecture contract expands this principle: every contract-derived
violation should carry project-specific context and cite the decision it came
from.

---

## Plugin system

Plugins add depth for specific languages. They are not the mechanism for building
the project's architecture contract.

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
exists. Plugins improve precision, but the dynamic architecture contract is the
core product layer.

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
  creating many one-off rule implementations.
- Add architecture profiles such as layered, clean, and hexagonal.
- Generate contract constraints from the user's planning choices, not from a
  universal checklist.
- Make violations cite the exact contract section and design decision they come
  from.
- Separate observed architecture from intended architecture so CodeGuards does
  not preserve accidental messes.
- Add explicit contract update flows for legitimate architecture changes.

Long-term identity:

> CodeGuards helps establish an architecture at project inception, records that
> architecture as an executable contract, and continuously verifies that
> AI-generated code does not drift away from the user's agreed design.
