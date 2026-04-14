"""Pure stdlib helpers: trigrams, cosine, topological sort, import analysis, DB, JSON."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import random
import re
import sqlite3
import time
from collections import Counter, deque
from collections.abc import Callable, Generator
from typing import Any

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


# ── Trigram similarity ───────────────────────────────────────────────────────

def _trigram_list(text: str) -> list[str]:
    if len(text) < 3:
        return []
    return [text[i : i + 3].lower() for i in range(len(text) - 2)]


def trigram_signature(text: str) -> list[float]:
    """L2-normalized trigram count vector (sorted keys). Used for fingerprints."""
    if len(text) < 3:
        return [1.0]
    counts = Counter(_trigram_list(text))
    vec = [counts[t] for t in sorted(counts)]
    norm = (sum(x * x for x in vec) ** 0.5) or 1.0
    return [x / norm for x in vec]


def unique_trigrams(text: str) -> set[str]:
    """Return the set of distinct trigrams in text (lowercased)."""
    return set(_trigram_list(text))


def trigram_bag_cosine(a: str, b: str) -> float:
    """Cosine similarity over bag-of-trigrams with a shared vocabulary."""
    ca = Counter(_trigram_list(a))
    cb = Counter(_trigram_list(b))
    keys = sorted(set(ca) | set(cb))
    if not keys:
        return 1.0
    va = [float(ca[k]) for k in keys]
    vb = [float(cb[k]) for k in keys]
    return _cosine(va, vb)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    na, nb = sum(x * x for x in a) ** 0.5, sum(y * y for y in b) ** 0.5
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


# ── Goal normalization and similarity ────────────────────────────────────────

_VERB_SYNONYMS: dict[str, str] = {
    v: canonical
    for canonical, variants in {
        "restructure": ["refactor", "rewrite", "rework", "reorganize", "restructure"],
        "fix": ["fix", "repair", "patch", "debug", "resolve"],
        "add": ["add", "create", "implement", "introduce", "build"],
        "remove": ["remove", "delete", "drop", "eliminate"],
        "update": ["update", "modify", "change", "adjust"],
        "move": ["move", "migrate", "relocate", "transfer"],
        "rename": ["rename"],
        "test": ["test", "verify", "validate", "check"],
        "optimize": ["optimize", "improve", "enhance"],
        "extract": ["extract", "split", "separate", "decouple"],
    }.items()
    for v in variants
}

_ABBREVIATIONS: dict[str, str] = {
    "gc": "garbage collector", "db": "database", "auth": "authentication",
    "config": "configuration", "impl": "implementation", "init": "initialization",
    "env": "environment", "deps": "dependencies", "dep": "dependency",
    "repo": "repository", "fn": "function", "func": "function",
    "param": "parameter", "params": "parameters", "args": "arguments",
    "err": "error", "msg": "message", "req": "request", "resp": "response",
    "res": "response", "cmd": "command", "ctx": "context", "util": "utility",
    "utils": "utilities", "lib": "library", "pkg": "package", "dir": "directory",
    "perf": "performance", "opt": "optimize", "mem": "memory",
    "alloc": "allocation", "io": "input output", "ui": "user interface",
    "api": "application programming interface", "cli": "command line interface",
    "orm": "object relational mapping", "sdk": "software development kit",
    "jwt": "json web token", "url": "uniform resource locator",
    "http": "hypertext transfer protocol", "src": "source", "dst": "destination",
    "ref": "reference", "refs": "references", "idx": "index", "tmp": "temporary",
    "async": "asynchronous", "sync": "synchronous",
}

# Lightweight technical thesaurus for recipe retrieval
_TECH_SYNONYMS: dict[str, list[str]] = {
    "websocket": ["socket.io", "real-time transport", "event stream", "realtime"],
    "merge": ["combine", "integrate", "reconcile", "unify"],
    "conflict resolution": ["ot", "crdt", "consistency", "merge"],
    "auth": ["authentication", "authorization", "login", "token"],
    "metric": ["telemetry", "monitoring", "observability", "dashboard"],
    "optimize": ["improve", "enhance", "tune", "refine"],
    "validate": ["verify", "check", "assert", "test"],
    "deploy": ["release", "publish", "ship", "launch"],
    "cache": ["memoize", "store", "buffer"],
    "queue": ["buffer", "stream", "pipeline"],
}


def expand_goal_terms(text: str) -> str:
    """Expand abbreviations, tech synonyms, and normalize verbs for retrieval."""
    words = text.lower().split()
    expanded: list[str] = []
    for w in words:
        expanded.append(_ABBREVIATIONS.get(w, w))
        synonyms = _TECH_SYNONYMS.get(w)
        if synonyms:
            expanded.extend(synonyms)
    return " ".join(_VERB_SYNONYMS.get(w, w) for w in expanded)


def normalize_goal(text: str) -> str:
    """Lowercase, expand abbreviations, then replace coding verbs with canonical synonyms."""
    words = text.lower().split()
    expanded = " ".join(_ABBREVIATIONS.get(w, w) for w in words)
    return " ".join(_VERB_SYNONYMS.get(w, w) for w in expanded.split())


def word_jaccard(a: str, b: str) -> float:
    """Word-level Jaccard similarity between two strings."""
    wa, wb = set(a.split()), set(b.split())
    union = wa | wb
    return len(wa & wb) / len(union) if union else 1.0


def word_substring_score(a: str, b: str) -> float:
    """Partial credit when words are substrings of each other."""
    wa = a.lower().split()
    wb = b.lower().split()
    if not wa or not wb:
        return 0.0
    matches = sum(
        1 for w_a in wa
        if any(w_a in w_b or w_b in w_a for w_b in wb)
    )
    return matches / len(wa)


def goal_similarity(a: str, b: str) -> float:
    """Blended similarity: trigram cosine + word Jaccard + substring on normalized text."""
    tri = trigram_bag_cosine(a, b)
    norm_a = normalize_goal(a)
    norm_b = normalize_goal(b)
    wj = word_jaccard(norm_a, norm_b)
    ws = word_substring_score(norm_a, norm_b)
    return 0.3 * tri + 0.4 * wj + 0.3 * ws


# ── Database ─────────────────────────────────────────────────────────────────

DEFAULT_DB_PATH = "trammel.db"

_BUSY_RETRIES = 5
_BUSY_BASE_DELAY = 0.05


def db_connect(path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextlib.contextmanager
def transaction(
    conn: sqlite3.Connection, immediate: bool = True,
) -> Generator[sqlite3.Connection, None, None]:
    """Execute a block inside an explicit transaction with SQLITE_BUSY retry."""
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
        conn.commit()
    except Exception:
        conn.rollback()
        raise


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


def compute_scaffold_dag_metrics(graph: dict[str, list[str]]) -> dict[str, Any]:
    """Metrics for a scaffold DAG (node = file id; edges = depends_on).

    Aligns with common plan-graph summaries: longest chain length (nodes),
    per-level widths, and max width (parallelism). Uses the same dependency
    convention as ``topological_sort``: each node lists the files it depends on.
    Handles cycles gracefully by using longest-path DP with safe fallbacks.
    """
    g: dict[str, list[str]] = {k: list(v) for k, v in graph.items()}
    all_nodes: set[str] = set(g.keys())
    for targets in g.values():
        all_nodes.update(targets)
    for n in all_nodes:
        g.setdefault(n, [])
    if not all_nodes:
        return {
            "node_count": 0,
            "edge_count": 0,
            "max_dependency_depth": 0,
            "critical_path_length": 0,
            "max_parallelism": 0,
            "layer_widths": [],
        }
    order = topological_sort(g)
    longest_path: dict[str, int] = {}
    for n in order:
        deps = g.get(n, [])
        # Use .get(d, 0) so cycles (where a dependency hasn't been processed yet)
        # don't crash with KeyError.
        longest_path[n] = 1 + max((longest_path.get(d, 0) for d in deps), default=0)
    critical_path_length = max(longest_path.values()) if longest_path else 0
    level: dict[str, int] = {}
    for n in order:
        deps = g.get(n, [])
        level[n] = max((level.get(d, -1) for d in deps), default=-1) + 1
    max_level = max(level.values()) if level else -1
    layer_widths = [0] * (max_level + 1) if max_level >= 0 else []
    for n in all_nodes:
        layer_widths[level[n]] += 1
    max_parallelism = max(layer_widths) if layer_widths else 0
    edge_count = sum(len(v) for v in g.values())
    return {
        "node_count": len(all_nodes),
        "edge_count": edge_count,
        "max_dependency_depth": max_level + 1 if max_level >= 0 else 0,
        "critical_path_length": critical_path_length,
        "max_parallelism": max_parallelism,
        "layer_widths": layer_widths,
    }


def validate_scaffold(
    entries: list[dict[str, Any]],
    existing_files: set[str] | None = None,
) -> dict[str, Any]:
    """Pre-flight validation for scaffold entries.

    Detects cycles, duplicate files, self-referential entries,
    over-constrained nodes (>4 deps), and missing dependencies.
    Returns a dict with ``valid`` bool and diagnostic details.
    """
    result: dict[str, Any] = {
        "valid": True,
        "error": None,
        "cycle": None,
        "duplicates": [],
        "missing_deps": [],
        "over_constrained": [],
        "self_referential": [],
    }

    files = [e.get("file") for e in entries if e.get("file")]
    file_set = set(files)

    # Duplicate files
    seen: set[str] = set()
    for f in files:
        if f in seen:
            result["duplicates"].append(f)
        seen.add(f)
    if result["duplicates"]:
        result["valid"] = False
        result["error"] = "duplicate_files"

    # Build declared graph
    graph: dict[str, list[str]] = {}
    for e in entries:
        f = e.get("file")
        if f:
            graph[f] = [d for d in (e.get("depends_on") or []) if d]

    # Self-referential
    for f, deps in graph.items():
        if f in deps:
            result["self_referential"].append(f)
    if result["self_referential"] and result["valid"]:
        result["valid"] = False
        result["error"] = "self_referential"

    # Over-constrained (>4 deps)
    for f, deps in graph.items():
        if len(deps) > 4:
            result["over_constrained"].append({"file": f, "deps": deps})
    if result["over_constrained"] and result["valid"]:
        result["valid"] = False
        result["error"] = "over_constrained"

    # Missing dependencies
    if existing_files is not None:
        all_known = file_set | existing_files
        for f, deps in graph.items():
            for d in deps:
                if d not in all_known:
                    result["missing_deps"].append({"file": f, "missing": d})
        if result["missing_deps"] and result["valid"]:
            result["valid"] = False
            result["error"] = "missing_dependencies"

    # Cycle detection via DFS
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {f: WHITE for f in graph}

    def dfs(node: str, path: list[str]) -> list[str] | None:
        color[node] = GRAY
        for neighbor in graph.get(node, []):
            if neighbor not in graph:
                continue
            ncolor = color.get(neighbor, WHITE)
            if ncolor == GRAY:
                cycle_start = path.index(neighbor)
                return path[cycle_start:] + [neighbor]
            if ncolor == WHITE:
                cycle = dfs(neighbor, path + [neighbor])
                if cycle:
                    return cycle
        color[node] = BLACK
        return None

    if result["valid"]:
        for f in graph:
            if color[f] == WHITE:
                cycle = dfs(f, [f])
                if cycle:
                    result["cycle"] = cycle
                    result["valid"] = False
                    result["error"] = "circular_dependency"
                    break

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
