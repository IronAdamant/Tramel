"""Trigram and goal-similarity helpers.

Split out of :mod:`utils` to keep that grab-bag module under the project's
500-LOC target. Re-exported through :mod:`utils` so existing call sites
(``from .utils import goal_similarity, unique_trigrams, ...``) keep
working without churn.
"""

from __future__ import annotations

from collections import Counter


# ── Trigram similarity ───────────────────────────────────────────────────────

def _trigram_list(text: str) -> list[str]:
    """Return a list of overlapping lowercase trigrams (empty if text < 3 chars)."""
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
    """Cosine similarity between two numeric vectors (0.0 on empty input)."""
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
    """Lowercase, expand abbreviations, then map coding verbs to canonical forms."""
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
