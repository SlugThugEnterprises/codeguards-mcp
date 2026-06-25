"""Generic guards — work on any codebase, any language.

Each guard maps to a principle from a senior engineering code audit:
  Architecture — SOC, SRP, layering, coupling
  Code Quality — smells, DRY, naming, dead code
  Complexity   — cyclomatic, nesting, parameter count
  Security     — credential leaks, unsafe patterns
  Maintainability — commented-out code, documentation gaps
"""

import re
from collections import Counter
from pathlib import Path


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
                 "guard": "file_length", "principle": "SOC"}]
    return []


def check_function_length(path: Path, content: str, cfg: dict) -> list[dict]:
    """Functions exceeding max lines — too many responsibilities, hard to test."""
    if not cfg.get("enabled", True):
        return []
    max_fn = cfg.get("max", 50)
    violations = []
    lines = content.split("\n")
    fn_patterns = [
        r"^\s*(?:pub\s+|export\s+|public\s+)?(?:async\s+|static\s+)?(?:unsafe\s+)?"
        r"(?:fn|def|function|func|class|impl|struct|trait|enum)\s+",
    ]
    fn_re = re.compile("|".join(fn_patterns), re.IGNORECASE)

    i = 0
    while i < len(lines):
        if fn_re.match(lines[i]):
            start = i
            depth = 0
            seen_open = False
            end = start
            for j in range(start, len(lines)):
                for c in lines[j]:
                    if c == '{':
                        depth += 1
                        seen_open = True
                    elif c == '}':
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


def check_god_file(path: Path, content: str, cfg: dict) -> list[dict]:
    """God files have too many imports or public items — SRP violation."""
    if not cfg.get("enabled", True):
        return []
    violations = []
    max_public = cfg.get("max_public_items", 15)
    max_imports = cfg.get("max_imports", 20)

    # Count public items (pub fn, pub struct, export, def/class with docstring)
    pub_patterns = [r"^\s*(pub\s+)(fn|struct|enum|trait|mod|type|const|static)\s",
                    r"^\s*(export\s+)(function|class|const|interface|type|enum)\s",
                    r'^\s*(def\s+\w+|class\s+\w+)\s*(?:\(|:)']
    pub_re = re.compile("|".join(pub_patterns), re.MULTILINE)
    pub_count = len(pub_re.findall(content))
    if pub_count > max_public:
        violations.append({"file": str(path), "line": 1,
            "message": f"Too many public items ({pub_count}, max {max_public}) — likely god file, split into modules",
            "guard": "god_file", "principle": "SRP"})

    # Count imports
    import_patterns = [r"^\s*(use\s+[\w:]+)", r"^\s*(import\s+[\w.]+)", r"^\s*(require\(|from\s+[\w.]+\s+import)"]
    import_re = re.compile("|".join(import_patterns), re.MULTILINE)
    import_count = len(import_re.findall(content))
    if import_count > max_imports:
        violations.append({"file": str(path), "line": 1,
            "message": f"Too many imports ({import_count}, max {max_imports}) — high coupling, split into modules",
            "guard": "god_file", "principle": "DRY/Modular"})
    return violations


# ──────────────────────────────────────────────
# Code Quality — smells, DRY, naming
# ──────────────────────────────────────────────

def check_forbidden_phrases(path: Path, content: str, cfg: dict) -> list[dict]:
    """No weasel words — forces concrete, defensible language."""
    if not cfg.get("enabled", True):
        return []
    violations = []
    for entry in cfg.get("patterns", []):
        pat, msg = entry.get("pattern", ""), entry.get("message", "")
        try:
            re_obj = re.compile(pat, re.IGNORECASE)
        except re.error:
            continue
        for m in re_obj.finditer(content):
            violations.append({"file": str(path),
                "line": content[:m.start()].count("\n") + 1,
                "message": f"Forbidden phrase `{m.group()}` — {msg}",
                "guard": "forbidden_phrases", "principle": "Code Quality"})
    return violations


def check_glob_imports(path: Path, content: str, cfg: dict) -> list[dict]:
    """No wildcard imports — imports should be explicit."""
    if not cfg.get("enabled", True):
        return []
    violations = []
    patterns = [
        r"^\s*(use\s+[\w:]+\s*::\s*\*)",             # Rust
        r"^\s*(from\s+[\w.]+\s+import\s+\*)",         # Python
        r"^\s*(import\s+[\w.]+\s*\.\s*\*)",            # TS/JS
    ]
    for pat in patterns:
        for m in re.compile(pat, re.MULTILINE).finditer(content):
            violations.append({"file": str(path),
                "line": content[:m.start()].count("\n") + 1,
                "message": "Glob import — import specific names instead",
                "guard": "glob_imports", "principle": "Modular"})
    return violations


def check_debug_statements(path: Path, content: str, cfg: dict) -> list[dict]:
    """No debug output in production code — use structured logging."""
    if not cfg.get("enabled", True):
        return []
    violations = []
    patterns = [
        (r"^\s*println!\(", "use tracing::info! or log::info!"),
        (r"^\s*dbg!\(", "use tracing::debug! or remove"),
        (r"^\s*(?:eprintln!|eprint!)\(", "use tracing::error!"),
        (r"^\s*print\((?!.*logger|.*logging)", "use logger.info() or structured logging"),
        (r"^\s*console\.(log|debug|warn)\(", "use structured logger"),
        (r"^\s*(?:log|fmt)\.(Print|Fprint)(?:f|ln)?\(", "use structured logger"),
    ]
    for pat, msg in patterns:
        for m in re.compile(pat, re.MULTILINE).finditer(content):
            line = content[:m.start()].count("\n") + 1
            violations.append({"file": str(path), "line": line,
                "message": f"Debug statement — {msg}",
                "guard": "debug_statements", "principle": "Logging"})
    return violations


def check_commented_code(path: Path, content: str, cfg: dict) -> list[dict]:
    """No large blocks of commented-out code — use version control."""
    if not cfg.get("enabled", True):
        return []
    violations = []
    threshold = cfg.get("min_lines", 5)
    lines = content.split("\n")
    in_comment_block = False
    comment_start = 0
    comment_lines = 0
    code_like = re.compile(r"[{}();=\[\]]|^\s*(?:if|for|while|fn|def|function|return|let|const|var|match)\b")

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
        if is_comment and code_like.search(line):
            comment_lines += 1
            if comment_lines == 1:
                comment_start = i
            if comment_lines >= threshold:
                violations.append({"file": str(path), "line": comment_start + 1,
                    "message": "Commented-out code block — remove or use version control",
                    "guard": "commented_code", "principle": "Maintainability"})
                comment_lines = 0  # Reset to avoid duplicate reports
        else:
            comment_lines = 0
    return violations


def check_magic_numbers(path: Path, content: str, cfg: dict) -> list[dict]:
    """No unexplained numeric literals — use named constants."""
    if not cfg.get("enabled", True):
        return []
    violations = []
    # Skip common non-magic numbers: 0, 1, -1, 2, 100, 1000, array indices
    skip = {0, 1, -1, 2}
    skip_patterns = [r"^\s*(use|import|mod|const|static|let mut|let\s+\w+:|function\s+\w+|///|//)", r"array|index|idx|\.push\("]

    magic_re = re.compile(r"(?<![a-zA-Z_#\"])(?<!\w)(-?\d{2,})(?!\w)")
    for m in magic_re.finditer(content):
        num = int(m.group())
        if num in skip:
            continue
        line_num = content[:m.start()].count("\n") + 1
        line = content.split("\n")[line_num - 1] if line_num <= len(content.split("\n")) else ""
        if any(re.search(p, line) for p in skip_patterns):
            continue
        violations.append({"file": str(path), "line": line_num,
            "message": f"Magic number {num} — extract to a named constant",
            "guard": "magic_numbers", "principle": "Code Quality"})
    return violations


def check_duplicated_code(path: Path, content: str, cfg: dict) -> list[dict]:
    """Detect copy-paste via n-gram similarity — DRY violation."""
    if not cfg.get("enabled", True):
        return []
    violations = []
    n = cfg.get("n_gram_size", 5)
    min_repeats = cfg.get("min_repeats", 2)
    min_line_len = cfg.get("min_line_len", 10)

    # Normalize: strip whitespace, skip short lines and comments
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

    n_grams = []
    for i in range(len(lines) - n + 1):
        n_gram = "\n".join(lines[i:i + n])
        n_grams.append(n_gram)

    counter = Counter(n_grams)
    for gram, count in counter.most_common():
        if count >= min_repeats and len(gram) > 30:
            # Find the first occurrence line
            idx = n_grams.index(gram)
            violations.append({"file": str(path), "line": idx + 1,
                "message": f"Duplicated code block (repeated {count}x, {n} lines each) — extract into shared function",
                "guard": "duplicated_code", "principle": "DRY"})
            if len(violations) >= 5:  # Don't flood
                break
    return violations


def check_unsafe_patterns(path: Path, content: str, cfg: dict) -> list[dict]:
    """Flag unsafe operations — eval, exec, raw SQL, unchecked access."""
    if not cfg.get("enabled", True):
        return []
    violations = []
    patterns = [
        (r"\beval\s*\(", "eval() — code injection risk"),
        (r"\bexec\s*\(", "exec() — arbitrary code execution"),
        (r"\bunsafe\s*\{", "unsafe block — requires explicit justification comment"),
        (r"\.unwrap_unchecked\(", "unchecked unwrap — potential panic"),
    ]
    for pat, msg in patterns:
        for m in re.compile(pat).finditer(content):
            violations.append({"file": str(path),
                "line": content[:m.start()].count("\n") + 1,
                "message": f"{m.group().strip()[:30]} — {msg}",
                "guard": "unsafe_patterns", "severity": "error", "principle": "Security"})
    return violations


# ──────────────────────────────────────────────
# Complexity — nesting depth, parameter count
# ──────────────────────────────────────────────

def check_deep_nesting(path: Path, content: str, cfg: dict) -> list[dict]:
    """No deep nesting — flag lines with >3 levels of indentation/braces."""
    if not cfg.get("enabled", True):
        return []
    violations = []
    max_nest = cfg.get("max_depth", 3)

    nest_counters = {
        "4-spaces": re.compile(r"^(\s{4,})"),
        "2-spaces": re.compile(r"^(\s{2,})"),
        "tabs": re.compile(r"^(\t+)"),
    }

    for style, re_obj in nest_counters.items():
        for i, line in enumerate(content.split("\n")):
            m = re_obj.match(line)
            if m:
                depth = len(m.group(1)) // (4 if style == "4-spaces" else 2 if style == "2-spaces" else 1)
                if depth > max_nest:
                    violations.append({"file": str(path), "line": i + 1,
                        "message": f"Nesting depth {depth} exceeds max {max_nest} — refactor with early returns or helper functions",
                        "guard": "deep_nesting", "principle": "Complexity"})
                    break  # One violation per file is enough for nesting
            if violations:
                break
        if violations:
            break
    return violations


def check_parameter_count(path: Path, content: str, cfg: dict) -> list[dict]:
    """Functions with too many parameters — hard to understand, easy to misorder."""
    if not cfg.get("enabled", True):
        return []
    violations = []
    max_params = cfg.get("max_params", 5)

    # Match function definitions and count params between first ( and )
    fn_re = re.compile(
        r"^\s*(?:pub\s+|export\s+|public\s+)?(?:async\s+)?(?:unsafe\s+)?"
        r"(?:fn|def|function|func)\s+(\w+)\s*\(([^)]*)\)",
        re.MULTILINE | re.IGNORECASE
    )
    for m in fn_re.finditer(content):
        params = m.group(2).strip()
        if not params:
            continue
        # Split on commas, respecting generics angle brackets
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
    """No API keys, tokens, or secrets in source code."""
    if not cfg.get("enabled", True):
        return []
    violations = []
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
    violations = []

    allowed = cfg.get("allowed_pattern", r"//\s*(TODO|FIXME|HACK|ACTION)\(#\d+\):")
    scan_pattern = cfg.get("scan_pattern", r"//\s*(TODO|FIXME|HACK|ACTION)\b")

    try:
        allowed_re = re.compile(allowed)
        scan_re = re.compile(scan_pattern)
    except re.error:
        return violations

    for m in scan_re.finditer(content):
        if allowed_re.search(m.group()):
            continue
        violations.append({"file": str(path),
            "line": content[:m.start()].count("\n") + 1,
            "message": "Action item without issue link — use `TODO(#123): description`",
            "guard": "action_items", "principle": "Maintainability"})
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
}
