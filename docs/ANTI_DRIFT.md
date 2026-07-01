# CodeGuards MCP — Design Notes & Anti-Drift Strategy

**Date**: 2026-06-30
**Context**: Anti-detect browser codebase audit and remediation

---

## Problem: Model-Induced Guard Drift

LLM agents editing code have a systematic incentive to make guards pass by
changing the guards rather than fixing the underlying code. Observed patterns:

1. **Guard threshold inflation** — Model increases `SOFT_FN_LINES` from 50 to 80
   so its 70-line function passes.
2. **Architecture doc shifts** — Model edits `ARCHITECTURE.md` to describe the
   code it just wrote, making the docs "match" degraded code.
3. **CLAUDE.md erosion** — Model removes rules from project instructions that
   it violated, so future audits don't flag the violation.
4. **Test editing** — Model changes assertion values so tests pass with wrong
   behavior (e.g., changing `assert_eq!(result, 404)` to `assert_eq!(result, 503)`).

These are all **semantic violations** — the code technically passes the guard,
but the guard's intent has been subverted.

---

## Solution: MCP-Controlled Authorization Token

### Core idea

The MCP server holds a secret token that is required to modify protected files.
Models never see the token. Only deliberate human authorization includes it.

### Protected files

```
crates/architecture-tests/src/code_quality_test.rs
crates/architecture-tests/src/tracing_instrument.rs
crates/architecture-tests/src/no_unwrap.rs
crates/architecture-tests/src/dependency_guard.rs
crates/architecture-tests/src/credential_sanitization.rs
crates/architecture-tests/src/forbidden_phrases.rs
.planning/ARCHITECTURE.md
CLAUDE.md
```

### Mechanism

1. **Token generation**: MCP generates a random token on first run, stores it
   in its external state directory (not in the repo).

2. **Pre-commit hook**: A git `pre-commit` hook checks if any protected file
   was modified. If yes, it looks for `[GUARD-AUTH:<token>]` in the commit
   message. No valid token → reject the commit.

3. **MCP verification**: On each MCP run, the server:
   - Computes hashes of all protected files
   - Compares against stored baseline hashes
   - If any mismatch: reports "ARCHITECTURE DRIFT DETECTED" as a critical
     finding, regardless of other test results

4. **Deliberate changes**: When the human wants to change a guard:
   - Run `codeguards-mcp rotate-token` to get the current token
   - Include `[GUARD-AUTH:<token>]` in the commit message
   - After commit, run `codeguards-mcp rehash` to update baseline hashes

### Implementation files

- `/opt/codeguards-mcp/auth.py` — Token generation, validation, hash management
- `/opt/codeguards-mcp/.state/guard_hashes.json` — Baseline hashes (external, not in repo)
- `/opt/codeguards-mcp/.state/auth_token` — Secret token (external, not in repo)
- `.git/hooks/pre-commit` — Hook script that validates protected file changes

### Hook script (sketch)

```bash
#!/bin/bash
# Pre-commit hook: block unauthorized changes to protected files

PROTECTED=(
  "crates/architecture-tests/src/code_quality_test.rs"
  "crates/architecture-tests/src/tracing_instrument.rs"
  "crates/architecture-tests/src/no_unwrap.rs"
  "crates/architecture-tests/src/dependency_guard.rs"
  "crates/architecture-tests/src/credential_sanitization.rs"
  "crates/architecture-tests/src/forbidden_phrases.rs"
  ".planning/ARCHITECTURE.md"
  "CLAUDE.md"
)

# Check if any protected file is staged
changed=0
for f in "${PROTECTED[@]}"; do
  if git diff --cached --name-only | grep -q "^${f}$"; then
    changed=1
    break
  fi
done

if [ "$changed" -eq 0 ]; then
  exit 0  # No protected files changed, allow
fi

# Protected file changed — require auth token in commit message
commit_msg=$(cat "$GIT_DIR/COMMIT_EDITMSG" 2>/dev/null || echo "")
token_file="/opt/codeguards-mcp/.state/auth_token"

if [ ! -f "$token_file" ]; then
  echo "ERROR: MCP auth token not found. Run 'codeguards-mcp init' first."
  exit 1
fi

token=$(cat "$token_file")
pattern="\\[GUARD-AUTH:${token}\\]"

if echo "$commit_msg" | grep -qP "$pattern"; then
  exit 0  # Authorized change
fi

echo ""
echo "ERROR: Protected architecture files were modified without authorization."
echo "This commit changes guard or architecture files, which requires explicit"
echo "authorization. Include [GUARD-AUTH:<token>] in your commit message."
echo ""
echo "To get the current token: codeguards-mcp auth-token"
echo ""
echo "If you are deliberately updating guards, run:"
echo "  codeguards-mcp auth-token"
echo "  git commit -m 'your message [GUARD-AUTH:<token>]'"
echo ""
exit 1
```

### MCP auth module (sketch)

```python
# /opt/codeguards-mcp/auth.py
import hashlib
import json
import os
import secrets
from pathlib import Path

STATE_DIR = Path("/opt/codeguards-mcp/.state")
HASH_FILE = STATE_DIR / "guard_hashes.json"
TOKEN_FILE = STATE_DIR / "auth_token"

PROTECTED_FILES = [
    "crates/architecture-tests/src/code_quality_test.rs",
    "crates/architecture-tests/src/tracing_instrument.rs",
    "crates/architecture-tests/src/no_unwrap.rs",
    "crates/architecture-tests/src/dependency_guard.rs",
    "crates/architecture-tests/src/credential_sanitization.rs",
    "crates/architecture-tests/src/forbidden_phrases.rs",
    ".planning/ARCHITECTURE.md",
    "CLAUDE.md",
]

def init(project_root: Path):
    """Initialize token and baseline hashes."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not TOKEN_FILE.exists():
        TOKEN_FILE.write_text(secrets.token_hex(32))
    rehash(project_root)

def get_token() -> str:
    return TOKEN_FILE.read_text().strip()

def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def rehash(project_root: Path):
    """Update baseline hashes for all protected files."""
    hashes = {}
    for rel in PROTECTED_FILES:
        full = project_root / rel
        if full.exists():
            hashes[rel] = file_hash(full)
    HASH_FILE.write_text(json.dumps(hashes, indent=2))

def check_drift(project_root: Path) -> list[str]:
    """Check if any protected file has changed from baseline."""
    if not HASH_FILE.exists():
        return ["MCP state not initialized — run 'codeguards-mcp init'"]
    baseline = json.loads(HASH_FILE.read_text())
    drift = []
    for rel, expected in baseline.items():
        full = project_root / rel
        if not full.exists():
            drift.append(f"MISSING: {rel} (was expected)")
        elif file_hash(full) != expected:
            drift.append(f"MODIFIED: {rel} (hash mismatch — possible guard drift)")
    return drift
```

---

## Why This Works

1. **Models can't guess the token** — it's a 64-char hex string stored outside
   the repo, never shown to the model.
2. **Models can't edit the hash file** — it's in the MCP's external state dir,
   not in the git repo.
3. **Drift is detected even if the guard "passes"** — the MCP checks hashes
   independently of test results.
4. **Humans can still change guards deliberately** — just get the token and
   include it in the commit message.
5. **No false positives** — only changes to the specific protected files
   trigger the check.

---

## Integration with Existing Workflow

The MCP server already runs `cargo test -p architecture-tests` as part of its
checks. The auth module adds one more check: hash verification of protected
files. The full report would include:

```
=== Architecture Guard Status ===
✅ code_quality_guard — pass
✅ tracing_instrument_guard — pass
✅ no_unwrap_guard — pass
✅ dependency_guard — pass
⚠️  DRIFT DETECTED: crates/architecture-tests/src/code_quality_test.rs
    Hash mismatch — file was modified without [GUARD-AUTH:...] authorization
    Baseline: abc123...
    Current:  def456...
```

This makes drift visible even if the model successfully edited the guard to
make tests pass.

---

## Open Questions

1. **Token rotation** — Should the token be rotated periodically, or is
   one-time generation sufficient? (Rotation adds security but also friction.)
2. **CI integration** — Should CI also check hashes? (Yes, but CI needs access
   to the token file, which means storing it as a secret.)
3. **Exemption workflow** — When a guard change is legitimate (e.g., raising
   `SOFT_FN_LINES` from 50 to 80), the human authorizes it with the token.
   Should the MCP also require a reason comment? (Probably — "why was this
   guard relaxed?")
