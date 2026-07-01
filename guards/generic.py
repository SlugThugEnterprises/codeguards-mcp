"""Generic guards — work on any codebase, any language.

Each guard maps to a principle from a senior engineering code audit:
  Architecture — SOC, SRP, layering, coupling
  Code Quality — smells, DRY, naming, dead code
  Complexity   — cyclomatic, nesting, parameter count
  Security     — credential leaks, unsafe patterns
  Maintainability — commented-out code, documentation gaps

Language-specific parsing is provided by plugins (see ``plugins/python.py``
and ``plugins/rust.py``) via the ``function_blocks`` and ``missing_docs``
capabilities. Generic guards consult ``get_global_registry().get_extractor``
when they need language-aware knowledge, and fall back to language-agnostic
heuristics (e.g., a brace-counter for function lengths) for unknown languages.
The core never branches on ``path.suffix`` directly any more — the plugin
layer owns the language-specific knowledge.
"""

import re
from collections import Counter
from pathlib import Path

import constants

from fixes import (
    fix_file_length,
    fix_function_length,
    fix_god_file,
    fix_deep_nesting,
    fix_parameter_count,
    fix_swallowed_error,
    fix_no_stubs,
    fix_hardcoded_value,
    fix_missing_docs,
    fix_magic_number,
    fix_duplicated_code,
)


# ──────────────────────────────────────────────
# Path utilities
# ──────────────────────────────────────────────

def _is_test_path(path: Path) -> bool:
    """Whether ``path`` looks like a test file — used to skip checks that
    produce false positives on test fixtures and mock data.

    Matches common naming conventions: ``tests/``/``test/`` directories,
    ``test_*`` prefixes, and language-specific suffixes like ``_test.py``,
    ``_test.rs``, ``.test.ts``, ``.spec.js``.
    """
    p = str(path)
    name = path.name
    if "/tests/" in p or "/test/" in p or p.startswith("tests/") or p.startswith("test/"):
        return True
    if name.startswith("test_") or name.endswith((
        "_test.py", "_test.rs", "_tests.rs",
        ".test.ts", ".test.js", ".spec.ts", ".spec.js",
    )):
        return True
    return False


# ──────────────────────────────────────────────
# Plugin extractor lookup — language-agnostic helpers
# ──────────────────────────────────────────────

def _extractor_for(capability: str, file_ext: str):
    """Look up a plugin-registered extractor. Returns None if the plugins
    module isn't loaded yet or no plugin registered for this capability/ext.

    Generic guards never crash on a missing registry — they fall through
    to language-agnostic heuristics, so tests that import generic.py
    without first running ``load_plugins()`` still exercise the fallback
    paths.
    """
    try:
        from plugins import get_global_registry
        return get_global_registry().get_extractor(capability, file_ext)
    except Exception:
        return None


# ──────────────────────────────────────────────
# Architecture — SOC, SRP, modularity
# ──────────────────────────────────────────────

def check_file_length(path: Path, content: str, cfg: dict) -> list[dict]:
    """Files exceeding max lines break SRP — too many responsibilities."""
    if not cfg.get("enabled", True):
        return []
    is_test = ("/tests/" in str(path) or "/test/" in str(path) or
               str(path).endswith("_test.rs") or str(path).endswith("_test.py"))
    max_lines = cfg.get("max_test" if is_test else "max_prod", 200)
    line_count = content.count("\n") + 1
    if line_count > max_lines:
        return [{"file": str(path), "line": 1,
                 "message": f"File exceeds {max_lines} lines ({line_count}) — split into smaller modules (SRP)",
                 "guard": "file_length", "principle": "SOC",
                 "fix": fix_file_length(path, content, line_count, max_lines)}]
    return []


# Pre-compile brace-delimited function-start pattern once at module load.
_BRACED_FN_START_RE = re.compile(
    r"^\s*(?:pub\s+|export\s+|public\s+)?(?:async\s+|static\s+)?(?:unsafe\s+)?"
    r"(?:fn|function|func|def)\s+",
    re.IGNORECASE,
)

# Pre-compile function signature pattern for parameter counting.
_FN_SIG_RE = re.compile(
    r"^\s*(?:pub\s+|export\s+|public\s+)?(?:async\s+)?(?:unsafe\s+)?"
    r"(?:fn|def|function|func)\s+(\w+)\s*\(([^)]*)\)",
    re.MULTILINE | re.IGNORECASE,
)


def _brace_counter_function_lengths(path: Path, content: str, max_fn: int) -> list[dict]:
    """Fallback function-length detector — brace-counted blocks.

    Used for any language without a registered ``function_blocks`` extractor.
    Catches Rust / JS / C++ / Go / C-style code by tracking matched braces.
    """
    violations: list[dict] = []
    lines = content.split("\n")
    i = 0
    while i < len(lines):
        if _BRACED_FN_START_RE.match(lines[i]):
            start = i
            depth = 0
            seen_open = False
            end = start
            for j in range(start, len(lines)):
                for c in lines[j]:
                    if c == "{":
                        depth += 1
                        seen_open = True
                    elif c == "}":
                        depth -= 1
                if seen_open and depth == 0:
                    end = j
                    break
                if j == len(lines) - 1:
                    end = j
            fn_lines = end - start + 1
            if fn_lines > max_fn:
                func_name = lines[start].strip()[:60]
                violations.append({"file": str(path), "line": start + 1,
                    "message": f"Block exceeds {max_fn} lines ({fn_lines}) — split into smaller units",
                    "guard": "function_length", "principle": "SRP/Modular"})
                i = end
        i += 1
    return violations


def check_function_length(path: Path, content: str, cfg: dict) -> list[dict]:
    """Functions exceeding max lines — too many responsibilities, hard to test.

    Strategy:
      1. Consult the plugin registry for a ``function_blocks`` extractor
         scoped to ``path.suffix``. Python ships one (plugins/python.py);
         add more by registering extractors for other languages.
      2. If no extractor is registered, fall back to a brace-counter that
         works for any C-style language (Rust, JS, C++, Go, etc.).

    The core never branches on file extension directly — the plugin layer
    owns the language-specific knowledge.
    """
    if not cfg.get("enabled", True):
        return []
    max_fn = cfg.get("max", 50)
    extractor = _extractor_for("function_blocks", path.suffix)
    if extractor is not None:
        try:
            blocks = extractor(content) or []
        except Exception:
            blocks = []
        violations: list[dict] = []
        for b in blocks:
            if b["length"] > max_fn:
                violations.append({"file": str(path), "line": b["start_line"] + 1,
                    "message": f"Function `{b['name']}` exceeds {max_fn} lines ({b['length']}) — split into smaller units",
                    "guard": "function_length", "principle": "SRP/Modular"})
        return violations
    # Fallback: brace-counter works for Rust/JS/C++/Go/etc.
    return _brace_counter_function_lengths(path, content, max_fn)


# Pre-compile god-file pub/import patterns.
_GOD_FILE_PUB_RE = re.compile(
    r"^\s*(pub\s+)(fn|struct|enum|trait|mod|type|const|static)\s"
    r"|^\s*(export\s+)(function|class|const|interface|type|enum)\s"
    r"|^\s*(def\s+\w+|class\s+\w+)\s*(?:\(|:)",
    re.MULTILINE,
)
_GOD_FILE_IMPORTS_RE = re.compile(
    r"^\s*(use\s+[\w:]+)"
    r"|^\s*(import\s+[\w.]+)"
    r"|^\s*(require\(|from\s+[\w.]+\s+import)",
    re.MULTILINE,
)


def check_god_file(path: Path, content: str, cfg: dict) -> list[dict]:
    """God files have too many imports or public items — SRP violation."""
    if not cfg.get("enabled", True):
        return []
    violations: list[dict] = []
    max_public = cfg.get("max_public_items", 15)
    max_imports = cfg.get("max_imports", 20)

    if len(_GOD_FILE_PUB_RE.findall(content)) > max_public:
        violations.append({"file": str(path), "line": 1,
            "message": f"Too many public items (max {max_public}) — likely god file, split into modules",
            "guard": "god_file", "principle": "SRP"})
    if len(_GOD_FILE_IMPORTS_RE.findall(content)) > max_imports:
        violations.append({"file": str(path), "line": 1,
            "message": f"Too many imports (max {max_imports}) — high coupling, split into modules",
            "guard": "god_file", "principle": "DRY/Modular"})
    return violations


# ──────────────────────────────────────────────
# Code Quality — smells, DRY, naming
# ──────────────────────────────────────────────

def check_forbidden_phrases(path: Path, content: str, cfg: dict) -> list[dict]:
    """No weasel words — forces concrete, defensible language."""
    if not cfg.get("enabled", True):
        return []
    violations: list[dict] = []
    lines = content.split("\n")
    for entry in cfg.get("patterns", []):
        pat, msg = entry.get("pattern", ""), entry.get("message", "")
        try:
            re_obj = re.compile(pat, re.IGNORECASE)
        except re.error:
            continue
        for m in re_obj.finditer(content):
            line_num = content[:m.start()].count("\n") + 1
            line = lines[line_num - 1] if line_num <= len(lines) else ""
            # Skip false positive when match is inside a raw regex string.
            stripped = line.strip()
            if stripped.startswith("r\"") or stripped.startswith("r'"):
                continue
            violations.append({"file": str(path),
                "line": line_num,
                "message": f"Forbidden phrase `{m.group()}` — {msg}",
                "guard": "forbidden_phrases", "principle": "Code Quality"})
    return violations


# Glob import patterns, pre-compiled once.
_GLOB_IMPORT_PATTERNS = [
    re.compile(p, re.MULTILINE) for p in (
        r"^\s*(use\s+[\w:]+\s*::\s*\*)",                          # Rust
        r"^\s*(from\s+[\w.]+\s+import\s+\*)",                       # Python
        r"^\s*(import\s+[\w.]+\s*\.\s*\*)",                         # JS/TS
    )
]


def check_glob_imports(path: Path, content: str, cfg: dict) -> list[dict]:
    """No wildcard imports — imports should be explicit."""
    if not cfg.get("enabled", True):
        return []
    violations: list[dict] = []
    for pat in _GLOB_IMPORT_PATTERNS:
        for m in pat.finditer(content):
            violations.append({"file": str(path),
                "line": content[:m.start()].count("\n") + 1,
                "message": "Glob import — import specific names instead",
                "guard": "glob_imports", "principle": "Modular"})
    return violations


# Debug-statement patterns, pre-compiled once.
_DEBUG_PATTERNS = [
    (re.compile(p, re.MULTILINE), msg) for p, msg in (
        (r"^\s*println!\(", "use tracing::info! or log::info!"),
        (r"^\s*dbg!\(", "use tracing::debug! or remove"),
        (r"^\s*(?:eprintln!|eprint!)\(", "use tracing::error!"),
        (r"^\s*print\((?!.*logger|.*logging)", "use logger.info() or structured logging"),
        (r"^\s*console\.(log|debug|warn)\(", "use structured logger"),
        (r"^\s*(?:log|fmt)\.(Print|Fprint)(?:f|ln)?\(", "use structured logger"),
    )
]


def check_debug_statements(path: Path, content: str, cfg: dict) -> list[dict]:
    """No debug output in production code — use structured logging."""
    if not cfg.get("enabled", True):
        return []
    violations: list[dict] = []
    for pat, msg in _DEBUG_PATTERNS:
        for m in pat.finditer(content):
            violations.append({"file": str(path),
                "line": content[:m.start()].count("\n") + 1,
                "message": f"Debug statement — {msg}",
                "guard": "debug_statements", "principle": "Logging"})
    return violations


_CODE_LIKE_RE = re.compile(
    r"[{}();=\[\]]"
    r"|^\s*(?:if|for|while|fn|def|function|return|let|const|var|match)\b"
)


def check_commented_code(path: Path, content: str, cfg: dict) -> list[dict]:
    """No large blocks of commented-out code — use version control."""
    if not cfg.get("enabled", True):
        return []
    violations: list[dict] = []
    threshold = cfg.get("min_lines", 5)
    lines = content.split("\n")
    in_comment_block = False
    comment_start = 0
    comment_lines = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        is_comment = stripped.startswith("//") or stripped.startswith("#")
        if not is_comment and stripped.startswith("/*"):
            in_comment_block = True
            comment_start = i
            comment_lines = 0
            continue
        if in_comment_block:
            comment_lines += 1
            if "*/" in stripped:
                in_comment_block = False
            continue
        if is_comment and _CODE_LIKE_RE.search(line):
            comment_lines += 1
            if comment_lines == 1:
                comment_start = i
            if comment_lines >= threshold:
                violations.append({"file": str(path), "line": comment_start + 1,
                    "message": "Commented-out code block — remove or use version control",
                    "guard": "commented_code", "principle": "Maintainability"})
                comment_lines = 0
        else:
            comment_lines = 0
    return violations


_MAGIC_RE = re.compile(r"(?<![a-zA-Z_#\"])(?<!\w)(-?\d{2,})(?!\w)")
_SKIP_NUMBERS = frozenset({0, 1, -1, 2, 10, 100, 1000})
_MAGIC_SKIP_PATTERNS = [
    re.compile(p) for p in (
        r"^\s*(use|import|mod|const|static|let mut|let\s+\w+:|function\s+\w+|///|//)",
        r"array|index|idx|\.push\(",
        r"\b(max|min)_(prod|test|fn|lines|depth|params|deps|score|ratio)\b",
        r"\b(max|min)\s*[=:]\s*\d+",
        r"\bassert(_eq|_ne|_gt|_lt|_ge|_le)?\s*\(",
        r"\bself\.assert",
        r"^\s*(?:#\s*|//\s*).*\d+",
    )
]


def check_magic_numbers(path: Path, content: str, cfg: dict) -> list[dict]:
    """No unexplained numeric literals — use named constants."""
    if not cfg.get("enabled", True):
        return []
    if "constants.py" in str(path):
        return []
    lines = content.split("\n")
    violations: list[dict] = []
    for m in _MAGIC_RE.finditer(content):
        num = int(m.group())
        if num in _SKIP_NUMBERS:
            continue
        line_num = content[:m.start()].count("\n") + 1
        line = lines[line_num - 1] if line_num <= len(lines) else ""
        if any(pat.search(line) for pat in _MAGIC_SKIP_PATTERNS):
            continue
        violations.append({"file": str(path), "line": line_num,
            "message": f"Magic number {num} — extract to a named constant",
            "guard": "magic_numbers", "principle": "Code Quality"})
    return violations


def check_duplicated_code(path: Path, content: str, cfg: dict) -> list[dict]:
    """Detect copy-paste via n-gram similarity — DRY violation."""
    if not cfg.get("enabled", True):
        return []
    violations: list[dict] = []
    n = cfg.get("n_gram_size", 5)
    min_repeats = cfg.get("min_repeats", 2)
    min_line_len = cfg.get("min_line_len", 10)

    lines = []
    for l in content.split("\n"):
        stripped = l.strip()
        if len(stripped) < min_line_len:
            continue
        if stripped.startswith("//") or stripped.startswith("#") or stripped.startswith("--"):
            continue
        if stripped.startswith("/*") or stripped.startswith("*") or stripped.startswith("*/"):
            continue
        lines.append(stripped)

    if len(lines) < n:
        return violations

    n_grams = ["\n".join(lines[i:i + n]) for i in range(len(lines) - n + 1)]
    counter = Counter(n_grams)
    for gram, count in counter.most_common():
        if count >= min_repeats and len(gram) > 30:
            idx = n_grams.index(gram)
            violations.append({"file": str(path), "line": idx + 1,
                "message": f"Duplicated code block (repeated {count}x, {n} lines each) — extract into shared function",
                "guard": "duplicated_code", "principle": "DRY"})
            if len(violations) >= 5:
                break
    return violations


def check_unsafe_patterns(path: Path, content: str, cfg: dict) -> list[dict]:
    """Flag unsafe operations — eval, exec, raw SQL, unchecked access.

    Skips test files — fixtures intentionally use mock unsafe-looking code."""
    if not cfg.get("enabled", True):
        return []
    if _is_test_path(path):
        return []
    violations: list[dict] = []
    patterns = [
        (r"\beval\s*\(", "eval() — code injection risk"),
        (r"\bexec\s*\(", "exec() — arbitrary code execution"),
        (r"\bunsafe\s*\{", "unsafe block — requires explicit justification comment"),
        (r"\.unwrap_unchecked\(", "unchecked unwrap — potential panic"),
    ]
    for pat_str, msg in patterns:
        re_obj = re.compile(pat_str)
        for m in re_obj.finditer(content):
            violations.append({"file": str(path),
                "line": content[:m.start()].count("\n") + 1,
                "message": f"{m.group().strip()[:30]} — {msg}",
                "guard": "unsafe_patterns", "severity": "error",
                "principle": "Security"})
    return violations


# ──────────────────────────────────────────────
# Complexity — nesting depth, parameter count
# ──────────────────────────────────────────────

_NEST_INDENT_RE_4 = re.compile(r"^(\s{4,})")
_NEST_INDENT_RE_2 = re.compile(r"^(\s{2,})")
_NEST_INDENT_RE_T = re.compile(r"^(\t+)")


def check_deep_nesting(path: Path, content: str, cfg: dict) -> list[dict]:
    """No deep nesting — flag lines with >3 levels of indentation/braces.

    Skips continuation lines in multi-line function signatures (not real nesting)."""
    if not cfg.get("enabled", True):
        return []
    violations: list[dict] = []
    max_nest = cfg.get("max_depth", 4)
    lines = content.split("\n")

    in_params = False
    paren_depth = 0

    nest_styles = (
        ("4-spaces", _NEST_INDENT_RE_4, 4),
        ("2-spaces", _NEST_INDENT_RE_2, 2),
        ("tabs", _NEST_INDENT_RE_T, 1),
    )

    for style, re_obj, divisor in nest_styles:
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == "" or stripped.startswith("//") or stripped.startswith("#"):
                continue

            if paren_depth > 0:
                in_params = True
            for c in stripped:
                if c == "(":
                    paren_depth += 1
                    in_params = True
                elif c == ")":
                    paren_depth -= 1
            if paren_depth <= 0:
                in_params = False
                paren_depth = 0
            if in_params:
                continue

            m = re_obj.match(line)
            if m:
                depth = len(m.group(1)) // divisor
                if depth > max_nest:
                    violations.append({"file": str(path), "line": i + 1,
                        "message": f"Nesting depth {depth} exceeds max {max_nest} — refactor with early returns or helper functions",
                        "guard": "deep_nesting", "principle": "Complexity"})
                    break
        if violations:
            break
    return violations


def check_parameter_count(path: Path, content: str, cfg: dict) -> list[dict]:
    """Functions with too many parameters — hard to understand, easy to misorder."""
    if not cfg.get("enabled", True):
        return []
    violations: list[dict] = []
    max_params = cfg.get("max_params", 5)

    for m in _FN_SIG_RE.finditer(content):
        params = m.group(2).strip()
        if not params:
            continue
        count = _count_params(params)
        if count > max_params:
            violations.append({"file": str(path),
                "line": content[:m.start()].count("\n") + 1,
                "message": f"Function `{m.group(1)}` has {count} parameters (max {max_params}) — consider grouping into a struct/options object",
                "guard": "parameter_count", "principle": "Complexity"})
    return violations


def _count_params(params_str: str) -> int:
    """Rough param count with angle-bracket awareness."""
    depth = 0
    count = 1 if params_str.strip() else 0
    for c in params_str:
        if c in "<([{":
            depth += 1
        elif c in ">)]}":
            depth -= 1
        elif c == "," and depth == 0:
            count += 1
    return count


# ──────────────────────────────────────────────
# Security — credential leaks
# ──────────────────────────────────────────────

def check_credentials(path: Path, content: str, cfg: dict) -> list[dict]:
    """No API keys, tokens, or secrets in source code.

    Skips test files — fixtures contain mock credentials."""
    if not cfg.get("enabled", True):
        return []
    if _is_test_path(path):
        return []
    violations: list[dict] = []
    for entry in cfg.get("patterns", []):
        pat, msg = entry.get("pattern", ""), entry.get("message", "")
        try:
            re_obj = re.compile(pat)
        except re.error:
            continue
        for m in re_obj.finditer(content):
            violations.append({"file": str(path),
                "line": content[:m.start()].count("\n") + 1,
                "message": msg, "severity": "error",
                "guard": "credentials", "principle": "Security"})
    return violations


# ──────────────────────────────────────────────
# Maintainability — documentation, dead code
# ──────────────────────────────────────────────

def check_action_items(path: Path, content: str, cfg: dict) -> list[dict]:
    """TODO/FIXME/HACK/ACTION must link to a tracking issue."""
    if not cfg.get("enabled", True):
        return []
    if not cfg.get("require_issue", True):
        return []
    violations: list[dict] = []

    allowed = cfg.get("allowed_pattern", r"//\s*(TODO|FIXME|HACK|ACTION)\(#\d+\):")
    scan_pattern = cfg.get("scan_pattern", r"//\s*(TODO|FIXME|HACK|ACTION)\b")

    try:
        allowed_re = re.compile(allowed)
        scan_re = re.compile(scan_pattern)
    except re.error:
        return violations

    lines = content.split("\n")
    for m in scan_re.finditer(content):
        line_num = content[:m.start()].count("\n")
        line = lines[line_num] if line_num < len(lines) else ""
        if allowed_re.search(line):
            continue
        violations.append({"file": str(path),
            "line": content[:m.start()].count("\n") + 1,
            "message": "Action item without issue link — use `TODO(#123): description`",
            "guard": "action_items", "principle": "Maintainability"})
    return violations


# ──────────────────────────────────────────────
# Error Handling — no swallowed errors, error context
# ──────────────────────────────────────────────

def check_swallowed_errors(path: Path, content: str, cfg: dict) -> list[dict]:
    """Empty catch/except blocks — errors eaten silently, nightmare to debug.

    Skips test files — fixtures intentionally use ``except: pass`` to
    isolate failure modes."""
    if not cfg.get("enabled", True):
        return []
    if _is_test_path(path):
        return []
    violations: list[dict] = []

    patterns = [
        (r"(?s)_\s*=>\s*\{\s*\}", "Empty match arm — silently drops error, handle or propagate it"),
        (r"(?s)Err\(\s*_\s*\)\s*=>\s*\{\s*\}", "Swallowed Err — handle the error or add context to the return"),
        (r"except\s*:\s*pass", "Bare `except: pass` — swallows all errors including KeyboardInterrupt"),
        (r"(?s)except\s+Exception\s*:\s*pass", "`except Exception: pass` — silently drops real errors"),
        (r"(?s)except\s+\w+\s*:\s*pass", "Empty except block — at minimum log the error"),
        (r"(?s)catch\s*\(\s*\w*\s*\)\s*\{\s*\}", "Empty catch block — silently swallows error"),
        (r"(?s)catch\s*\{\s*\}", "Empty catch block — silently swallows error"),
        (r"(?s)\.catch\(\s*\(\s*\)\s*=>\s*\{\s*\}\s*\)", "Empty promise catch — swallows async errors"),
    ]
    for pat_str, msg in patterns:
        re_obj = re.compile(pat_str)
        for m in re_obj.finditer(content):
            violations.append({"file": str(path),
                "line": content[:m.start()].count("\n") + 1,
                "message": f"{m.group()[:40].strip()} — {msg}",
                "guard": "swallowed_errors", "principle": "Error Handling"})
    return violations


def check_no_stubs(path: Path, content: str, cfg: dict) -> list[dict]:
    """No placeholder/stub implementations in production code."""
    if not cfg.get("enabled", True):
        return []
    if _is_test_path(path):
        return []
    violations: list[dict] = []

    patterns = [
        (r"\btodo!\s*\(", "stub `todo!()` in production code"),
        (r"\bunimplemented!\s*\(", "stub `unimplemented!()` in production code"),
        (r"\bunreachable!\s*\(\s*\"(?:not implemented|TODO|stub)", "stub `unreachable!()` with placeholder message"),
        (r"^\s*pass\s*#\s*(?:TODO|FIXME|stub|placeholder)", "Stub pass with TODO — implement or remove"),
        (r"\braise\s+NotImplementedError\b", "Stub `raise NotImplementedError` — implement before shipping"),
        (r"\bthrow\s+new\s+Error\s*\(\s*[\"'](?:not\s+implemented|TODO|stub)", "Stub error — implement before shipping"),
        (r"(?i)#\s*FIXME.*(?:stub|placeholder|replace\s+me)", "Stub comment — implement or remove"),
    ]
    for pat_str, msg in patterns:
        re_obj = re.compile(pat_str, re.IGNORECASE)
        for m in re_obj.finditer(content):
            line = content[:m.start()].count("\n") + 1
            line_text = content.split("\n")[line - 1].strip()
            if line_text.startswith("//") or line_text.startswith("#") or line_text.startswith("///"):
                if not any(w in line_text.lower() for w in ("stub", "placeholder", "replace me")):
                    continue
            violations.append({"file": str(path), "line": line,
                "message": f"{m.group()[:40].strip()} — {msg}",
                "guard": "no_stubs", "principle": "Testing"})
    return violations


# ──────────────────────────────────────────────
# Configuration — hardcoded values
# ──────────────────────────────────────────────

_HARDCODED_PATTERNS = [
    re.compile(p, re.MULTILINE) for p in (
        r"""(?<!\w)["'](https?://(?!localhost|127\.0\.0\.1|0\.0\.0\.0)[^"']{8,})['"]""",
        r"""(?<!\w)["']((?!127\.|0\.0\.|::1|192\.168\.|10\.)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})['"]""",
        r"""(?i)(?:\bport\s*[=:]\s*|:\s*)(\d{4,5})\b""",
        r"""(?i)(?:\btimeout\s*[=:]\s*|\btimeout_secs?\s*[=:]\s*)(\d{2,})\b""",
    )
]
_HARDCODED_SKIP_RE = re.compile(
    r"^\s*(?:const|static|let\s+\w+:|import|use)\s",
)
_HARDCODED_MESSAGES = (
    "Hardcoded URL — extract to config or environment variable",
    "Hardcoded IP address — extract to config",
    "Hardcoded port — extract to config constant",
    "Hardcoded timeout — extract to config constant",
)


def check_hardcoded_values(path: Path, content: str, cfg: dict) -> list[dict]:
    """Configuration values as raw literals — should come from config/env.

    Skips test files — fixtures contain hardcoded URLs/ports as inputs."""
    if not cfg.get("enabled", True):
        return []
    if _is_test_path(path):
        return []
    violations: list[dict] = []
    lines = content.split("\n")
    for re_obj, msg in zip(_HARDCODED_PATTERNS, _HARDCODED_MESSAGES):
        for m in re_obj.finditer(content):
            line = content[:m.start()].count("\n") + 1
            line_text = lines[line - 1] if line <= len(lines) else ""
            if _HARDCODED_SKIP_RE.match(line_text):
                continue
            violations.append({"file": str(path), "line": line,
                "message": f"Hardcoded config value `{m.group(1)[:30]}` — {msg}",
                "guard": "hardcoded_values", "principle": "Maintainability"})
    return violations


# ──────────────────────────────────────────────
# Documentation gaps — delegated to plugins.
# ──────────────────────────────────────────────

def check_missing_docs(path: Path, content: str, cfg: dict) -> list[dict]:
    """Public items without docstrings — poor maintainability signal.

    Looks up a plugin-registered ``missing_docs`` extractor for the
    file's extension. Currently Python and Rust both ship extractors
    (see plugins/python.py and plugins/rust.py); other languages get
    no check until a plugin registers one.

    The core never branches on file extension directly — that knowledge
    lives in the plugin layer.
    """
    if not cfg.get("enabled", True):
        return []
    extractor = _extractor_for("missing_docs", path.suffix)
    if extractor is None:
        return []  # no plugin handles this language
    try:
        items = extractor(content) or []
    except Exception:
        return []
    violations: list[dict] = []
    for item in items:
        violations.append({"file": str(path), "line": item["line"] + 1,
            "message": f"Public {item['type']} `{item['name']}` has no doc comment — add documentation",
            "guard": "missing_docs", "principle": "Maintainability"})
    return violations


# ──────────────────────────────────────────────
# Architectural completeness — absence bugs
# ──────────────────────────────────────────────

def check_entry_point_init(path: Path, content: str, cfg: dict) -> list[dict]:
    """Binary entry points must call required initialization functions.

    Catches absence bugs where the AI writes a main() function but forgets
    to initialize critical infrastructure (logging, config validation,
    panic hooks, etc.) before starting services.

    Configured via .codeguards.yaml:

        entry_point_init:
          required_calls:
            - pattern: "logging::init"    # Rust
              before: "tokio::runtime"
            - pattern: "logging.basicConfig"  # Python
              before: "app.run"
            - pattern: "logger\\.configure"  # Node
              before: "server\\.listen"

    The guard checks that the required pattern appears in the file before
    the service-start pattern. Skips test files.
    """
    if not cfg.get("enabled", True):
        return []
    if _is_test_path(path):
        return []

    required_calls = cfg.get("required_calls", [])
    if not required_calls:
        return []  # No init requirements configured for this project

    violations: list[dict] = []

    # Check if this file contains a main/entry point
    is_entry_point = False
    entry_patterns = [
        r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+main\s*\(",       # Rust
        r"^\s*(?:async\s+)?def\s+main\s*\(",                  # Python
        r"^\s*function\s+main\s*\(",                          # JS/TS
        r'\.listen\s*\(',                                      # Node servers
        r'\.serve\s*\(',                                       # Generic servers
    ]
    for pat in entry_patterns:
        if re.search(pat, content):
            is_entry_point = True
            break

    if not is_entry_point:
        return []  # Not an entry point file, skip

    for req in required_calls:
        init_pattern = req.get("pattern", "")
        before_pattern = req.get("before", "")
        if not init_pattern or not before_pattern:
            continue

        try:
            init_re = re.compile(init_pattern)
            before_re = re.compile(before_pattern)
        except re.error:
            continue

        init_match = init_re.search(content)
        before_match = before_re.search(content)

        if before_match and not init_match:
            violations.append({
                "file": str(path),
                "line": before_match.start() and content[:before_match.start()].count("\n") + 1 or 1,
                "message": (
                    f"Entry point calls `{before_pattern}` but missing required "
                    f"initialization `{init_pattern}` — add initialization before "
                    f"starting the service (absence bug: infrastructure not initialized)"
                ),
                "guard": "entry_point_init",
                "principle": "Architectural Completeness",
                "severity": "error",
            })
        elif init_match and before_match and init_match.start() > before_match.start():
            violations.append({
                "file": str(path),
                "line": content[:before_match.start()].count("\n") + 1,
                "message": (
                    f"Initialization `{init_pattern}` appears AFTER `{before_pattern}` "
                    f"— move initialization before service startup"
                ),
                "guard": "entry_point_init",
                "principle": "Architectural Completeness",
                "severity": "error",
            })

    return violations


# ──────────────────────────────────────────────
# All generic guards — registered in __init__.py
# ──────────────────────────────────────────────

ALL_GENERIC_CHECKS = {
    "file_length": check_file_length,
    "function_length": check_function_length,
    "god_file": check_god_file,
    "forbidden_phrases": check_forbidden_phrases,
    "glob_imports": check_glob_imports,
    "debug_statements": check_debug_statements,
    "commented_code": check_commented_code,
    "magic_numbers": check_magic_numbers,
    "duplicated_code": check_duplicated_code,
    "unsafe_patterns": check_unsafe_patterns,
    "deep_nesting": check_deep_nesting,
    "parameter_count": check_parameter_count,
    "credentials": check_credentials,
    "action_items": check_action_items,
    "swallowed_errors": check_swallowed_errors,
    "no_stubs": check_no_stubs,
    "hardcoded_values": check_hardcoded_values,
    "missing_docs": check_missing_docs,
    "entry_point_init": check_entry_point_init,
}


# Auto-load plugins the first time the module is imported, so generic
# guards can find extractors for whatever languages are registered.
# ``load_plugins`` is idempotent — calling it again just overwrites the
# registry with whatever's currently on disk. Tests that want a clean
# registry can call ``_set_global_registry`` directly or pass their own.
try:
    from plugins import load_plugins
    load_plugins()
except Exception:
    # Plugins failing to load shouldn't break generic.py import — falls
    # back to brace-counter and no-op for missing_docs.
    pass
