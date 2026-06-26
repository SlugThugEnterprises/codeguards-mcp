# CodeGuards v0.2 — Architecture-as-Source-of-Truth Design

> **Status:** 🚧 **PARKED** — not committed to a release. Implementation does not begin
> until v0.1.1 hotfixes ship. This document is a captured design decision, not an
> active work item. Do not start coding from this doc without an explicit go-ahead.

---

## 0. Context

**v0.1.0 ships** (this is already true):

- `probe` blocks `plan` until intent is declared (the "confidence to build" gate).
- `.codeguards/intent.json` exists and gates violations as `acceptable_per_intent`
  (proven live by the friend's session — 522 property-data magic numbers
  correctly reclassified).
- Generic guard layer fires without language-plugin coverage (proven by the
  same friend: Python + JS + HTML, no language plugin matched, audit still ran
  end-to-end and produced actionable fixes).
- `check_layer_enforcement` already reads `ARCHITECTURE.md`'s
  `allowed_dependencies` frontmatter and emits violations — the
  architecture-decision-as-enforcement pattern already has a working example.

**v0.1.0 does NOT solve** (this is the gap v0.2 closes):

- AI forgets half its architectural decisions by Prompt 73 of a long task.
- `intent.json` is at risk of becoming a "one-use throwaway" the AI fills with
  contextual detail until it's more brittle than not having it.
- Per-project enforcement (e.g., "no console.log after 4pm on this repo")
  has no first-class home. Today it has to either live in a global plugin
  (pollutes every other project) or be invented from scratch each session.
- The relationship between intent.json and ARCHITECTURE.md is muddy — they
  overlap, drift, and the AI doesn't know when to write which.

---

## 1. Design Goals

1. **Human-readable AND machine-enforceable architecture doc** that survives
   across sessions and model changes.
2. **Goal is write-once and stays small.** Anti-bloat is structural, not
   policing. The AI cannot accidentally inflate it.
3. **Per-project rules have a first-class home** that loads at session start
   and drops at session end. No global pollution from project-specific quirks.
4. **Vocabulary is bounded.** Rules are *predetermined schema fields* that
   map to existing guards (or to session-scoped checks) — not a freeform DSL
   that can grow into a regex tarpit.
5. **Edit ARCHITECTURE.md = a deliberate act.** The doc declares itself the
   source of truth in its own preamble. Casual edits are not the mode.

## 2. Non-Goals

- Replacing the plugin system. Plugins remain the language-specific
  enrichment layer; v0.2 adds *project-scoped* rules on top.
- AI-emits-arbitrary-code. The "Thursday deploy" check is data, not Python
  source. We are not building an AI-generates-guard-functions feature.
- A full rule compiler / DSL. Vocabulary is bounded to a fixed set of schema
  fields (see §6).
- Multi-user collaborative editing of ARCHITECTURE.md (no concurrent merge
  expected; it's a single-AI-author-with-human-review doc).

---

## 3. Files and Lanes

| File | Role | Owned by | Lifecycle |
|------|------|----------|-----------|
| `.planning/ARCHITECTURE.md` | The source of truth: goal + principles + architecture + quality goals | Project, often git-tracked | Read every check; written only by `plan` / explicit architecture update tool |
| `.codeguards/checks.json` | Per-project session-scoped enforcement cache | Project, often gitignored | Loaded into `GuardRegistry` on session start; evicted on session end |
| `.codeguards/intent_archive/<timestamp>.json` | Prior intent snapshots, only when Goal changes | Project, gitignored | Append-only archive |

`intent.json` is **gone** (absorbed into ARCHITECTURE.md's `## Goal` section).

---

## 4. ARCHITECTURE.md — Layout

Top to bottom:

```
# Architecture — single source of truth

> This document is the canonical record of this project's goal and architecture.
> Edit here means you mean it.

---

## Goal

[one short paragraph]

---

## Principles

- [name]: [one-line description]

---

## Layers

- [layer name]: [responsibility]

---

## Modules

- [module name]: [path], [responsibility]

---

## Constraints

- [layer]:
    may_import: [list]
    must_import: [list]

---

## Quality Goals

[vocabulary schema — see §6]

---

## Out of scope

[explicit non-goals for this project]
```

### 4.1 The Preamble

Three sentences, lines 1–6:

1. **What it is.** "Canonical record" — anyone opening the file knows the
   role. No more "is it intent.json, README, or the planning notes?".
2. **What it covers.** "Goal and architecture" — implies intent is *here*,
   not in a sidecar.
3. **The contract.** "Edit here means you mean it." It's the unspoken user
   contract. AI gets the message too — don't touch ARCHITECTURE.md without a
   reason.

### 4.2 `## Goal`

**Schema:** exactly one paragraph. The MCP refuses to write anything else.

That's not a soft line count — it's a structural constraint enforced by
`plan` / `update_architecture`. The validator checks:

- Total length of section is fewer than N words (suggested: 60; tunable).
- Section contains exactly one paragraph block.
- No bullet lists, no sub-sections, no tables.

Failure to comply: `plan` returns an error and the doc is not updated.

### 4.3 `## Principles`, `## Layers`, `## Modules`, `## Constraints`

Existing semantics from v0.1.0 — based on the frontmatter `planning.py`
already writes (modules, allowed_dependencies). Section headers replace
frontmatter keys for human readability; the frontmatter continues to exist
because `check_layer_enforcement` (in `guards/structural.py`) reads it, but
the *canonical* source is now the markdown body.

Validate by parsing markdown section bodies and emitting the equivalent
YAML frontmatter; if the two disagree, fail loud. (Migration: §8.)

### 4.4 `## Quality Goals`

A **vocabulary-bounded** schema. See §6 for the full enumeration. This is
where the schema-as-decisions principle lives.

### 4.5 `## Out of scope`

Optional. Lets the project say what it's *not*. Useful for AI: when
reasoning about a feature request, "is X in scope?" has a direct answer.
Not enforced — informational only.

---

## 5. Write-Once Goal Lifecycle

This is the anti-bloat / anti-silent-edit guarantee.

### 5.1 States

`## Goal` has three stable states:

| State | Trigger | Behavior |
|-------|---------|----------|
| **Empty** | Project has never declared a goal | `plan` and `check_project` work, but emit a warning: "No goal declared. Document your goal in `## Goal`." |
| **Declared** | Goal written for the first time | `plan` and `check_project` are unblocked. Doc is now canonical. |
| **Stable** | Any later write — `Goal` exists | Writes are blocked unless user confirms. See §5.2. |

### 5.2 Confirmation-Before-Change

If `## Goal` exists and someone tries to write a different value:

```
CodeGuards: The current goal is:
  "Create MCP server to help AI create better code and architecture"
Attempted new goal:
  "Refactor the MCP for multi-tenant use"
This changes the project's north star. Are you sure you want to change the goal?
- A "no" leaves the goal unchanged.
- A "yes" archives the old goal to .codeguards/intent_archive/<ts>.json
  and replaces it.
```

Archive schema: same as the live `## Goal` parser — `{goal: string}`.
Filename: `<ISO8601-timestamp>_goal.json`.

The MCP does not proceed silently. The human (or AI acting with explicit
user confirmation) has to authorize the change.

### 5.3 Why Write-Once-Without-Confirmation Fails

If we allowed any rewrite, the AI would silently rephrase the goal whenever
the world shifts: "We're building an MCP for Claude Code on Thursdays"
becomes "We're building something for AI coding assistants in 2026" — each
slightly off, none loud enough to notice. After a year, the goal is a
distortion of the original. Write-once-with-explicit-confirmation keeps the
history honest.

### 5.4 Schema-Level Enforcement

`## Goal` schema: `{goal: string}`. Anything else fails validation.

| What the AI wants to add | Schema response | Where it actually belongs |
|---|---|---|
| `for Claude Code` | ❌ context, not goal | nowhere — session state |
| `in Rust` | ❌ language choice | `## Principles` or `## Constraints` |
| `on Thursdays` | ❌ scheduling | `## Quality Goals.deploy_only_on` (example) |
| `modules: [...]` | ❌ architecture | `## Modules` |
| `constraints: [...]` | ❌ architecture | `## Constraints` |

The MCP returns an error and discards. The AI learns by error message that
goal takes only one paragraph.

---

## 6. Vocabulary-Bounded Rules

This is the antidote to the regex-DSL tarpit.

Each entry in `## Quality Goals` is from a **fixed schema**. The schema is a
closed set (see §6.1). Each field maps to either:

- An **existing guard** whose threshold/scope becomes config-driven, OR
- An entry in `.codeguards/checks.json` (session-scoped custom check), OR
- An informational field that affects guards' *severity* but not their
  *existence*.

The schema does NOT grow into:

- `forbid_pattern_unless_in_block`
- `regex_with_3_capturing_groups_and_a_lookahead`
- "any other YAML the AI wants to invent"

### 6.1 Schema (closed set, v0.2 candidate)

```yaml
quality_goals:

  # --- existing-guard configuration ---
  max_file_lines: int                # → constants.py::FILE_LENGTH_MAX
  max_function_lines: int            # → constants.py::FUNCTION_LENGTH_MAX
  max_public_methods: int            # → generic check class-size (if shipped)
  require_tests: bool                # → check_no_stubs / per-module test presence
  require_logging: bool              # → check_debug_statements + intent rule
  forbid_console_log: bool           # → universal JS/Python heuristic (generic)
  magic_numbers_limit: int|false     # → guards/generic.py::check_magic_numbers
                                     #   false = don't fire, int = max acceptable

  # --- architectural mapping (config, not logic) ---
  deploy_only_on: weekday|name       # → checks.json (session cache)
  ci_runs_on: [label]                # → checks.json
  docstring_required: bool           # → existing missing_docs guard
  forbid_unwrap_in_lib: bool         # → plugins/rust.py::check_no_unwrap

  # --- informational (changes displayed severity, no new logic) ---
  criticality: low|medium|high       # → weights violations in run_checks output
  risk_tolerance: conservative|balanced|adventurous
                                     # → which violations escalate vs warn

  # --- session-scoped checks (see §7) ---
  custom_checks: [check_id, ...]     # → entries in checks.json
```

That's the entire schema. Any field outside this is a schema-validation
failure.

### 6.2 Mapping Mechanism (existing code, reused)

| Field | Code target | Already exists? |
|-------|-------------|-----------------|
| `max_file_lines` | `constants.py::FILE_LENGTH_MAX` | Yes — config source moves to arch doc |
| `max_function_lines` | `constants.py::FUNCTION_LENGTH_MAX` | Yes — config source moves to arch doc |
| `require_tests` | New: per-module test existence check | Partial — needs check |
| `require_logging` | `intent.py::GUARD_TO_RULE["debug_statements"]` | Yes — config confirms |
| `forbid_unwrap_in_lib` | `plugins/rust.py::check_no_unwrap` | Yes — config gate |
| `criticality` | `guards/__init__.py::run_checks` output weighting | New — small change |
| `deploy_only_on` | `checks.json` entry | New — session cache |
| `custom_checks` | `checks.json` → `GuardRegistry.register_guard` | New — session cache |

All target primitives already exist. The schema is the user-facing
configuration; the code is the consumer.

### 6.3 Migration of v0.1.0 Constants

Currently, thresholds are in `constants.py` (per the v0.1.0 commit
"extract config thresholds to constants.py"). v0.2 moves the *source of
truth* for these thresholds from `constants.py` to ARCHITECTURE.md.
`constants.py` keeps default values when ARCHITECTURE.md's field is absent
— backward compat for projects that haven't migrated.

This is consistent with the v0.1.0 design intent (extract thresholds to
config); v0.2 just relocates the config.

---

## 7. `.codeguards/checks.json` — Session-Scoped Custom Checks

What happens when the AI + user agree on a check that doesn't fit the
schema? E.g., "no console.log after 4pm" or "this file has exactly 17
functions". That goes in the per-project session cache.

### 7.1 Schema

```json
{
  "schema_version": 1,
  "project_root": ".",
  "load_at": "<ISO8601 timestamp>",
  "checks": [
    {
      "id": "no-console-log-on-thursdays",
      "description": "Forbid console.log() on Thursdays",
      "scope": {"path_glob": "*.{js,ts}"},
      "type": "temporal_forbid",
      "matcher": {"pattern": "\\bconsole\\.log\\(", "language": "javascript"},
      "days_blocked": ["Thursday"],
      "severity": "violation"
    }
  ]
}
```

### 7.2 Vocabulary-Bounded Types (closed set, v0.2 candidate)

The `type` field is also a fixed enum:

- `temporal_forbid` — pattern forbidden on specified days/weeks/dates
- `temporal_require` — pattern required on specified conditions
- `count_limit` — count of matches ≤ N
- `path_forbid` — pattern forbidden in matching paths (existing layer_forbid
  pattern, generalized)
- `co_occurrence` — pattern A implies pattern B must also be present
  within N lines

Anything outside this enum is rejected. The schema *cannot* grow into
arbitrary predicate logic.

### 7.3 Lifecycle

**Load:**

```
MCP server starts
  → for each project_root in known set:
    → load .codeguards/checks.json (if exists)
    → for each entry: register_guard(checks.json_entry)
    → GuardRegistry._global_registry now contains
      [global plugins] + [this project's checks]
```

Or:

```
check_project called for a project_root that wasn't loaded
  → lazy-load checks.json for that root
  → register
  → then run_checks
```

**Active:**

Every `check_file` / `check_project` call iterates the full registry. New
project-specific checks fire on every file. Existing code path in
`guards/__init__.py::run_checks` — no changes needed.

**Drop:**

```
MCP session ends
  → on exit: clear session-scoped guards from registry
  → .codeguards/checks.json remains on disk for next session
OR
working directory changes (different project)
  → evict previous project's session guards
  → lazy-load new project's checks
```

### 7.4 Why Not in `plugins/`?

Three reasons:

1. **`plugins/` is global.** Anything there ships to every user of the MCP.
   A "Thursday deploy" rule from one project would leak to all projects.
2. **`plugins/` is for language enrichment.** AST extractors, per-language
   patterns. Business rules don't belong here.
3. **`plugins/` loads at server start.** Per-project rules must load *per
   project*, on project-entry, not on server-boot.

`.codeguards/checks.json` solves all three.

### 7.5 Migration Note

Existing v0.1.0 projects don't have this file. That's fine — it's optional.
The schema is "absent → no project-specific session checks." No backward
compat burden.

---

## 8. Migration from v0.1.0

This is the change surface for existing projects:

| v0.1.0 | v0.2 | For existing projects |
|--------|------|------------------------|
| `.codeguards/intent.json` | absorbed into `ARCHITECTURE.md` `## Goal` | Migration tool: read intent.json, write one-paragraph `## Goal` section, archive the intent.json path |
| `intent.json` with `modules:`, `global:`, etc. | replaced by ARCHITECTURE.md sections | Migration tool: emit `## Modules` and `## Constraints` from intent.json's old structure |
| `constants.py::FILE_LENGTH_MAX` | sourced from ARCHITECTURE.md, fallback to constants.py | No change for projects that don't declare `max_file_lines` |
| `ARCHITECTURE.md` YAML frontmatter | YAML frontmatter exists alongside markdown body | Validator: frontmatter must agree with section bodies |
| `plugins/rust.py` global rules | unchanged | No change for non-Rust projects |
| no per-project checks | `.codeguards/checks.json` loaded on project entry | No-op for projects without the file |

Migration is **non-destructive**. Existing projects upgrade at their own
pace. `intent.json` is preserved (renamed to `.codeguards/intent_legacy.json`
or moved to archive) so tools that still read it continue to work during the
transition window.

---

## 9. The "Thursday Deploy" Example (end-to-end)

Concrete walk-through of a project-specific, vocabulary-bounded rule.

### Scenario

User: "We deploy only on Thursdays." AI: "Got it. Adding that to the
quality goals."

### What Happens

1. **AI tries `max_file_lines`, etc.** — none fit. AI reads `## Quality Goals`
   schema, sees `deploy_only_on: weekday|name`. Fits.
2. **AI writes:**

   ```yaml
   quality_goals:
     deploy_only_on: thursday
   ```

   This is in the closed schema. Validator accepts.

3. **Sunday:** developer writes code, `check_project` runs. Existing
   guards fire. No special behavior — `deploy_only_on` doesn't affect code
   quality, it affects *deployment*.

4. **Wednesday:** developer tries to run the deploy script. We need a
   check that fires here. Since `deploy_only_on: thursday` doesn't map to
   any existing code-guard, the system emits:

   ```
   Note: 'deploy_only_on: thursday' is a deployment-time rule, not a
   code-quality guard. To enforce, add to .codeguards/checks.json:
     type: temporal_forbid
     days_blocked: ["Wednesday"]
     forbidden_action: "deploy"
   ```

   (This is a v0.2 forward note, not v0.2 itself — but the schema leaves
   room for it.)

5. **Project adds the entry to `checks.json`.** From that point, the
   project has a session-loaded check that fires on Wednesday deploys.
   Other projects don't — they have their own `checks.json` or none.

### What We Did NOT Do

- Did NOT ship a "Thursday deploy" plugin globally.
- Did NOT introduce a regex DSL the AI could grow into arbitrary rules.
- Did NOT make the goal string longer to include scheduling.
- Did NOT make session length depend on current day-of-week.

The Thursday example proves the design fits weird cases without escaping
its boundaries.

---

## 10. Open Questions (for v0.2 implementation, if/when un-parked)

These need answers before code starts:

1. **Where does the `## Goal` validator live?** Suggestion: new
   `intent.py::validate_goal_section`. Single function, called by `plan`
   and `check_project`.
2. **What's the word count cap?** Suggestion: 60 words, tunable via
   constants. Or: ≥1 paragraph, ≤3 sentences, ≤80 words.
3. **`check_layer_enforcement`** currently reads YAML frontmatter. Should
   it read markdown sections instead? Lean: keep frontmatter, validate
   markdown agrees with it. Less disruption.
4. **Should `criticality` map to `run_checks` output ordering?** Yes — high
   criticality means violations sort first. Small change in
   `guards/__init__.py`.
5. **Archive format.** Suggestion: same `{goal: string}` JSON, timestamped
   filename. Archived files ARE gitignorable but ARE archivable.
6. **`custom_checks` cross-reference.** If `## Quality Goals.custom_checks`
   lists `["no-console-log-on-thursdays"]` but `checks.json` doesn't have
   that entry, what happens? Suggestion: emit a one-time warning at
   session start, treat as not-enforced.

---

## 11. Why This Is Parked

The user explicitly tagged this as park-until-v0.1.1-hotfixes. Reasons
this is the right call:

- **v0.1.0 ships and is validated.** Friend's session proved end-to-end
  working. Don't destabilize working software.
- **v0.1.1 hotfixes are likely small.** Probably docstring enforcement
  edge cases, fix-application bugs, OpenCode-client quirk surfaces. Cheap.
- **v0.2's scope is large.** Schema expansion, new file, validator, MCP
  tool surface changes, migration tool. Not a one-commit feature.
- **The "write-once Goal" guarantee is novel.** Worth doing right, not
  fast. Better to spec-then-build than build-then-fix.

When v0.1.1 ships, this doc is the spec. The work starts there.

---

## 12. References to Existing Code (correspondence with v0.1.0)

| v0.2 concept | Lands on existing v0.1.0 code |
|--------------|-------------------------------|
| ARCHITECTURE.md preamble | new — adds to `planning.py::create_architecture` |
| `## Goal` section | new — replaces path from `intent.json` |
| `## Quality Goals` schema | new — extends `planning.py::create_architecture` template |
| Anti-bloat validator | new — `intent.py::validate_goal_section` (or new module) |
| Write-once confirm | new — `server.py::handle_declare_intent` behavior change |
| Checks.json schema | new — `checks.py` or `plugins/checks.py` |
| Checks.json loader | new — invoked at MCP project-entry |
| Quality-Goals → guard mapping | **existing** — `intent.py::GUARD_TO_RULE`, `constants.py`, `plugins/__init__.py::GuardRegistry` |
| Quality-Goals → severity | **existing** — `guards/__init__.py::run_checks` (small change) |
| Layer enforcement | **existing** — `guards/structural.py::check_layer_enforcement` reads frontmatter |
| Migration from intent.json | new tool — `tools/migrate_v0.1_to_v0.2.py` (one-shot) |

Total new code estimate (when un-parked): ~500 LOC + tests. Reuses all
existing primitives.

---

## 13. Versioning Note

This is a **non-breaking API addition** to the MCP if implemented
carefully:

- `declare_intent` *behavior* changes (write-once + confirmation) but
  *output schema* stays the same.
- New tool: `update_architecture` (writes ARCHITECTURE.md sections).
- New tool: `list_custom_checks` (reads `.codeguards/checks.json`).
- New behavior: `check_project` warns when `.codeguards/checks.json` has
  unresolved entries.

No tool is removed. v0.1.0 clients keep working against a v0.2 server
(potentially with warnings). v0.2 clients gain the new tools.

---

*End of parked design. Do not implement. Spec only. Next: ship v0.1.1 hotfixes.
When v0.1.1 ships, this doc becomes the input to v0.2 implementation.*
