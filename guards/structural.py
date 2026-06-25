"""Structural guards — responsibility detection, fan-out, layer enforcement.

These move CodeGuards from "shape checker" to "structure checker":
  - responsibility_clusters: how many distinct domains does this file touch
  - fan_out: how many unique modules does this file depend on
  - layer_enforcement: does this import go the wrong direction
  - structural_health: composite score from the above
  - growth_drift: is this module accumulating structure (getting worse over time)
  - cosmetic_fix: did the last change actually improve structure or just move code
"""

import json
import os
import re
from pathlib import Path

from import_analyzer import (
    analyze_imports,
    detect_layer_violations,
    structural_health_score,
)

# Persisted structural baselines per project
_BASELINE_FILE = "structural_baseline.json"


def _get_baseline_path(project_root: str) -> Path:
    return Path(project_root) / ".codeguards" / _BASELINE_FILE


def _load_baseline(project_root: str) -> dict:
    path = _get_baseline_path(project_root)
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_baseline(project_root: str, baseline: dict):
    path = _get_baseline_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(baseline, f, indent=2)


def check_responsibility_clusters(
    path: Path, content: str, _cfg: dict
) -> list[dict]:
    """Detect how many distinct concern domains a file imports from.

    A file importing from db::, http::, auth::, and models:: has 4 unrelated
    responsibilities — regardless of line count. This is a structural smell
    that line-count checks miss entirely.
    """
    if _cfg.get("enabled", True) is False:
        return []
    max_domains = _cfg.get("max_domains", 3)
    violations = []

    analysis = analyze_imports(content, path.suffix)
    domains = analysis.get("domain_list", [])
    domain_map = analysis.get("domains", {})

    if len(domains) >= max_domains:
        domain_detail = ", ".join(
            f"{d}({domain_map[d]})" for d in domains
        )
        violations.append({
            "file": str(path),
            "line": 1,
            "message": (
                f"Mixed IO + business logic boundary risk: {len(domains)} responsibility "
                f"domains detected: {', '.join(domains)}. "
                f"Combining {', '.join(domains[:2])} creates coupling "
                f"between unrelated concerns. Extract into separate modules."
            ),
            "guard": "responsibility_clusters",
            "principle": "SRP",
            "severity": "warning",
            "fix": (
                f"Split by domain into: "
                f"{', '.join(f'{d}_module/' for d in domains[:3])}"
            ),
        })
    return violations


def check_fan_out(path: Path, content: str, _cfg: dict) -> list[dict]:
    """Detect structural hubs — files with too many unique dependencies.

    A file importing from 15 different modules is becoming a structural hub
    (god object in terms of dependency graph). This is more meaningful
    than line count for detecting architectural degradation.
    """
    if _cfg.get("enabled", True) is False:
        return []
    max_deps = _cfg.get("max_dependencies", 10)
    violations = []

    analysis = analyze_imports(content, path.suffix)
    fanout = analysis.get("unique_imports", 0)

    if fanout > max_deps:
        internal = analysis.get("internal_imports", 0)
        external = analysis.get("external_imports", 0)
        violations.append({
            "file": str(path),
            "line": 1,
            "message": (
                f"Structural hub: {fanout} unique dependencies "
                f"({internal} internal, {external} external, max {max_deps}). "
                f"High fan-out → coordination point forming/deep coupling."
            ),
            "guard": "fan_out",
            "principle": "SOC",
            "severity": "warning",
            "fix": (
                f"Delegate to focused service modules. Current: {internal} internal "
                f"+ {external} external deps. Target < {max_deps} total."
            ),
        })
    return violations


def check_layer_enforcement(
    path: Path, content: str, cfg: dict
) -> list[dict]:
    """Enforce architectural layer rules on imports.

    Configured via .codeguards.yaml:
        layer_enforcement:
          layers:
            repository: [domain]
            service: [domain, repository]
            api: [domain, repository, service]
    """
    if not cfg.get("enabled", True):
        return []
    layer_rules = cfg.get("layers", {})
    if not layer_rules:
        return []

    violations = detect_layer_violations(str(path), content, path.suffix, layer_rules)
    for v in violations:
        v["file"] = str(path)
        v["line"] = 1
        v["severity"] = "error"
    return violations


def check_structural_health(
    path: Path, content: str, _cfg: dict
) -> list[dict]:
    """Composite structural health score for a file.

    Combines responsibility clusters and fan-out into a single
    score (0-100). Lower → more structural degradation.
    """
    if _cfg.get("enabled", True) is False:
        return []
    min_score = _cfg.get("min_score", 70)
    violations = []

    analysis = analyze_imports(content, path.suffix)
    health = structural_health_score(analysis)
    score = health["score"]

    if score < min_score:
        violations.append({
            "file": str(path),
            "line": 1,
            "message": (
                f"Structural health: {score}/100 ({health['rating']}). "
                f"Domains={health['domains']} Fan-out={health['fanout']}. "
                f"Refactor to reduce responsibility overlap."
            ),
            "guard": "structural_health",
            "principle": "Architecture",
            "severity": "error" if score < 50 else "warning",
            "fix": (
                f"Target score >70. Extract domains into focused modules. "
                f"Current: {health['domains']} domains, {health['fanout']} dependencies."
            ),
        })
    return violations


def check_growth_drift(project_root: str) -> list[dict]:
    """Compare current structural state against previous baseline.

    Detects modules that are accumulating structure (getting worse):
      - Growing import counts
      - Adding new concern domains
      - Increasing fan-out
    """
    violations = []
    prev = _load_baseline(project_root)
    if not prev:
        return violations

    for rel_path, prev_data in prev.items():
        full_path = Path(project_root) / rel_path
        if not full_path.exists():
            continue
        try:
            content = full_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        analysis = analyze_imports(content, full_path.suffix)
        curr = structural_health_score(analysis)

        prev_domains = prev_data.get("domains", 0)
        prev_fanout = prev_data.get("fanout", 0)

        delta_domains = curr["domains"] - prev_domains
        delta_fanout = curr["fanout"] - prev_fanout

        if delta_domains >= 2 or delta_fanout >= 3:
            violations.append({
                "file": str(full_path),
                "line": 1,
                "message": (
                    f"Growth drift: +{delta_domains} domains, +{delta_fanout} deps "
                    f"since baseline. Module is accumulating structure without "
                    f"corresponding architectural refactoring."
                ),
                "guard": "growth_drift",
                "principle": "Architecture",
                "severity": "warning",
                "fix": "Pause feature work. Refactor to split modules before adding more dependencies.",
            })
    return violations


def check_cosmetic_fix(
    project_root: str, violations: list[dict]
) -> list[dict]:
    """Detect cosmetic refactors — shape changed but structure did not.
    
    If the dependency graph / responsibility clusters stayed the same
    but line counts improved, the fix was superficial and should be rejected.
    """
    prev = _load_baseline(project_root)
    if not prev:
        return []

    # Check if the current check had improvements
    # If previous had violations but current shows clean files with same
    # import structure → flag as cosmetic
    # This is a heuristic — we flag when files that WERE violating
    # now pass without actual dependency restructuring.

    return []  # Stub: needs tracking across check cycles to be meaningful


def save_structural_baseline(project_root: str):
    """Snapshot current structural state for future growth_drift comparison."""
    from detectors import walk_source_files

    baseline = {}
    for sf in walk_source_files(project_root):
        try:
            content = sf.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        analysis = analyze_imports(content, sf.suffix)
        health = structural_health_score(analysis)
        rel_path = str(sf.relative_to(project_root))
        baseline[rel_path] = {
            "domains": health["domains"],
            "fanout": health["fanout"],
            "score": health["score"],
        }

    _save_baseline(project_root, baseline)
    return baseline


STRUCTURAL_CHECKS = {
    "responsibility_clusters": check_responsibility_clusters,
    "fan_out": check_fan_out,
    "layer_enforcement": check_layer_enforcement,
    "structural_health": check_structural_health,
}
