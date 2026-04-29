"""Pure stdlib helpers: topological sort, import analysis, DB, JSON, DAG metrics.

Text- and goal-similarity helpers moved to :mod:`text_similarity`; they are
re-exported below so existing ``from .utils import goal_similarity`` (etc.)
imports continue to work.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import random
import re
import sqlite3
import time
from collections import deque
from collections.abc import Callable, Generator
from typing import Any

# Re-exports for backward compatibility. New code should import directly
# from :mod:`text_similarity` / :mod:`scaffold_validation` when it only
# needs those helpers.
from .text_similarity import (  # noqa: F401
    _cosine,
    _trigram_list,
    expand_goal_terms,
    goal_similarity,
    normalize_goal,
    trigram_bag_cosine,
    trigram_signature,
    unique_trigrams,
    word_jaccard,
    word_substring_score,
)
# NOTE: scaffold_validation imports from this module, so it must be
# imported lazily to avoid a circular import at module load.
from .scaffold_validation import (  # noqa: F401,E402
    compute_scaffold_dag_metrics,
    validate_scaffold,
)

_IGNORED_DIRS = frozenset({
    ".git", "__pycache__", ".pytest_cache", "venv", ".venv", "node_modules",
    ".tox", ".mypy_cache", ".ruff_cache", ".chisel", ".stele-context", "dist", "build",
    ".next", ".nuxt", "coverage", ".turbo", ".parcel-cache", "sample_file_test",
})


def _is_ignored_dir(name: str) -> bool:
    """Check if a directory should be skipped during project traversal."""
    return name in _IGNORED_DIRS or name.endswith(".egg-info")


_C_COMMENT_RE = re.compile(r"//[^\n]*|/\*[\s\S]*?\*/")
_HASH_COMMENT_RE = re.compile(r"#[^\n]*")


def _strip_c_comments(src: str) -> str:
    """Remove C-style line and block comments (Go, Rust, Java, C#, Dart, Zig)."""
    return _C_COMMENT_RE.sub("", src)


def _strip_hash_comments(src: str) -> str:
    """Remove hash-style line comments (Ruby, Python)."""
    return _HASH_COMMENT_RE.sub("", src)


def _strip_php_comments(src: str) -> str:
    """Remove PHP comments: //, /* */, and #."""
    return _HASH_COMMENT_RE.sub("", _C_COMMENT_RE.sub("", src))


def _walk_project_sources(
    project_root: str,
    extensions: tuple[str, ...],
    preprocess: Callable[[str], str] | None = None,
) -> Generator[tuple[str, str], None, None]:
    """Yield (relative_path, source) for matching files, skipping ignored dirs."""
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if not _is_ignored_dir(d)]
        for fname in files:
            if not fname.endswith(extensions):
                continue
            path = os.path.join(root, fname)
            rel = os.path.relpath(path, project_root)
            try:
                with open(path, encoding="utf-8", errors="replace") as fp:
                    src = fp.read()
            except OSError:
                continue
            if preprocess:
                src = preprocess(src)
            yield rel, src


def _collect_symbols_regex(
    project_root: str,
    extensions: tuple[str, ...],
    patterns: list[re.Pattern[str]],
    preprocess: Callable[[str], str] | None = None,
) -> dict[str, list[str]]:
    """Shared symbol collection for regex-based analyzers."""
    symbols: dict[str, list[str]] = {}
    for rel, src in _walk_project_sources(project_root, extensions, preprocess):
        seen: set[str] = set()
        names: list[str] = []
        for pat in patterns:
            for m in pat.finditer(src):
                name = m.group(1)
                if name and name not in seen:
                    seen.add(name)
                    names.append(name)
        if names:
            symbols[rel] = names
    return symbols


def _collect_typed_symbols_regex(
    project_root: str,
    extensions: tuple[str, ...],
    typed_patterns: list[tuple[re.Pattern[str], str]],
    preprocess: Callable[[str], str] | None = None,
) -> dict[str, list[tuple[str, str]]]:
    """Shared typed symbol collection: returns file -> [(name, type_label)]."""
    symbols: dict[str, list[tuple[str, str]]] = {}
    for rel, src in _walk_project_sources(project_root, extensions, preprocess):
        seen: set[str] = set()
        entries: list[tuple[str, str]] = []
        for pat, type_label in typed_patterns:
            for m in pat.finditer(src):
                name = m.group(1)
                if name and name not in seen:
                    seen.add(name)
                    entries.append((name, type_label))
        if entries:
            symbols[rel] = entries
    return symbols


def _collect_project_files(project_root: str, extensions: tuple[str, ...]) -> set[str]:
    """Collect relative paths of files matching extensions, skipping ignored dirs."""
    files: set[str] = set()
    for root, dirs, fnames in os.walk(project_root):
        dirs[:] = [d for d in dirs if not _is_ignored_dir(d)]
        for fname in fnames:
            if fname.endswith(extensions):
                files.add(os.path.relpath(os.path.join(root, fname), project_root))
    return files


def _walk_and_map_namespaces(
    project_root: str,
    extensions: tuple[str, ...],
    namespace_re: re.Pattern[str],
    preprocess: Callable[[str], str],
    source_roots: list[str] | None = None,
) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Walk project files, read sources, extract namespaces/packages.

    Returns (namespace_to_files, file_to_source).
    Used by CSharp, PHP, and Java analyzers to avoid duplicating the walk+map pattern.
    """
    ns_to_files: dict[str, list[str]] = {}
    file_sources: dict[str, str] = {}
    roots = source_roots or [project_root]
    for src_root in roots:
        for root, dirs, files in os.walk(src_root):
            dirs[:] = [d for d in dirs if not _is_ignored_dir(d)]
            for fname in files:
                if not fname.endswith(extensions):
                    continue
                path = os.path.join(root, fname)
                rel = os.path.relpath(path, project_root)
                try:
                    with open(path, encoding="utf-8", errors="replace") as fp:
                        src = fp.read()
                except OSError:
                    continue
                src = preprocess(src)
                file_sources[rel] = src
                m = namespace_re.search(src)
                if m:
                    ns_to_files.setdefault(m.group(1), []).append(rel)
    return ns_to_files, file_sources


def _resolve_namespace_import(
    import_path: str,
    ns_to_files: dict[str, list[str]],
    rel: str,
    deps: set[str],
    sep: str = ".",
) -> None:
    """Resolve a namespace/package import by trying progressively shorter prefixes.

    Used by Java, C#, and PHP analyzers to resolve dotted import paths
    against a namespace-to-files mapping. Adds matching files to deps.
    """
    parts = import_path.split(sep)
    for i in range(len(parts), 0, -1):
        prefix = sep.join(parts[:i])
        if prefix in ns_to_files:
            for dep in ns_to_files[prefix]:
                if dep != rel:
                    deps.add(dep)
            break


def _read_workspace_packages(project_root: str) -> dict[str, str]:
    """Read workspace packages from package.json. Returns {pkg_name: relative_dir}."""
    pkg_json = os.path.join(project_root, "package.json")
    if not os.path.isfile(pkg_json):
        return {}
    try:
        with open(pkg_json, encoding="utf-8") as fp:
            root_pkg = json.load(fp)
    except (OSError, json.JSONDecodeError):
        return {}
    workspace_globs = root_pkg.get("workspaces", [])
    # workspaces can be {"packages": [...]} (yarn) or [...] (npm/pnpm)
    if isinstance(workspace_globs, dict):
        workspace_globs = workspace_globs.get("packages", [])
    if not isinstance(workspace_globs, list):
        return {}
    # Expand simple glob patterns (e.g. "packages/*")
    pkg_dirs: list[str] = []
    for pattern in workspace_globs:
        if pattern.endswith("/*"):
            parent = os.path.join(project_root, pattern[:-2])
            if os.path.isdir(parent):
                try:
                    for entry in sorted(os.listdir(parent)):
                        full = os.path.join(parent, entry)
                        if os.path.isdir(full) and os.path.isfile(os.path.join(full, "package.json")):
                            pkg_dirs.append(os.path.relpath(full, project_root))
                except OSError:
                    pass
        else:
            full = os.path.join(project_root, pattern)
            if os.path.isdir(full) and os.path.isfile(os.path.join(full, "package.json")):
                pkg_dirs.append(pattern)
    # Map package names to their directories
    result: dict[str, str] = {}
    for pkg_dir in pkg_dirs:
        child_pkg = os.path.join(project_root, pkg_dir, "package.json")
        try:
            with open(child_pkg, encoding="utf-8") as fp:
                child = json.load(fp)
            name = child.get("name")
            if name:
                result[name] = pkg_dir
        except (OSError, json.JSONDecodeError):
            continue
    return result


def _resolve_workspace_import(
    import_path: str, file_set: set[str],
    workspace_pkgs: dict[str, str],
    extensions: tuple[str, ...],
) -> str | None:
    """Resolve a bare import to a workspace package entry point."""
    pkg_name = import_path
    sub_path = ""
    if pkg_name not in workspace_pkgs:
        parts = import_path.split("/")
        if parts[0].startswith("@") and len(parts) >= 2:
            pkg_name = parts[0] + "/" + parts[1]
            sub_path = "/".join(parts[2:])
        elif len(parts) >= 2:
            pkg_name = parts[0]
            sub_path = "/".join(parts[1:])
    if pkg_name not in workspace_pkgs:
        return None
    pkg_dir = workspace_pkgs[pkg_name]
    if sub_path:
        resolved_base = os.path.normpath(os.path.join(pkg_dir, sub_path))
    else:
        resolved_base = os.path.join(pkg_dir, "src", "index")
        found = any((resolved_base + ext) in file_set for ext in extensions)
        if not found:
            resolved_base = os.path.join(pkg_dir, "index")
    for ext in extensions:
        candidate = resolved_base + ext
        if candidate in file_set:
            return candidate
    return None


# ── JSON / hashing ──────────────────────────────────────────────────────────

def dumps_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True)


def sha256_json(obj: object) -> str:
    return hashlib.sha256(dumps_json(obj).encode("utf-8")).hexdigest()


# ── Database ─────────────────────────────────────────────────────────────────

DEFAULT_DB_PATH = "trammel.db"

_BUSY_RETRIES = 5
_BUSY_BASE_DELAY = 0.05


def db_connect(path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    # isolation_level=None puts the driver in manual mode: no implicit BEGIN
    # before DML statements.  All writes go through transaction() below, so
    # we own the BEGIN/COMMIT lifecycle and can never get bitten by Python
    # auto-starting a transaction we don't know about (which produced
    # "cannot start a transaction within a transaction" on Python 3.14).
    conn = sqlite3.connect(path, timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextlib.contextmanager
def transaction(
    conn: sqlite3.Connection, immediate: bool = True,
) -> Generator[sqlite3.Connection, None, None]:
    """Execute a block inside an explicit transaction with SQLITE_BUSY retry.

    If the connection already has a transaction open (caller wrapped us, or
    a stray implicit transaction is still active), use a SAVEPOINT so the
    inner block stays atomic without colliding with the outer BEGIN.
    """
    if conn.in_transaction:
        sp = f"trammel_sp_{int(time.time() * 1_000_000)}_{random.randrange(1 << 30)}"
        conn.execute(f"SAVEPOINT {sp}")
        try:
            yield conn
        except Exception:
            try:
                conn.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                conn.execute(f"RELEASE SAVEPOINT {sp}")
            except sqlite3.Error:
                pass
            raise
        else:
            conn.execute(f"RELEASE SAVEPOINT {sp}")
        return

    mode = "BEGIN IMMEDIATE" if immediate else "BEGIN"
    for attempt in range(_BUSY_RETRIES):
        try:
            conn.execute(mode)
            break
        except sqlite3.OperationalError as exc:
            if "database is locked" not in str(exc):
                raise
            if attempt == _BUSY_RETRIES - 1:
                raise
            delay = _BUSY_BASE_DELAY * (2 ** attempt) + random.uniform(0, _BUSY_BASE_DELAY)
            time.sleep(delay)
    try:
        yield conn
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    else:
        conn.execute("COMMIT")


# ── Topological sort ─────────────────────────────────────────────────────────

def topological_sort(deps: dict[str, list[str]]) -> list[str]:
    """Kahn's algorithm: returns nodes with dependencies first. Cycles appended at end."""
    all_nodes: set[str] = set(deps.keys())
    for targets in deps.values():
        all_nodes.update(targets)

    in_count: dict[str, int] = {n: 0 for n in all_nodes}
    rev: dict[str, list[str]] = {n: [] for n in all_nodes}

    for node, targets in deps.items():
        in_count[node] = len(targets)
        for t in targets:
            rev[t].append(node)

    queue = deque(sorted(n for n in all_nodes if in_count[n] == 0))
    result: list[str] = []

    while queue:
        node = queue.popleft()
        result.append(node)
        for dependent in sorted(rev[node]):
            in_count[dependent] -= 1
            if in_count[dependent] == 0:
                queue.append(dependent)

    for n in sorted(all_nodes):
        if n not in result:
            result.append(n)

    return result




# ── Failure analysis ─────────────────────────────────────────────────────────

_TRACEBACK_RE = re.compile(r'File "([^"]+)", line (\d+)')

_ERROR_PATTERNS: list[tuple[str, str, str]] = [
    ("ImportError", "import_error", "Check import paths and module dependencies"),
    ("ModuleNotFoundError", "import_error", "Check import paths and module dependencies"),
    ("AttributeError", "attribute_error", "Verify referenced attributes exist on the object"),
    ("SyntaxError", "syntax_error", "Fix Python syntax in the referenced file"),
    ("TypeError", "type_error", "Check argument types and function signatures"),
    ("NameError", "name_error", "Check that referenced names are defined in scope"),
    ("AssertionError", "assertion_error", "Test assertion failed — check expected vs actual"),
    ("FAIL", "test_failure", "One or more test assertions failed"),
]


def analyze_failure(
    stderr: str,
    stdout: str,
    error_patterns: list[tuple[str, str, str]] | None = None,
) -> dict[str, Any]:
    """Extract structured failure information from test output."""
    combined = stderr + "\n" + stdout
    analysis: dict[str, Any] = {
        "error_type": "unknown",
        "message": "",
        "file": None,
        "line": None,
        "suggestion": "",
    }

    patterns = error_patterns if error_patterns is not None else _ERROR_PATTERNS
    for marker, etype, suggestion in patterns:
        if marker in combined:
            analysis["error_type"] = etype
            analysis["suggestion"] = suggestion
            for line in combined.split("\n"):
                if marker in line:
                    analysis["message"] = line.strip()[:200]
                    break
            break

    if analysis["error_type"] == "unknown":
        for line in combined.split("\n"):
            if "error" in line.lower():
                analysis["error_type"] = "runtime_error"
                analysis["message"] = line.strip()[:200]
                break

    matches = _TRACEBACK_RE.findall(combined)
    if matches:
        last_file, last_line = matches[-1]
        analysis["file"] = last_file
        analysis["line"] = int(last_line)

    return analysis
