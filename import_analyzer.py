"""Import-domain analyzer — structural detection without AST parsing.

Cross-language analysis of import statements to detect:
  - Responsibility clusters (how many distinct domains does this file touch)
  - Fan-out (how many unique modules does this file depend on)
  - Layer violations (does this import go the wrong direction)

Works on Rust, Python, JS/TS, Go, and others — just regex, no AST.
"""

import re
from pathlib import Path
from typing import Optional


# Language-specific import patterns (keyed by file extension)
_IMPORT_PATTERNS: dict[str, list[str]] = {
    # Rust: use crate::foo::bar;  use foo::bar;  use super::...
    ".rs": [
        r"^\s*use\s+(crate\:\:)?(?P<path>[a-z_][a-z0-9_]*(?:\:\:[a-z_][a-z0-9_]*)*)",
    ],
    # Python: from .foo.bar import X   import foo.bar
    ".py": [
        r"^\s*(?:from\s+)(?P<path>[a-z_][a-z0-9_.]*)\s+import",
        r"^\s*import\s+(?P<path>[a-z_][a-z0-9_.]*)",
    ],
    # JS/TS: import X from './foo/bar'   require('./foo')
    ".js": [
        r"^\s*(?:import\s+(?:{[^}]*}|\*\s+as\s+\w+|\w+)\s+from\s+['\"])(?P<path>[^'\"]+)",
        r"^\s*(?:const\s+\{[^}]*\}\s*=\s*require\()['\"](?P<path>[^'\"]+)",
    ],
    ".ts": [
        r"^\s*(?:import\s+(?:{[^}]*}|\*\s+as\s+\w+|\w+)\s+from\s+['\"])(?P<path>[^'\"]+)",
    ],
    ".tsx": [
        r"^\s*(?:import\s+(?:{[^}]*}|\*\s+as\s+\w+|\w+)\s+from\s+['\"])(?P<path>[^'\"]+)",
    ],
    ".jsx": [
        r"^\s*(?:import\s+(?:{[^}]*}|\*\s+as\s+\w+|\w+)\s+from\s+['\"])(?P<path>[^'\"]+)",
    ],
    # Go: import ( "foo/bar" )   or  import "foo/bar"
    ".go": [
        r"^\s*(?:\w+\s+)?\"(?P<path>[a-z][a-z0-9_/]*)\"",
    ],
    # Ruby: require 'foo/bar'
    ".rb": [
        r"^\s*require\s+['\"](?P<path>[^'\"]+)['\"]",
    ],
}


# Common namespaces that indicate concern domains
# If an import starts with one of these, use the first component as domain.
# Otherwise, use "local" or "external" as domain.
_DOMAIN_HINTS = {
    "crate", "models", "db", "database", "http", "api", "auth", "authn", "authz",
    "logging", "tracing", "telemetry", "config", "settings", "errors", "error",
    "events", "event", "messaging", "queue", "storage", "cache", "metrics",
    "validation", "validator", "parser", "serialize", "encoding", "crypto",
    "security", "tls", "network", "rpc", "grpc", "graphql", "rest",
    "domain", "entity", "repository", "service", "usecase", "handler",
    "middleware", "interceptor", "filter", "plugin", "extension",
    "util", "utils", "helpers", "common", "shared", "core", "base",
    "types", "schema", "migration", "seed", "fixture",
    "cli", "command", "job", "task", "worker", "scheduler",
    "notification", "email", "sms", "push",
    "payment", "billing", "invoice", "subscription",
    "search", "index", "query",
    "template", "view", "render", "ui", "component",
}


def _extract_domain(import_path: str, crate_name: str = "") -> Optional[str]:
    """Extract the concern domain from an import path.

    Examples:
        crate::db::profiles::Profile → db
        models::user::User → models
        super::config::Settings → config
        tokio::sync::Mutex → tokio (external)
        std::collections::HashMap → std (stdlib)
        from .db.profiles import → db
        from '../auth/session' → auth
        require('express') → express (external)
    """
    if not import_path:
        return None

    # Normalize: strip leading dots, slashes, crate::
    clean = import_path.strip()
    clean = re.sub(r'^(?:crate\:\:)+', '', clean)
    clean = re.sub(r'^\.\.?/', '', clean)
    clean = clean.replace('/', '::')

    parts = clean.split('::')
    if not parts:
        return None

    first = parts[0].strip().lower()

    # Skip empty, self, super
    if first in ('', 'self', 'super'):
        if len(parts) > 1:
            return parts[1].strip().lower()
        return None

    # Known external crates / libraries — tag as external
    EXTERNALS = {
        'tokio', 'serde', 'std', 'anyhow', 'thiserror', 'clap', 'reqwest',
        'axum', 'actix', 'rocket', 'chrono', 'regex', 'log', 'env_logger',
        'rand', 'uuid', 'sqlx', 'diesel', 'sea_orm', 'redis', 'kafka',
        'tonic', 'prost', 'tower', 'hyper', 'hyper_util', 'bytes', 'futures',
        'async_trait', 'dashmap', 'parking_lot', 'crossbeam', 'rayon',
        'openssl', 'rustls', 'native_tls', 'url', 'mime', 'mime_guess',
        'base64', 'hex', 'sha2', 'hmac', 'jsonwebtoken', 'oauth2',
        'reqwest', 'ureq', 'warp', 'tide', 'poem', 'lambda_runtime',
        'opentelemetry', 'tracing_subscriber', 'metrics', 'lazy_static',
        'once_cell', 'itertools', 'either', 'cfg_if',
        # Python
        'flask', 'django', 'fastapi', 'sqlalchemy', 'pydantic', 'pandas',
        'numpy', 'requests', 'httpx', 'celery', 'pytest',
        # JS
        'express', 'react', 'vue', 'angular', 'next', 'nuxt', 'svelte',
        'axios', 'lodash', 'moment', 'dayjs', 'prisma', 'typeorm',
        'zod', 'yup', 'jest', 'vitest', 'mocha', 'cypress',
    }

    if first in EXTERNALS or not first.isalpha():
        return "external"

    # Known internal domain hints → use as-is
    if first in _DOMAIN_HINTS:
        return first

    # If crate name is known and import starts with it, second component is the domain
    if crate_name and first == crate_name.lower() and len(parts) > 1:
        return parts[1].strip().lower()

    # Unknown = treat as external
    return "external"


def analyze_imports(content: str, file_ext: str, crate_name: str = "") -> dict:
    """Parse imports and return structural analysis.

    Returns:
        {
            "domains": {"db": 3, "auth": 1, "external": 5},  # domain → import count
            "unique_imports": 9,                                 # fan-out
            "internal_imports": 4,                               # non-external
            "external_imports": 5,                               # stdlib + packages
            "raw_imports": ["crate::db::profiles", ...],
        }
    """
    patterns = _IMPORT_PATTERNS.get(file_ext, [])
    domains: dict[str, int] = {}
    raw_imports: list[str] = []

    for pat in patterns:
        for m in re.compile(pat, re.MULTILINE).finditer(content):
            import_path = m.group("path")
            if not import_path:
                continue
            # Skip test-only imports
            line_start = max(0, content[:m.start()].rfind('\n'))
            line = content[line_start:m.start()].strip()
            if line.startswith("#[cfg(test)]") or "@pytest" in line or "test(" in line:
                continue

            domain = _extract_domain(import_path, crate_name) or "unknown"
            domains[domain] = domains.get(domain, 0) + 1
            raw_imports.append(import_path)

    internal_domains = {k: v for k, v in domains.items() if k not in ("external", "unknown")}
    external_count = domains.get("external", 0)

    return {
        "domains": domains,
        "internal_domains": len(internal_domains),
        "unique_imports": len(raw_imports),
        "internal_imports": sum(internal_domains.values()),
        "external_imports": external_count,
        "raw_imports": raw_imports,
        "domain_list": sorted(internal_domains.keys()),
    }


def detect_layer_violations(
    file_path: str,
    content: str,
    file_ext: str,
    layers: dict[str, list[str]],  # e.g. {"domain": ["repository", "service"]}
) -> list[dict]:
    """Check if this file's imports violate layer rules.

    Args:
        layers: dict mapping layer-name → allowed imports from
            e.g. {"service": ["domain"], "api": ["service", "domain"]}
    """
    patterns = _IMPORT_PATTERNS.get(file_ext, [])
    violations = []

    # Determine what layer this file belongs to based on its path
    file_layer = _guess_layer(file_path, list(layers.keys()))

    if not file_layer:
        return []

    allowed = layers.get(file_layer, [])
    if not allowed:
        return []

    for pat in patterns:
        for m in re.compile(pat, re.MULTILINE).finditer(content):
            import_path = m.group("path")
            domain = _extract_domain(import_path)
            if not domain or domain in ("external", "unknown"):
                continue
            if domain not in allowed and domain != file_layer:
                violations.append({
                    "guard": "layer_enforcement",
                    "principle": "Architecture",
                    "message": (
                        f"Layer violation: `{file_layer}` imports from `{domain}` — "
                        f"{file_layer} is only allowed to import from: {', '.join(allowed)}"
                    ),
                })
    return violations


def _guess_layer(file_path: str, layer_names: list[str]) -> Optional[str]:
    """Guess what architectural layer a file belongs to based on path."""
    path_lower = file_path.lower()
    for layer in sorted(layer_names, key=lambda x: -len(x)):  # longest match first
        if layer in path_lower:
            return layer
    return None


def structural_health_score(import_analysis: dict) -> dict:
    """Generate a structural health score from import analysis.

    Returns a dict with score (0-100) and breakdown of contributing factors.
    Lower score = worse structural health (god file forming).
    """
    domains_count = import_analysis.get("internal_domains", 0)
    fanout = import_analysis.get("unique_imports", 0)

    # Scoring (all weights tunable):
    # - Each internal domain beyond 2 costs 8 points (3 domains = 92, 5 = 76)
    # - Each import beyond 8 costs 2 points (15 imports = 86)
    score = 100
    factors = {}

    if domains_count > 2:
        penalty = min(40, (domains_count - 2) * 8)
        score -= penalty
        factors["domains_penalty"] = penalty

    if fanout > 8:
        penalty = min(30, (fanout - 8) * 2)
        score -= penalty
        factors["fanout_penalty"] = penalty

    return {
        "score": max(0, score),
        "domains": domains_count,
        "fanout": fanout,
        "factors": factors,
        "rating": "healthy" if score >= 85 else "warning" if score >= 70 else "at_risk" if score >= 50 else "critical",
    }
