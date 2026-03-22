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
from typing import Any, Generator

_IGNORED_DIRS = frozenset({
    ".git", "__pycache__", ".pytest_cache", "venv", ".venv", "node_modules",
    ".tox", ".mypy_cache", ".ruff_cache", ".chisel", "dist", "build",
    ".next", ".nuxt", "coverage", ".turbo", ".parcel-cache",
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
    return cosine(va, vb)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


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


def normalize_goal(text: str) -> str:
    """Lowercase text and replace coding verbs with canonical synonyms."""
    return " ".join(_VERB_SYNONYMS.get(w, w) for w in text.lower().split())


def word_jaccard(a: str, b: str) -> float:
    """Word-level Jaccard similarity between two strings."""
    wa = set(a.split())
    wb = set(b.split())
    if not wa and not wb:
        return 1.0
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


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

_BUSY_RETRIES = 5
_BUSY_BASE_DELAY = 0.05


def db_connect(path: str = "trammel.db") -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=5.0)
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
