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


# Source regex strings — kept as documentable form, but never iterated
# directly. ``_COMPILED_IMPORT_PATTERNS`` below is the hot path: every
# regex is compiled exactly once at module load.
_IMPORT_PATTERNS: dict[str, list[str]] = {
    # Rust: use crate::foo::bar;  use foo::bar;  use super::...
    # is_internal captures crate:: or super:: prefix — when present,
    # _extract_domain treats unknown names as internal; absent → external.
    ".rs": [
        r"^\s*use\s+(?:(?P<is_internal>crate\:\:|super\:\:))?(?P<path>[a-z_][a-z0-9_]*(?:\:\:[a-z_][a-z0-9_]*)*)",
    ],
    # Python: from .foo.bar import X   import foo.bar
    # is_internal captures leading dot(s) — relative imports are internal.
    ".py": [
        r"^\s*(?:from\s+)(?:(?P<is_internal>\.+))?(?P<path>[a-z_][a-z0-9_.]*)\s+import",
        r"^\s*import\s+(?:(?P<is_internal>\.+))?(?P<path>[a-z_][a-z0-9_.]*)",
    ],
    # JS/TS: import X from './foo/bar'   require('./foo')
    # is_internal captures ./ or ../ prefix — relative imports are internal.
    ".js": [
        r"^\s*(?:import\s+(?:{[^}]*}|\*\s+as\s+\w+|\w+)\s+from\s+['\"])(?:(?P<is_internal>\.\.?\/))?(?P<path>[^'\"]+)",
        r"^\s*(?:const\s+\{[^}]*\}\s*=\s*require\()['\"](?:(?P<is_internal>\.\.?\/))?(?P<path>[^'\"]+)",
    ],
    ".ts": [
        r"^\s*(?:import\s+(?:{[^}]*}|\*\s+as\s+\w+|\w+)\s+from\s+['\"])(?:(?P<is_internal>\.\.?\/))?(?P<path>[^'\"]+)",
    ],
    ".tsx": [
        r"^\s*(?:import\s+(?:{[^}]*}|\*\s+as\s+\w+|\w+)\s+from\s+['\"])(?:(?P<is_internal>\.\.?\/))?(?P<path>[^'\"]+)",
    ],
    ".jsx": [
        r"^\s*(?:import\s+(?:{[^}]*}|\*\s+as\s+\w+|\w+)\s+from\s+['\"])(?:(?P<is_internal>\.\.?\/))?(?P<path>[^'\"]+)",
    ],
    # Go / Ruby — no is_internal capture; these languages don't distinguish
    # project-internal vs external at the syntax level.
    # Go: import ( "foo/bar" )   or  import "foo/bar"
    ".go": [
        r"^\s*(?:\w+\s+)?\"(?P<path>[a-z][a-z0-9_/]*)\"",
    ],
    # Ruby: require 'foo/bar'
    ".rb": [
        r"^\s*require\s+['\"](?P<path>[^'\"]+)['\"]",
    ],
}


# Pre-compiled once at import time. ``analyze_imports`` and
# ``detect_layer_violations`` both call ``finditer`` on every source file,
# so the difference between compile-per-call (~1ms each) and reuse is
# significant on a repo with thousands of files.
_COMPILED_IMPORT_PATTERNS: dict[str, list[re.Pattern]] = {
    ext: [re.compile(pat, re.MULTILINE) for pat in patterns]
    for ext, patterns in _IMPORT_PATTERNS.items()
}


# Project prefix aliases — match "app.db" → "db", "myproject.models" → "models".
_PROJECT_PREFIXES: frozenset[str] = frozenset({
    'app', 'src', 'lib', 'project', 'myapp', 'myproject', 'backend',
})


# Common namespaces that indicate concern domains.
# If an import starts with one of these, use the first component as domain.
_DOMAIN_HINTS: frozenset[str] = frozenset({
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
})


# Match valid identifier-like names: alpha start, then alphanumeric/underscore.
# Replaces isalpha() which rejected domain_0, config_v2, api_v3, etc.
_IDENT_LIKE_RE = re.compile(r'^[a-z][a-z0-9_]*$')


def _extract_domain(import_path: str, crate_name: str = "",
                    is_internal: bool = False) -> Optional[str]:
    """Extract the concern domain from an import path.

    ``is_internal`` should be True when the import syntax indicates a
    project-internal reference (e.g., ``crate::`` or ``super::`` in Rust,
    a leading ``.`` in Python, ``./`` or ``../`` in JS).  When True,
    unknown identifier-like names are treated as internal domains rather
    than being collapsed into ``"external"``.

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
    normalized = import_path.strip()
    normalized = re.sub(r'^(?:crate\:\:)+', '', normalized)
    normalized = re.sub(r'^\.\.?/', '', normalized)
    normalized = normalized.replace('/', '::')
    # Python uses dot separators — normalize to ::
    normalized = normalized.replace('.', '::')

    parts = normalized.split('::')
    if not parts:
        return None

    first = parts[0].strip().lower()

    # Skip empty, self, super
    if first in ('', 'self', 'super'):
        if len(parts) > 1:
            return parts[1].strip().lower()
        return None

    if first in _EXTERNAL_LIBS or not _IDENT_LIKE_RE.match(first):
        return "external"

    # If first is a generic project prefix, use second component as domain
    # ("app.db" → "db", "myproject.models" → "models").
    if first in _PROJECT_PREFIXES and len(parts) > 1:
        domain = parts[1].strip().lower()
        return domain if domain in _DOMAIN_HINTS else domain  # still return it

    # Known internal domain hints → use as-is
    if first in _DOMAIN_HINTS:
        return first

    # If crate name is known and import starts with it, second component is the domain
    if crate_name and first == crate_name.lower() and len(parts) > 1:
        return parts[1].strip().lower()

    # When the import syntax says "this is internal" (crate::, super::,
    # .module, ./path, ../path), treat unknown names as project domains.
    # Otherwise, unknown names are assumed external — avoids classifying
    # bare ``use some_crate::Thing;`` as an internal domain.
    if _IDENT_LIKE_RE.match(first):
        return first if is_internal else "external"

    # Genuinely unknown — treat as external
    return "external"


# Module-level frozenset — allocated once, immutable, safe to share.
_EXTERNAL_LIBS: frozenset[str] = frozenset({
    # Rust / cross-language crates
    'tokio', 'serde', 'std', 'anyhow', 'thiserror', 'clap', 'reqwest',
    'axum', 'actix', 'rocket', 'chrono', 'regex', 'log', 'env_logger',
    'rand', 'uuid', 'sqlx', 'diesel', 'sea_orm', 'redis', 'kafka',
    'tonic', 'prost', 'tower', 'hyper', 'hyper_util', 'bytes', 'futures',
    'async_trait', 'dashmap', 'parking_lot', 'crossbeam', 'rayon',
    'openssl', 'rustls', 'native_tls', 'url', 'mime', 'mime_guess',
    'base64', 'hex', 'sha2', 'hmac', 'config', 'jsonwebtoken', 'oauth2',
    'reqwest', 'ureq', 'warp', 'tide', 'poem', 'lambda_runtime',
    'opentelemetry', 'tracing_subscriber', 'metrics', 'lazy_static',
    'once_cell', 'itertools', 'either', 'cfg_if',

    # Python 3rd-party
    'flask', 'django', 'fastapi', 'sqlalchemy', 'pydantic', 'pandas',
    'numpy', 'requests', 'httpx', 'celery', 'pytest',
    # JS/TS
    'express', 'react', 'vue', 'angular', 'next', 'nuxt', 'svelte',
    'axios', 'lodash', 'moment', 'dayjs', 'prisma', 'typeorm',
    'zod', 'yup', 'jest', 'vitest', 'mocha', 'cypress',
    # YAML (Python)
    'yaml',
})


def analyze_imports(content: str, file_ext: str, crate_name: str = "") -> dict:
    """Parse imports and return structural analysis.

    Returns:
        {
            "domains": {"db": 3, "auth": 1, "external": 5},
            "unique_imports": 9,
            "internal_imports": 4,
            "external_imports": 5,
            "raw_imports": ["crate::db::profiles", ...],
        }
    """
    patterns = _COMPILED_IMPORT_PATTERNS.get(file_ext, [])
    domains: dict[str, int] = {}
    raw_imports: list[str] = []

    for pat in patterns:
        for m in pat.finditer(content):
            import_path = m.group("path")
            if not import_path:
                continue
            # Skip test-only imports
            line_start = max(0, content[:m.start()].rfind('\n'))
            line = content[line_start:m.start()].strip()
            if line.startswith("#[cfg(test)]") or "@pytest" in line or "test(" in line:
                continue

            is_internal = bool(m.groupdict().get("is_internal"))
            domain = _extract_domain(import_path, crate_name,
                                     is_internal=is_internal) or "unknown"
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
    patterns = _COMPILED_IMPORT_PATTERNS.get(file_ext, [])
    violations = []

    # Determine what layer this file belongs to based on its path
    file_layer = _guess_layer(file_path, list(layers.keys()))

    if not file_layer:
        return []

    allowed = layers.get(file_layer, [])
    if not allowed:
        return []

    for pat in patterns:
        for m in pat.finditer(content):
            import_path = m.group("path")
            is_internal = bool(m.groupdict().get("is_internal"))
            domain = _extract_domain(import_path,
                                     is_internal=is_internal)
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
