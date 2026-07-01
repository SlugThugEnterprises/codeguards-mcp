# CodeGuards

**CodeGuards is an MCP server that turns AI coding intent into an enforceable architecture contract and continuously prevents drift as code is generated.**

It exists to help AI start with a good architecture, preserve that architecture as development evolves, and reduce downstream friction by nudging the AI toward better engineering practices from the beginning.

CodeGuards is not trying to be the linter people use. Linters, Clippy, Ruff, formatters, tests, security scanners, and CI still matter. CodeGuards sits before them.

For the detailed v0.2 system model, file contracts, plugin standard, and runtime guarantees, see [`docs/V0.2_ARCHITECTURE_SPEC.md`](docs/V0.2_ARCHITECTURE_SPEC.md).

```text
Intent
  what are we building?
        ↓
Architecture
  how is it structured?
        ↓
Plan
  how will we implement it?
        ↓
Code
  AI generates the change
        ↓
Guards enforce alignment
  CodeGuards catches design drift
        ↓
AI fixes drift
  before Clippy, Ruff, tests, CI, reviewers, or humans get the mess
```

Compilers catch mistakes. Linters catch language issues. CodeGuards catches design drift.

---

## Why this exists

AI coding agents can usually start a project cleanly. They can discuss structure, choose modules, sketch tests, and follow the user's preferences for the first set of changes.

The failure mode appears later:

```text
Prompt 1:   Use a service layer.
Prompt 12:  Add authentication.
Prompt 31:  Add billing.
Prompt 58:  Add reporting.
Prompt 90:  The AI bypasses the service layer because it is faster.
```

That is architectural drift. The decision still exists somewhere in chat history, but the agent no longer has a compact, enforceable contract in front of it.

Humans naturally remember decisions like:

```text
Business logic lives in services.
Controllers do not talk directly to repositories.
Domain code does not import infrastructure.
```

AI does not reliably preserve those decisions across long implementation sessions. Repeating the same reminder in every prompt is brittle.

CodeGuards changes the loop from:

```text
Remember to keep business logic out of controllers.
```

to:

```text
That decision has been recorded. CodeGuards will enforce it.
```

---

## What CodeGuards is

CodeGuards is a **staged architecture enforcement lifecycle for AI coding agents**.

The core lifecycle is:

```text
probe → declare_intent → plan → update_task → check_project
```

That lifecycle creates a clean hierarchy:

| Layer | File/tool | Meaning |
|---|---|---|
| Intent | `.codeguards/intent.json` | Why are we building this, and what direction did the user choose? |
| Architecture | `.planning/ARCHITECTURE.md` | How is the system structured, and what constraints must remain true? |
| Plan | `.planning/PROJECT_PLAN.md` | How will implementation proceed? |
| Guards | `check_project` | Does the generated code still align with the contract? |

`check_project` refuses to run without `.codeguards/intent.json`. That is not just a feature; it is the boundary that prevents architecture-less execution.

No intent, no full-project enforcement.

---

## Planning Mode

The architecture interview is the key workflow.

Instead of:

```text
User: Build me an ERP.
        ↓
AI: Starts writing code.
```

CodeGuards pushes the process toward:

```text
User: Build me an ERP.
        ↓
AI: Let's spend a few minutes designing the architecture.
        ↓
CodeGuards Planning captures the decisions.
        ↓
ARCHITECTURE.md is generated.
        ↓
Project-specific guard behavior is derived from the contract.
        ↓
Implementation begins.
```

A greenfield Planning Mode might look like:

```text
CodeGuards Planning

Project Type:
✓ REST API

Architecture:
✓ Layered

Persistence:
✓ PostgreSQL

Dependency Rules:
✓ Controllers → Services only
✓ Domain must not import Infrastructure

Quality Goals:
✓ Strong tests
✓ Structured logging
✓ No God Objects

Generate Architecture Contract?
```

When the user says yes:

1. `.codeguards/intent.json` is created,
2. `.planning/ARCHITECTURE.md` is created,
3. `.planning/PROJECT_PLAN.md` is created,
4. the MCP derives project-specific guard behavior,
5. every future coding request can be checked against the contract.

That changes the conversation from:

```text
Why did the AI write messy code?
```

to:

```text
Did we define the architecture well enough before implementation started?
```

Good architects do not usually start by writing classes. They start by agreeing on constraints, boundaries, dependencies, and tradeoffs. CodeGuards brings that habit into AI-assisted development.

---

## Greenfield and existing-project modes

CodeGuards is useful in two modes.

### Greenfield mode

For a new project, CodeGuards should run the strict lifecycle from the start:

```text
probe → declare_intent → plan → implement → check_project
```

The user and AI agree on the architecture before the first real implementation pass. The generated contract becomes the source of truth for future changes.

### Existing project mode

For an existing codebase, CodeGuards can be introduced by generating an initial intent and architecture snapshot from the current structure, then asking the user what should be preserved, cleaned up, or changed.

That produces a baseline contract for future work:

```text
inspect existing structure
        ↓
bootstrap intent + architecture snapshot
        ↓
user confirms or corrects the contract
        ↓
future changes are checked against it
```

The goal is not to freeze accidental messes. Existing projects need a distinction between:

| Concept | Meaning |
|---|---|
| Observed architecture | What the code currently does |
| Intended architecture | What future work must move toward or preserve |

CodeGuards should make that distinction explicit so it can help improve a legacy project instead of preserving every bad pattern it finds.

---

## Static rules vs. dynamic architecture contracts

| Static rule engine | CodeGuards architecture contract |
|---|---|
| Starts with generic rules | Starts with the user's goals and constraints |
| Same checks for every project | Guard behavior is derived from the project contract |
| Mostly reports style failures | Reports drift from agreed architecture |
| Easy for agents to treat as busywork | Tells the agent which design decision it violated |
| Passive documentation is optional | The contract is part of the build workflow |
| Usually runs after code exists | Shapes the code before traditional tooling sees it |

CodeGuards can still run baseline guards: file size, function size, TODOs, credentials, `unwrap`, tracing, tests, and structural heuristics. Those checks are the floor. The differentiator is that the core guard behavior should be shaped by what the user is actually building.

For Rust, the goal is not to replace `cargo clippy`. The goal is to make the first AI-generated Clippy run less noisy by catching common agent habits earlier: `.unwrap()` spam, missing tracing on async entry points, oversized files, poor module boundaries, and drift from the architecture the user chose.

---

## The core idea: one contract guard, many derived constraints

CodeGuards should not create a pile of unrelated ad hoc checks for every project. The right model is a core **ArchitectureContractGuard** that reads the project's contract and enforces whatever constraints the user and AI established during planning.

```text
.planning/ARCHITECTURE.md
        ↓
ArchitectureContractGuard
        ↓
Derived constraints for this project
        ↓
Violations explained by contract section and user decision
```

The constraints are not global opinions. They are decisions captured from the planning session.

Examples:

| User/project decision | Derived enforcement behavior |
|---|---|
| "Use layered architecture" | API code may import services, but not repositories directly |
| "Domain must be framework-independent" | Domain modules may not import web, database, or infrastructure modules |
| "Use structured tracing" | Public async entry points must carry tracing instrumentation |
| "No direct SQL outside persistence" | SQL clients are allowed only in declared persistence modules |
| "This is a library, not an app" | Public API stability and docs matter more than CLI/runtime checks |
| "This is a prototype" | Some strict production constraints can be absent or weaker |

If the user never chooses a constraint, CodeGuards should not invent it as a universal rule. If the user chooses it during planning, it becomes part of the contract.

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

---

## Project files

`declare_intent` and `plan` create project-local files. These are meant to be committed with the project so the next AI agent, teammate, or coding session sees the same expectations.

| File | Purpose | Read by |
|---|---|---|
| `.codeguards/intent.json` | Raw declared intent from the planning step | guards, report enrichment |
| `.planning/ARCHITECTURE.md` | Human-readable and machine-readable architecture contract | structural and contract checks |
| `.planning/PROJECT_PLAN.md` | Phased implementation plan with task state | `update_task`, `list_tasks` |

`ARCHITECTURE.md` is the key file. The markdown body explains the design to humans. The YAML frontmatter is the machine interface.

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

The design direction is to make this contract richer over time, using sections such as `project`, `architecture_profile`, `layers`, `modules`, `constraints`, `quality_goals`, and `decisions`.

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

The contract is not meant to be sacred. Projects evolve. The intended flow is to update the contract deliberately when architecture changes, not accidentally drift away from it during unrelated feature work.

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

That feedback loop is the core value of CodeGuards. The AI gets a reason tied to the project contract, not a disconnected rule number.

Fix suggestions are centralized in `fixes.py`, so violations can give the agent specific next steps instead of only reporting failure.

---

## Generic-first guarantee

The generic layer works without plugin coverage.

That is the adoption wedge: a project does not need a custom language plugin before CodeGuards can provide value. Generic guards and structural heuristics still catch common AI failure modes, and plugins add depth where precision matters.

```text
No plugin available
        ↓
Generic checks still run
        ↓
Structural checks still run
        ↓
The AI still gets actionable feedback
```

Plugins are depth, not the on-ramp.

---

## What exists today

The current implementation already provides the enforce-order pipeline and a set of useful baseline guards.

Implemented:

- MCP server over stdio, with optional HTTP SSE mode.
- `probe → declare_intent → plan → check_project` workflow.
- `.codeguards/intent.json` creation and required-before-check enforcement.
- `.planning/ARCHITECTURE.md` and `.planning/PROJECT_PLAN.md` generation.
- Generic source checks for common AI coding problems.
- Structural checks for fan-out, responsibility clusters, layer enforcement, structural health, and growth drift.
- Project-level `missing_tests` check.
- Rust guards for `.unwrap()` / `.expect()` and missing tracing instrumentation.
- Configurable thresholds through `.codeguards.yaml`.
- Path sandboxing for MCP file operations.

Still being sharpened:

- Treating `ARCHITECTURE.md` as the primary architecture contract input for contract-derived checks.
- Implementing a core `ArchitectureContractGuard` that evaluates contract data.
- Planning Mode as the signature greenfield workflow.
- Existing-project bootstrap mode for generating an initial contract from current structure.
- Rich architecture profiles such as layered, clean, and hexagonal.
- Contract-source reporting for every architecture violation.
- Better distinction between observed structure and intended structure.
- Deliberate contract update flows for legitimate architecture changes.

This README describes the intended product direction and the current mechanics. The near-term implementation target is to make the architecture contract the first-class source of enforcement, not just a generated planning artifact.

---

## Install

```bash
pip install mcp pyyaml
```

For HTTP SSE mode, also install:

```bash
pip install starlette uvicorn
```

The HTTP dependencies are only imported when `--port` is used. Stdio mode is the default for local MCP clients.

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

Any stdio-capable MCP client should be able to call the server. Codex and Cursor are design targets, but are not listed as verified here.

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

These are the current baseline checks. They are useful on their own, but they are not the full product vision. The product direction is for the core architecture contract to decide which constraints matter for a specific project.

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

`.codeguards.yaml` is for guard configuration and thresholds. The project-specific architecture contract belongs in `.planning/ARCHITECTURE.md`.

---

## Intent and violation context

`intent.json` lets violations be interpreted against declared project intent.

For example, a `swallowed_errors` violation can be reported with the declared error-handling strategy, and a `no_unwrap` violation can point back to the project's stated error-handling rule.

The architecture contract expands this principle: every contract-derived violation should carry project-specific context and cite the decision it came from.

---

## Plugin system

Plugins add depth for specific languages. They are not the mechanism for building the project's architecture contract.

The plugin registry supports two contribution types:

1. **Guards**: per-language checks with custom violation logic.
2. **Extractors**: parsing helpers used by generic guards, such as language-aware function block extraction.

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

At server startup, CodeGuards loads installed files from its own `plugins/` directory. Generic guards fall back to language-agnostic regex when no extractor exists. Plugins improve precision, but the dynamic architecture contract is the core product layer.

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

CodeGuards also refuses non-existent paths. Paths are resolved before checks, so `..` traversal and symlink tricks cannot bypass the deny list.

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

## The core problem: absence bugs

CodeGuards exists because AI-generated code has a systematic blind spot: **it cannot detect things that should be there but aren't**.

Linters, clippy, and tests catch *presence* bugs — code that is wrong. They cannot catch *absence* bugs — code that is missing.

Example from a real project (antidetect-browser, 2026-06-30):
- The API binary (`main.rs`) did not call `logging::init()` before starting the server.
- All tracing instrumentation in the codebase was silently doing nothing.
- `cargo build` passed. `cargo test` passed (522 tests). `cargo clippy` passed (0 warnings). Architecture tests passed (17/17).
- No tool caught it. No test failed. The code was "correct" and completely unobservable.

This is an **absence bug**. The AI wrote everything right except the one thing that makes the system work. The guards caught it only after a human asked "where is logging initialized?"

### What absence bugs look like

| Absence bug | Why tools miss it | How CodeGuards catches it |
|---|---|---|
| Binary doesn't call `logging::init()` | No compilation error, tests pass | Guard: "entry point initialization" |
| API endpoint has no tests | Test suite passes (other tests exist) | Guard: "endpoint test coverage" |
| Error source chains are dropped | Code compiles, error type is correct | Guard: "error context preservation" |
| Config validated but not propagated | `config.validate()` is called, check passes | Guard: "config propagation" |
| `#[tracing::instrument]` missing from pub async fn | Code runs, no compile error | Rust guard: `tracing_instrument` |
| Panic hook never set | Program runs fine until it crashes | Guard: "panic hook registration" |

These are not code quality issues. They are **architectural completeness** issues. The AI wrote code that passes all local checks but fails to form a working system.

### How CodeGuards activates audit-brain

The guards are not just post-hoc checkers. They are designed to make the AI **think like an auditor while writing code**. When the AI knows a guard exists, it preemptively checks for the condition before writing the code.

The workflow is:

```text
1. Human notices an absence bug (e.g., "logging isn't initialized")
2. Human asks AI: "Why did this happen?"
3. AI investigates and identifies the gap
4. Human asks: "How do we make sure this never happens again?"
5. AI proposes a guard rule
6. Guard is added to CodeGuards
7. Future AI runs check_project and sees the violation before shipping
8. Future AI learns to check for this condition proactively
```

Over time, the guard system accumulates the collective wisdom of every absence bug the human has caught. The AI doesn't just fix the bug — it **encodes the lesson into the enforcement system** so future AI agents inherit the knowledge.

This is pressure-driven development. The human doesn't write code. The human applies pressure through questions. The AI figures out the answer and locks it into the guard system.

### The human-AI conversation

CodeGuards is designed for a specific workflow: a non-technical human and an AI coding agent, working together through conversation.

The human describes what they want in plain English. The AI translates it into technical terms. If the AI is confused, it asks clarifying questions — it doesn't pretend to know. If the human's preferred approach is technically weak, the AI says so: *"We can do it that way, but this other approach is much better because…"*

The guard system captures the decisions from that conversation and enforces them. This means:
- The human never needs to learn technical details to get a well-architected system
- The AI never pretends to understand when it's confused
- Bad decisions get caught by guards, not by hindsight
- Good decisions get encoded into the system, not lost in chat history

### What this means for the roadmap

The guards should evolve from "shape checkers" (file length, function length, naming) to **"completeness checkers"** (entry point init, test coverage by endpoint, error context preservation, config propagation, panic hook registration).

Every guard should answer the question: *"Did the AI think about the full system, or just the code it wrote?"*

---

## Roadmap

### v0.2 (current)

- ✅ `probe → declare_intent → plan → check_project` workflow
- ✅ `.codeguards/intent.json` and `.planning/ARCHITECTURE.md` generation
- ✅ Baseline guards (file length, function length, credentials, unsafe patterns, etc.)
- ✅ Structural guards (fan-out, responsibility clusters, layer enforcement)
- ✅ Language-specific guards (Rust: no_unwrap, tracing_instrument)
- ✅ `entry_point_init` guard — first "completeness checker" for absence bugs
- ✅ Thinking pause notifications for expensive operations
- ✅ Test suite: 315 tests passing
- ✅ Coach-not-cop philosophy — positive reinforcement, opt-in checkpoints, agent-tunable modes

### v0.3 (next)

- **3 enforcement modes** — `fast` (suggestions only), `balanced` (random sampling), `strict` (every file review)
- **Coaching reports** — not just violations, but positives, streaks, and suggestions
- **Test library architecture** — guard tests live in `~/.codeguard/tests/` (outside any project), managed by the MCP server so the AI cannot silently edit them to make failures go away
- **tests.yaml** — maps architecture constraint declarations to test modules; the architecture document becomes the scope gate (with `ARCHITECTURE.md` → full enforcement; without → baseline only)
- **Composable tests** — tests written for one project are automatically available to all future projects; the library compounds over time
- **ArchitectureContractGuard** — reads `.planning/ARCHITECTURE.md` YAML frontmatter and resolves applicable tests dynamically, not from a static checklist
- **Remote test registry** — shared test modules published by the community (e.g., `@rust-expert/test_entry_point_init`)

Long-term identity:

> CodeGuards moves architectural decisions from fragile prompt history into an executable contract that continuously guides AI-generated code, while applying just enough engineering pressure to reduce friction with the rest of the development toolchain.
