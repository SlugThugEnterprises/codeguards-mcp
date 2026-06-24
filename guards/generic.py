"""Generic guards — work on any codebase, any language."""

import re
from pathlib import Path
from typing import Any


def check_file_length(path: Path, content: str, cfg: dict) -> list[dict]:
    """Files shouldn't exceed max lines."""
    if not cfg.get("enabled", True):
        return []
    violations = []
    line_count = content.count("\n") + 1
    is_test = "/tests/" in str(path) or str(path).endswith("_test.rs") or str(path).endswith("_test.py")
    max_lines = cfg.get("max_test" if is_test else "max_prod", 200)
    if line_count > max_lines:
        violations.append({
            "file": str(path),
            "line": 1,
            "message": f"File exceeds {max_lines} lines ({line_count} found) — split into smaller modules",
            "guard": "file_length",
        })
    return violations


def check_function_length(path: Path, content: str, cfg: dict) -> list[dict]:
    """Functions shouldn't exceed max lines."""
    if not cfg.get("enabled", True):
        return []
    max_fn = cfg.get("max", 50)
    violations = []

    lines = content.split("\n")
    fn_re = re.compile(r"^\s*(?:pub\s+|export\s+|public\s+)?(?:async\s+|static\s+)?(?:unsafe\s+)?(?:fn\s+|def\s+|function\s+|func\s+)", re.IGNORECASE)

    i = 0
    while i < len(lines):
        if fn_re.match(lines[i]):
            fn_name = lines[i].strip()
            # Find function body
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
                violations.append({
                    "file": str(path),
                    "line": start + 1,
                    "message": f"Function on line {start + 1} exceeds {max_fn} lines ({fn_lines} found) — split into smaller functions",
                    "guard": "function_length",
                })
            i = end
        i += 1
    return violations


def check_forbidden_phrases(path: Path, content: str, cfg: dict) -> list[dict]:
    """No weasel words or vague language."""
    if not cfg.get("enabled", True):
        return []
    violations = []
    patterns = cfg.get("patterns", [])

    for entry in patterns:
        pattern = entry.get("pattern", "")
        message = entry.get("message", "remove vague language")
        try:
            re_obj = re.compile(pattern, re.IGNORECASE)
        except re.error:
            continue
        for m in re_obj.finditer(content):
            line_num = content[:m.start()].count("\n") + 1
            violations.append({
                "file": str(path),
                "line": line_num,
                "message": f"forbidden phrase `{m.group()}` — {message}",
                "guard": "forbidden_phrases",
            })
    return violations


def check_credentials(path: Path, content: str, cfg: dict) -> list[dict]:
    """No API keys, tokens, or secrets in source."""
    if not cfg.get("enabled", True):
        return []
    violations = []
    patterns = cfg.get("patterns", [])

    for entry in patterns:
        pattern = entry.get("pattern", "")
        message = entry.get("message", "credential detected")
        try:
            re_obj = re.compile(pattern)
        except re.error:
            continue
        for m in re_obj.finditer(content):
            line_num = content[:m.start()].count("\n") + 1
            violations.append({
                "file": str(path),
                "line": line_num,
                "message": message,
                "guard": "credentials",
                "severity": "error",
            })
    return violations


def check_action_items(path: Path, content: str, cfg: dict) -> list[dict]:
    """ACTION/TODO/FIXME/HACK comments must link to an issue."""
    if not cfg.get("enabled", True):
        return []
    if not cfg.get("require_issue", True):
        return []
    violations = []

    allowed_pattern = cfg.get("allowed_pattern", r"//\s*(ACTION|TODO|FIXME|HACK)\(#\d+\):")
    scan_pattern = cfg.get("scan_pattern", r"//\s*(ACTION|TODO|FIXME|HACK)\b")

    try:
        allowed_re = re.compile(allowed_pattern)
        scan_re = re.compile(scan_pattern)
    except re.error:
        return violations

    for m in scan_re.finditer(content):
        # Check if this specific match has an issue link
        matched = m.group()
        if allowed_re.search(matched):
            continue
        line_num = content[:m.start()].count("\n") + 1
        violations.append({
            "file": str(path),
            "line": line_num,
            "message": f"Action item without issue link — use {allowed_pattern.replace('(','').replace(')','')}#123): description",
            "guard": "action_items",
        })
    return violations


def check_glob_imports(path: Path, content: str, cfg: dict) -> list[dict]:
    """No glob imports like `use foo::*`, `from bar import *`."""
    if not cfg.get("enabled", True):
        return []
    violations = []

    patterns = [
        r"^\s*(use\s+[a-zA-Z0-9_:]+\s*::\s*\*)",       # Rust: use foo::*;
        r"^\s*(from\s+[a-zA-Z0-9_.]+\s+import\s+\*)",   # Python: from foo import *
        r"^\s*(import\s+[a-zA-Z0-9_.]+\s*\.\s*\*)",     # TypeScript: import * from
    ]

    for pat in patterns:
        try:
            re_obj = re.compile(pat, re.MULTILINE)
        except re.error:
            continue
        for m in re_obj.finditer(content):
            line_num = content[:m.start()].count("\n") + 1
            violations.append({
                "file": str(path),
                "line": line_num,
                "message": f"Glob import on line {line_num} — import specific names instead",
                "guard": "glob_imports",
            })
    return violations
