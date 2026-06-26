"""Tests for guards/structural.py — responsibility clusters, fan-out, layer
enforcement, structural health, growth drift, baseline persistence."""

import json
import sys
sys.path.insert(0, ".")

from pathlib import Path
from guards.structural import (
    _get_baseline_path,
    _load_baseline,
    _save_baseline,
    check_responsibility_clusters,
    check_fan_out,
    check_structural_health,
    _check_cosmetic_fix,
    save_structural_baseline,
)


# ── baseline path helpers ──

def test_get_baseline_path():
    p = _get_baseline_path("/my/project")
    assert p == Path("/my/project/.codeguards/structural_baseline.json")


# ── baseline load/save ──

def test_load_baseline_missing(tmp_path):
    assert _load_baseline(str(tmp_path)) == {}


def test_load_baseline_valid(tmp_path):
    codeguards = tmp_path / ".codeguards"
    codeguards.mkdir()
    baseline = {"src/lib.rs": {"domains": 3, "fanout": 12, "score": 75}}
    (codeguards / "structural_baseline.json").write_text(json.dumps(baseline))
    loaded = _load_baseline(str(tmp_path))
    assert loaded == baseline


def test_load_baseline_invalid_json(tmp_path):
    codeguards = tmp_path / ".codeguards"
    codeguards.mkdir()
    (codeguards / "structural_baseline.json").write_text("{bad json")
    assert _load_baseline(str(tmp_path)) == {}


def test_save_and_load_baseline_roundtrip(tmp_path):
    baseline = {"src/lib.rs": {"domains": 2, "fanout": 8, "score": 82}}
    _save_baseline(str(tmp_path), baseline)
    loaded = _load_baseline(str(tmp_path))
    assert loaded == baseline


# ── check_responsibility_clusters ──

def test_responsibility_clusters_clean():
    """A file importing from one domain should not trigger."""
    code = (
        "use crate::db::profiles::Profile;\n"
        "use crate::db::settings::AppSettings;\n"
        "use serde::Deserialize;\n"
    )
    violations = check_responsibility_clusters(
        Path("src/db/lib.rs"), code,
        {"enabled": True, "max_domains": 3},
    )
    assert violations == []


def test_responsibility_clusters_violation():
    """A file importing from 4+ internal domains triggers the guard."""
    code = (
        "use crate::db::profiles::Profile;\n"
        "use crate::http::routes::Router;\n"
        "use crate::auth::session::Session;\n"
        "use crate::models::user::User;\n"
        "use serde::Deserialize;\n"
    )
    violations = check_responsibility_clusters(
        Path("src/lib.rs"), code,
        {"enabled": True, "max_domains": 3},
    )
    assert len(violations) >= 1
    assert "responsibility" in violations[0]["message"].lower()


def test_responsibility_clusters_disabled():
    violations = check_responsibility_clusters(
        Path("src/lib.rs"), "use crate::db::Item;",
        {"enabled": False},
    )
    assert violations == []


# ── check_fan_out ──

def test_fan_out_clean():
    code = "\n".join(f"use crate::db::Item{i};" for i in range(5))
    violations = check_fan_out(
        Path("src/lib.rs"), code,
        {"enabled": True, "max_dependencies": 10},
    )
    assert violations == []


def test_fan_out_violation():
    code = "\n".join(f"use crate::mod_{i}::Item;" for i in range(15))
    violations = check_fan_out(
        Path("src/lib.rs"), code,
        {"enabled": True, "max_dependencies": 10},
    )
    assert len(violations) >= 1
    assert "fan-out" in violations[0]["message"].lower() or "fan_out" in violations[0]["guard"]


def test_fan_out_disabled():
    violations = check_fan_out(
        Path("src/lib.rs"), "use crate::many::*;",
        {"enabled": False},
    )
    assert violations == []


# ── check_structural_health ──

def test_structural_health_good():
    """A file with few domains and imports should have a good score."""
    code = (
        "use crate::models::user::User;\n"
        "use crate::models::profile::Profile;\n"
        "use serde::Deserialize;\n"
    )
    violations = check_structural_health(
        Path("src/models/lib.rs"), code,
        {"enabled": True, "min_score": 70},
    )
    assert violations == []


def test_structural_health_bad():
    """A god file should score low and trigger the guard. Use all-alpha
    domain names — _extract_domain() returns 'external' for names with
    underscores/digits because of an isalpha() gate."""
    code = "\n".join(
        f"use crate::{domain}::Item;" for domain in [
            "db", "http", "auth", "models", "cache", "email",
            "payment", "search", "queue", "storage", "analytics", "notify",
        ]
    )
    violations = check_structural_health(
        Path("src/god.rs"), code,
        {"enabled": True, "min_score": 70},
    )
    assert len(violations) >= 1
    assert "Structural health" in violations[0]["message"]


def test_structural_health_disabled():
    violations = check_structural_health(
        Path("src/lib.rs"), "use crate::db::Item;",
        {"enabled": False},
    )
    assert violations == []


# ── _check_cosmetic_fix ──

def test_cosmetic_fix_returns_empty():
    """Stub always returns empty."""
    violations = _check_cosmetic_fix("/nonexistent", [])
    assert violations == []


# ── save_structural_baseline ──

def test_save_structural_baseline_no_files(tmp_path):
    """When there are no source files, baseline should be empty."""
    baseline = save_structural_baseline(str(tmp_path))
    assert baseline == {}

    # Should have created .codeguards/ directory
    assert (tmp_path / ".codeguards").is_dir()


def test_save_structural_baseline_with_files(tmp_path):
    """Baseline should capture structural data for source files."""
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "src" / "lib.rs").write_text(
        "use crate::db::User;\n"
        "use serde::Deserialize;\n"
        "pub fn process() {}\n"
    )
    baseline = save_structural_baseline(str(tmp_path))
    assert "src/lib.rs" in baseline
    assert "domains" in baseline["src/lib.rs"]
    assert "fanout" in baseline["src/lib.rs"]
    assert "score" in baseline["src/lib.rs"]
