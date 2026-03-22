"""Pure stdlib helpers: trigrams, cosine, topological sort, import analysis, DB, JSON."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sqlite3
from collections import Counter, deque
from typing import Any

_IGNORED_DIRS = frozenset({
    ".git", "__pycache__", ".pytest_cache", "venv", ".venv", "node_modules",
    ".tox", ".mypy_cache", ".ruff_cache", ".chisel", "dist", "build",
})


def _is_ignored_dir(name: str) -> bool:
    """Check if a directory should be skipped during project traversal."""
    return name in _IGNORED_DIRS or name.endswith(".egg-info")


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


def trigram_bag_cosine(a: str, b: str) -> float:
    """Cosine similarity over bag-of-trigrams with a shared vocabulary."""
    ca = Counter(_trigram_list(a))
    cb = Counter(_trigram_list(b))
    keys = sorted(set(ca) | set(cb))
    if not keys:
        return 1.0
    va = [float(ca[k]) for k in keys]
    vb = [float(cb[k]) for k in keys]
    return cosine(va, vb)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


# ── Database ─────────────────────────────────────────────────────────────────

def db_connect(path: str = "trammel.db") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ── Import analysis ──────────────────────────────────────────────────────────

def catalog_project_modules(project_root: str) -> dict[str, str]:
    """Map dotted module names to relative file paths for all .py files in the project."""
    modules: dict[str, str] = {}
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if not _is_ignored_dir(d)]
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, project_root)
            mod = rel.replace(os.sep, ".").removesuffix(".py")
            if mod.endswith(".__init__"):
                mod = mod.removesuffix(".__init__")
            modules[mod] = rel
    return modules


def analyze_imports(project_root: str) -> dict[str, list[str]]:
    """Build a dependency graph: file -> [files it imports from] (project-internal only)."""
    modules = catalog_project_modules(project_root)
    module_set = set(modules.keys())
    graph: dict[str, list[str]] = {}

    for mod, rel in modules.items():
        path = os.path.join(project_root, rel)
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                tree = ast.parse(f.read(), filename=path)
        except (OSError, SyntaxError):
            continue

        deps: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    _resolve_import(alias.name, module_set, modules, deps)
            elif isinstance(node, ast.ImportFrom) and node.module:
                _resolve_import(node.module, module_set, modules, deps)

        deps.discard(rel)
        if deps:
            graph[rel] = sorted(deps)

    return graph


def _resolve_import(
    name: str,
    module_set: set[str],
    modules: dict[str, str],
    deps: set[str],
) -> None:
    """Try to match an import name to a project-internal module."""
    if name in module_set:
        deps.add(modules[name])
        return
    parts = name.split(".")
    for i in range(len(parts), 0, -1):
        prefix = ".".join(parts[:i])
        if prefix in module_set:
            deps.add(modules[prefix])
            return


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


def analyze_failure(stderr: str, stdout: str) -> dict[str, Any]:
    """Extract structured failure information from test output."""
    combined = stderr + "\n" + stdout
    analysis: dict[str, Any] = {
        "error_type": "unknown",
        "message": "",
        "file": None,
        "line": None,
        "suggestion": "",
    }

    for marker, etype, suggestion in _ERROR_PATTERNS:
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
            if "Error" in line or "error" in line.lower():
                analysis["error_type"] = "runtime_error"
                analysis["message"] = line.strip()[:200]
                break

    matches = _TRACEBACK_RE.findall(combined)
    if matches:
        last_file, last_line = matches[-1]
        analysis["file"] = last_file
        analysis["line"] = int(last_line)

    return analysis
