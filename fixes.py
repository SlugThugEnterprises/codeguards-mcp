"""Fix suggestion generation — turns violations into actionable instructions.

The AI doesn't need to figure out architecture from a violation message.
The guard tells it exactly where to split, what to extract, and how to fix.
"""

import re
from pathlib import Path


def fix_file_length(path: Path, content: str, line_count: int, max_lines: int) -> str:
    """Suggest how to split an oversized file by identifying concern boundaries."""
    lines = content.split("\n")

    # Find natural boundaries: blank lines between blocks, major section changes
    boundaries = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "" and i > 5 and i < len(lines) - 5:
            boundaries.append(i)
        elif re.match(r"^(?:pub\s+)?(?:mod\s+|fn\s+|struct\s+|class\s+|\/\/\s*===)", stripped):
            if i > 5:
                boundaries.append(i)

    # Pick 2 best split points (one-third and two-thirds through)
    suggestions = []
    target1 = max_lines
    target2 = max_lines * 2
    for b in boundaries:
        if b > target1 - 10 and b < target1 + 50:
            suggestions.append(b)
        if b > target2 - 10 and b < target2 + 50:
            suggestions.append(b)
        if len(suggestions) >= 2:
            break

    if not suggestions and boundaries:
        suggestions = boundaries[:2]

    if not suggestions:
        return "Split into smaller modules by responsibility. Find natural concern boundaries."

    parts = []
    for i, split in enumerate(suggestions):
        section_lines = lines[max(0, split - 5):split]
        # Try to find a module/function/class name near the split
        context = " ".join(l.strip()[:60] for l in section_lines[-3:])
        parts.append(f"Split at line {split + 1}: context = {context[:80]}...")

    return " | ".join(parts)


def fix_function_length(path: Path, content: str, start_line: int, fn_lines: int, max_fn: int) -> str:
    """Find natural split points in a long function."""
    lines = content.split("\n")
    if start_line < 1 or start_line + fn_lines > len(lines):
        return "Split into smaller functions by extracting logical sub-tasks."

    fn_body = lines[start_line:start_line + fn_lines]

    # Find blank lines that separate logical blocks
    blank_lines = []
    in_block = False
    for i, line in enumerate(fn_body):
        stripped = line.strip()
        if stripped == "" and in_block:
            blank_lines.append(start_line + i + 1)
            in_block = False
        elif stripped != "" and not stripped.startswith("//") and not stripped.startswith("#"):
            in_block = True

    # Also look for scope level changes (end of if/for/while blocks at base indent)
    for i, line in enumerate(fn_body[5:], 5):
        if re.match(r"^\}[;\s]*$", line.strip()):
            blank_lines.append(start_line + i + 1)

    blank_lines = sorted(set(blank_lines))
    target = start_line + fn_lines // 2
    split_at = min(blank_lines, key=lambda x: abs(x - target)) if blank_lines else start_line + fn_lines // 2

    return (
        f"Extract logic after line {split_at} into a separate function. "
        f"Name the new function after what that block computes."
    )


def fix_god_file(path: Path, content: str, pub_count: int, import_count: int) -> str:
    """Suggest module splits for a god file based on public item clustering."""
    # Group public items by name prefix to find concern clusters
    lines = content.split("\n")
    pub_items = []
    for i, line in enumerate(lines):
        m = re.match(r"^\s*pub\s+(?:async\s+)?(?:unsafe\s+)?(?:fn|struct|enum|trait|mod)\s+(\w+)", line)
        if m:
            pub_items.append((i + 1, m.group(1)))

    if not pub_items:
        return "Split by responsibility: identify distinct concerns in this file."

    # Cluster by name prefix
    from collections import defaultdict
    clusters = defaultdict(list)
    for line_num, name in pub_items:
        prefix = name.split("_")[0] if "_" in name else "other"
        clusters[prefix].append(name)

    cluster_lines = []
    for prefix, names in sorted(clusters.items(), key=lambda x: -len(x[1])):
        cluster_lines.append(f"{prefix}: {', '.join(names[:5])}")

    return (
        f"Found {len(clusters)} concern clusters: {'; '.join(cluster_lines[:3])}. "
        f"Extract each cluster into its own module file."
    )


def fix_deep_nesting(path: Path, content: str, line_num: int, depth: int, max_depth: int) -> str:
    """Suggest early-return / guard clause refactor for deep nesting."""
    return (
        f"Refactor with early returns / guard clauses. "
        f"Invert the condition at depth {max_depth + 1}+ and return early. "
        f"This flattens the happy path and reduces nesting."
    )


def fix_parameter_count(function_name: str, param_count: int, max_params: int) -> str:
    """Suggest grouping params into a struct/options pattern."""
    return (
        f"Group these {param_count} parameters into a struct, config object, "
        f"or builder pattern. Example: `{function_name}(opts: {function_name.title()}Options)` "
        f"or a request/context struct."
    )


def fix_swallowed_error(match_text: str) -> str:
    """Suggest proper error handling for swallowed errors."""
    return (
        "Handle the error properly: log it with source context, "
        "wrap it in your project's error type, or propagate it upward. "
        "Never silently discard errors."
    )


def fix_no_stubs(match_text: str) -> str:
    """Generate a concrete suggestion for stubs."""
    if "todo!" in match_text.lower() or "not implemented" in match_text.lower():
        return "Implement this function or mark it clearly as deferred with an issue link."
    return "Replace this stub with a real implementation, or add an issue link."


def fix_hardcoded_value(value_text: str, context: str) -> str:
    """Suggest extracting hardcoded config to config/env."""
    return (
        f"Extract `{value_text[:40]}` to a configuration constant, "
        f"environment variable, or config file. Makes the code testable "
        f"and deployable across environments."
    )


def fix_missing_docs(item_type: str, item_name: str) -> str:
    """Suggest docstring format per language."""
    return (
        f"Add a doc comment for `{item_name}` explaining what it does, "
        f"its parameters, return value, and any important edge cases."
    )


def fix_magic_number(num: int) -> str:
    """Suggest extracting a magic number to a named constant."""
    return f"Extract `{num}` to a named constant that explains what it represents."


def fix_duplicated_code(n_lines: int, repeat_count: int) -> str:
    """Suggest extracting duplicated code to a shared function."""
    return (
        f"Extract these {n_lines * repeat_count} duplicated lines into a shared "
        f"function. Identify what varies between copies and make that the parameter."
    )
