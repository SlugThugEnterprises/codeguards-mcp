"""Project language detectors — sniffs a codebase to decide what guards to run."""

import os
from pathlib import Path

_LANGUAGE_MARKERS: dict[str, list[str]] = {
    "rust": ["Cargo.toml"],
    "python": ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile"],
    "node": ["package.json", "yarn.lock", "pnpm-lock.yaml"],
    "go": ["go.mod", "go.sum"],
    "ruby": ["Gemfile", "Gemfile.lock"],
    "java": ["pom.xml", "build.gradle", "build.gradle.kts"],
    "csharp": ["*.csproj", "*.sln"],
    "cpp": ["CMakeLists.txt", "meson.build"],
    "typescript": ["tsconfig.json"],
    "elixir": ["mix.exs"],
    "php": ["composer.json"],
}

_FILE_TYPE_MAP: dict[str, str] = {
    ".rs": "rust",
    ".py": "python",
    ".js": "node",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "node",
    ".go": "go",
    ".rb": "ruby",
    ".java": "java",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "cpp",
    ".h": "cpp",
    ".ex": "elixir",
    ".exs": "elixir",
    ".php": "php",
    ".vue": "node",
    ".svelte": "node",
}


def detect_languages(project_root: str) -> list[str]:
    """Sniff what languages a project uses by checking for marker files and source."""
    root = Path(project_root)
    if not root.is_dir():
        return []

    found: set[str] = set()

    # Check marker files
    for lang, markers in _LANGUAGE_MARKERS.items():
        for marker in markers:
            if "*" in marker:
                # Glob pattern
                if list(root.glob(marker)):
                    found.add(lang)
                    break
            else:
                if (root / marker).exists():
                    found.add(lang)
                    break

    # Fallback: scan source files (limit to first 2000 entries for speed)
    if not found:
        ext_counts: dict[str, int] = {}
        for i, f in enumerate(root.rglob("*")):
            if i > 2000:
                break
            if f.is_file() and f.suffix in _FILE_TYPE_MAP:
                lang = _FILE_TYPE_MAP[f.suffix]
                ext_counts[lang] = ext_counts.get(lang, 0) + 1

        if ext_counts:
            primary = max(ext_counts, key=ext_counts.get)
            found.add(primary)

    return sorted(found)


def relevant_file_globs(languages: list[str]) -> list[str]:
    """Get file glob patterns for source files in detected languages."""
    EXTENSIONS: dict[str, list[str]] = {
        "rust": ["**/*.rs"],
        "python": ["**/*.py"],
        "node": ["**/*.js", "**/*.jsx", "**/*.mjs"],
        "typescript": ["**/*.ts", "**/*.tsx"],
        "go": ["**/*.go"],
        "ruby": ["**/*.rb"],
        "java": ["**/*.java"],
        "csharp": ["**/*.cs"],
        "cpp": ["**/*.cpp", "**/*.c", "**/*.h", "**/*.hpp"],
        "elixir": ["**/*.ex", "**/*.exs"],
        "php": ["**/*.php"],
    }

    globs = []
    for lang in languages:
        globs.extend(EXTENSIONS.get(lang, []))
    return globs


IGNORED_DIRS: frozenset[str] = frozenset({
    "node_modules", ".git", "target", "build", "dist", ".next",
    "__pycache__", ".venv", "venv", ".env", ".tox", ".eggs",
    ".cargo", "coverage", ".nyc_output", ".pytest_cache",
    "plugins", "sample_code",
})

THIRD_PARTY_DIRS: frozenset[str] = frozenset({
    "third_party", "thirdparty", "3rdparty", "3rd_party", "external",
    "extern", "vendor",
})


_THIRD_PARTY_CACHE: dict[Path, bool] = {}


def is_third_party(path: Path, project_root: str, config: dict) -> bool:
    """Check if a file path belongs to third-party/vendor code."""
    root = Path(project_root)
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    parts = rel.parts

    # Check default third-party folder names
    if any(p in THIRD_PARTY_DIRS for p in parts):
        return True

    # Check custom ignored_dirs from config
    custom_ignored = config.get("ignored_dirs", [])
    if any(p in custom_ignored for p in parts):
        return True

    # Check custom ignored_patterns from config
    ignored_patterns = config.get("ignored_patterns", [])
    if ignored_patterns:
        for pat in ignored_patterns:
            if rel.match(pat) or (pat.startswith("**/") and rel.match(pat[3:])):
                return True

    # Traverse parent folders to root to detect LICENSE/package manager markers
    parent = path.parent
    while parent != root and parent != parent.parent:
        if parent in _THIRD_PARTY_CACHE:
            if _THIRD_PARTY_CACHE[parent]:
                return True
            parent = parent.parent
            continue

        is_tp = False
        markers = [
            ".git", "LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING",
            "Cargo.toml", "package.json", "go.mod", "Gemfile", "pyproject.toml",
            "setup.py", "build.gradle", "pom.xml"
        ]
        for marker in markers:
            if (parent / marker).exists():
                is_tp = True
                break

        _THIRD_PARTY_CACHE[parent] = is_tp
        if is_tp:
            return True
        parent = parent.parent

    return False


def walk_source_files(
    project_root: str,
    extensions: set[str] | None = None,
    custom_ignored_dirs: set[str] | None = None,
    ignored_patterns: list[str] | None = None,
) -> list[Path]:
    """Walk source files in a project, skipping ignored dirs and non-code files."""
    if extensions is None:
        # Only process common source code extensions
        extensions = {".py", ".rs", ".js", ".ts", ".jsx", ".tsx", ".go", ".rb",
                       ".java", ".cs", ".cpp", ".c", ".h", ".hpp", ".ex", ".exs",
                       ".php", ".vue", ".svelte", ".swift", ".kt", ".scala", ".elm",
                       ".hs", ".ml", ".mli", ".r", ".lua", ".sh", ".bash", ".zsh",
                       ".sql"}
    root = Path(project_root)
    files = []
    for f in root.rglob("*"):
        # Skip system/build/cache ignored dirs
        rel = f.relative_to(root)
        parts = rel.parts
        if any(p in IGNORED_DIRS for p in parts):
            continue
        if not f.is_file():
            continue
        if extensions and f.suffix not in extensions:
            continue
        files.append(f)
    return files
