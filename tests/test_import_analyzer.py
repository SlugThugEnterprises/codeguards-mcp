"""Tests for import_analyzer — domain extraction, fan-out, structural health."""

import sys
sys.path.insert(0, ".")

from import_analyzer import analyze_imports, structural_health_score


def test_rust_domain_extraction():
    """Rust crate imports should produce correct domain clusters."""
    code = """
use crate::db::profiles::Profile;
use crate::http::routes::RouteHandler;
use crate::auth::session::SessionManager;
use crate::models::user::User;
use anyhow::Result;
use tokio::sync::Mutex;
"""
    analysis = analyze_imports(code, ".rs", crate_name="antidetect")
    assert "db" in analysis["domain_list"], f"Expected 'db' in domains, got {analysis['domain_list']}"
    assert "http" in analysis["domain_list"]
    assert "auth" in analysis["domain_list"]
    assert "models" in analysis["domain_list"]
    assert analysis["internal_domains"] == 4, f"Expected 4 internal domains, got {analysis['internal_domains']}"
    assert analysis["unique_imports"] == 6


def test_rust_no_duplicate_domains():
    """Multiple imports from same domain should count as one cluster."""
    code = """
use crate::db::profiles::Profile;
use crate::db::settings::AppSettings;
use crate::db::migrations::Runner;
use anyhow::Result;
"""
    analysis = analyze_imports(code, ".rs")
    assert "db" in analysis["domain_list"]
    assert analysis["internal_domains"] == 1


def test_python_domain_extraction():
    """Python imports should produce correct domain clusters."""
    code = """
from app.db.session import get_db
from app.http.routes import router
from app.auth.login import login_user
from config.settings import Settings
"""
    analysis = analyze_imports(code, ".py")
    assert "db" in analysis["domain_list"], f"Got {analysis['domain_list']}"
    assert "http" in analysis["domain_list"]
    assert "auth" in analysis["domain_list"]
    assert analysis["internal_domains"] >= 3


def test_js_domain_extraction():
    """JS imports should produce correct domain clusters."""
    code = """
import { getDb } from './db/session';
import { router } from '../http/routes';
import { login } from '../auth/login';
"""
    analysis = analyze_imports(code, ".js")
    assert "db" in analysis["domain_list"]
    assert "http" in analysis["domain_list"]
    assert "auth" in analysis["domain_list"]


def test_structural_health_clean():
    """A single-domain file with few imports should score high."""
    code = """
use crate::models::user::User;
use crate::models::profile::Profile;
use serde::Deserialize;
"""
    analysis = analyze_imports(code, ".rs")
    health = structural_health_score(analysis)
    assert health["score"] >= 90, f"Expected score >= 90, got {health['score']}"
    assert health["rating"] in ("healthy", "warning")


def test_structural_health_god_file():
    """A multi-domain file with many imports should score low."""
    code = """
use crate::db::profiles::Profile;
use crate::http::routes::Route;
use crate::auth::session::Session;
use crate::models::user::User;
use crate::cache::redis::Redis;
use crate::email::sender::Mailer;
use crate::payment::stripe::Stripe;
use crate::search::elastic::Index;
use crate::queue::rabbit::MQ;
use crate::storage::s3::Bucket;
use serde::Deserialize;
use tokio::sync::Mutex;
use anyhow::Result;
"""
    analysis = analyze_imports(code, ".rs")
    health = structural_health_score(analysis)
    assert health["score"] < 80, f"Expected score < 80 for god file, got {health['score']}"
    assert health["domains"] >= 8


def test_empty_file():
    """Empty file should produce empty analysis, not crash."""
    analysis = analyze_imports("", ".rs")
    assert analysis["unique_imports"] == 0
    assert analysis["domain_list"] == []


def test_no_imports():
    """File with no imports should produce empty analysis."""
    code = "fn main() { println!(\"hello\"); }"
    analysis = analyze_imports(code, ".rs")
    assert analysis["unique_imports"] == 0


def test_domain_with_underscores_and_digits():
    """Domain names like domain_0, config_v2 should be internal, not external."""
    code = (
        "use crate::domain_0::Foo;\n"
        "use crate::domain_1::Bar;\n"
        "use crate::config_v2::Config;\n"
        "use serde::Deserialize;\n"
    )
    analysis = analyze_imports(code, ".rs")
    assert "domain_0" in analysis["domain_list"], f"Got: {analysis['domain_list']}"
    assert "domain_1" in analysis["domain_list"]
    assert "config_v2" in analysis["domain_list"]
    assert analysis["internal_domains"] == 3
    assert analysis["external_imports"] == 1  # only serde


def test_unknown_external_crate_not_internal():
    """A bare `use some_crate::Thing;` (no crate::/super:: prefix)
    should be classified as external, not internal — even if the name
    looks like a valid identifier."""
    code = (
        "use some_random_crate::Thing;\n"
        "use another_crate::Stuff;\n"
    )
    analysis = analyze_imports(code, ".rs")
    assert analysis["internal_domains"] == 0
    assert analysis["external_imports"] == 2


def test_crate_prefixed_import_is_internal():
    """crate:: and super:: prefixed imports are always internal."""
    code = (
        "use crate::domain_0::Foo;\n"
        "use crate::config_v2::Config;\n"
        "use super::helpers::Helper;\n"
    )
    analysis = analyze_imports(code, ".rs")
    assert analysis["internal_domains"] == 3
    assert "domain_0" in analysis["domain_list"]
    assert "config_v2" in analysis["domain_list"]
    assert "helpers" in analysis["domain_list"]


def test_python_relative_import_is_internal():
    """from .module import X should be internal."""
    code = "from .domain_utils import helper\nfrom ..parent_mod import func\n"
    analysis = analyze_imports(code, ".py")
    assert analysis["internal_domains"] == 2
    assert "domain_utils" in analysis["domain_list"]
    assert "parent_mod" in analysis["domain_list"]


def test_python_absolute_import_is_external():
    """from unknown_lib import X (no leading dot) should be external."""
    code = "from some_unknown_lib import helper\nimport another_lib\n"
    analysis = analyze_imports(code, ".py")
    assert analysis["internal_domains"] == 0
    assert analysis["external_imports"] == 2


def test_js_relative_import_is_internal():
    """./foo/bar and ../foo/bar should be internal."""
    code = (
        "import { util } from './helpers/string';\n"
        "import { api } from '../api/client';\n"
    )
    analysis = analyze_imports(code, ".js")
    assert analysis["internal_domains"] == 2
    assert "helpers" in analysis["domain_list"]
    assert "api" in analysis["domain_list"]


def test_js_bare_import_is_external():
    """import from 'some-package' (no ./ or ../) should be external."""
    code = "import express from 'express';\nimport lodash from 'lodash';\n"
    analysis = analyze_imports(code, ".js")
    assert analysis["internal_domains"] == 0
    assert analysis["external_imports"] == 2


def test_external_separation():
    """External imports should be counted separately from internal."""
    code = """
use crate::db::Db;
use tokio::sync::Mutex;
use serde::Serialize;
use std::collections::HashMap;
"""
    analysis = analyze_imports(code, ".rs")
    assert analysis["internal_imports"] == 1, f"Expected 1 internal, got {analysis['internal_imports']}"
    assert analysis["external_imports"] == 3, f"Expected 3 external, got {analysis['external_imports']}"
