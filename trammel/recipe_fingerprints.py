"""Structural fingerprinting and scoring helpers for recipe matching.

Extracted from :mod:`store_recipes` so the recipe CRUD/retrieval module can
stay under the project's 500-LOC target. These helpers build file-role
"fingerprints" from strategies, scaffolds, or raw goal text, and score how
structurally similar two of them are.
"""

from __future__ import annotations

import re
from typing import Any

from .utils import goal_similarity

# ── Pattern constants ────────────────────────────────────────────────────────
#
# File-role and goal-role regex tables are loaded from
# ``trammel/data/patterns.json`` via :mod:`pattern_config`.
from .pattern_config import get_config as _get_pattern_config

_cfg = _get_pattern_config()

_FILE_ROLE_PATTERNS: tuple[tuple[str, str], ...] = _cfg["file_role_patterns"]

_FILE_ROLE_RE: list[tuple[tuple[re.Pattern[str], int], str]] = [
    ((re.compile(pat, re.IGNORECASE), offset), role)
    for offset, (pat, role) in enumerate(_FILE_ROLE_PATTERNS)
]

_GOAL_ROLE_PATTERNS: tuple[tuple[str, str], ...] = _cfg["goal_role_patterns"]

_GOAL_ROLE_RE: list[tuple[re.Pattern[str], str]] = [
    (re.compile(pat, re.IGNORECASE), role)
    for pat, role in _GOAL_ROLE_PATTERNS
]

_ALL_ROLES: tuple[str, ...] = (
    "algorithm", "engine", "service", "route", "controller", "handler",
    "model", "repository", "middleware", "plugin", "registry",
    "collector", "aggregator", "generator", "util", "test", "other",
)

_SCAFFOLD_SIGNALS = frozenset({
    "scaffold", "initialize", "setup", "set up", "from scratch", "bootstrap",
    "new project", "phase 1", "build phase", "create project", "start project",
})
_SCAFFOLD_PENALTY = 0.60  # soft 40% reduction on scaffold patterns for populated projects


# ── Fingerprints ─────────────────────────────────────────────────────────────

def strategy_fingerprint(strategy: dict[str, Any]) -> dict[str, Any]:
    """Extract structural features from a strategy for structural matching.

    Returns a fingerprint dict with role_counts, total_files, create/modify
    counts, avg_symbols_per_file, structural boolean flags, and a fixed-width
    role_vector tuple suitable for cosine comparison.
    """
    steps = strategy.get("steps", [])
    if not steps:
        return {
            "role_counts": {}, "total_files": 0, "create_count": 0,
            "modify_count": 0, "avg_symbols": 0.0,
            "has_test": False, "has_service": False, "has_route": False,
            "has_algorithm": False, "role_vector": (),
        }

    role_counts: dict[str, int] = {}
    total_syms = 0
    has_test = has_service = has_route = has_algorithm = False
    create_count = modify_count = 0

    for s in steps:
        f = s.get("file", "")
        action = s.get("action", "")
        if action == "create":
            create_count += 1
        else:
            modify_count += 1

        sym_count = s.get("symbol_count", 0)
        if sym_count is None:
            sym_count = len(s.get("symbols", []))
        total_syms += sym_count

        for (pat_re, _offset), role in _FILE_ROLE_RE:
            if pat_re.search(f):
                role_counts[role] = role_counts.get(role, 0) + 1
                if role == "test":
                    has_test = True
                elif role == "service":
                    has_service = True
                elif role == "route":
                    has_route = True
                elif role in ("algorithm", "engine"):
                    has_algorithm = True
                break

    avg_syms = total_syms / len(steps) if steps else 0.0
    role_vec = tuple(role_counts.get(r, 0) for r in _ALL_ROLES)

    return {
        "role_counts": role_counts,
        "total_files": len(steps),
        "create_count": create_count,
        "modify_count": modify_count,
        "avg_symbols": round(avg_syms, 2),
        "has_test": has_test,
        "has_service": has_service,
        "has_route": has_route,
        "has_algorithm": has_algorithm,
        "role_vector": role_vec,
    }


def structural_similarity(fp_a: dict[str, Any], fp_b: dict[str, Any]) -> float:
    """Cosine similarity of role vectors, with a capped bonus for shared flags."""
    from .utils import _cosine

    vec_a = list(fp_a.get("role_vector") or ())
    vec_b = list(fp_b.get("role_vector") or ())
    max_len = max(len(vec_a), len(vec_b))
    vec_a = vec_a + [0] * (max_len - len(vec_a))
    vec_b = vec_b + [0] * (max_len - len(vec_b))

    vec_sim = _cosine(vec_a, vec_b)

    bonus = 0.0
    structural_keys = (
        "has_test", "has_service", "has_route", "has_algorithm",
        "has_collector", "has_aggregator", "has_generator",
    )
    for k in structural_keys:
        if fp_a.get(k) and fp_b.get(k):
            bonus += 0.05
    bonus = min(bonus, 0.2)

    return min(vec_sim + bonus, 1.0)


def goal_fingerprint_from_text(goal: str) -> dict[str, Any]:
    """Derive a structural fingerprint from goal text alone (no strategy needed)."""
    goal_lower = goal.lower()
    role_counts: dict[str, int] = {}
    has_test = has_service = has_route = has_algorithm = False
    has_collector = has_aggregator = has_generator = has_registry = has_manager = False

    for pat_re, role in _GOAL_ROLE_RE:
        matches = pat_re.findall(goal_lower)
        if matches:
            role_counts[role] = role_counts.get(role, 0) + len(matches)
            if role == "test":
                has_test = True
            elif role == "service":
                has_service = True
            elif role == "route":
                has_route = True
            elif role in ("algorithm", "engine"):
                has_algorithm = True

    layered_kw = {
        "similarity": [("algorithm", 1), ("engine", 1), ("service", 1), ("route", 1)],
        "optimize": [("algorithm", 1), ("service", 1), ("route", 1)],
        "metric": [("collector", 1), ("aggregator", 1), ("route", 1)],
        "plugin": [("registry", 1), ("manager", 1), ("plugin", 1)],
        "openapi": [("generator", 1)],
    }
    for kw, layers in layered_kw.items():
        if kw in goal_lower:
            for role, count in layers:
                role_counts[role] = role_counts.get(role, 0) + count
                if role == "test":
                    has_test = True
                elif role == "service":
                    has_service = True
                elif role == "route":
                    has_route = True
                elif role in ("algorithm", "engine"):
                    has_algorithm = True
                elif role == "collector":
                    has_collector = True
                elif role == "aggregator":
                    has_aggregator = True
                elif role == "generator":
                    has_generator = True
                elif role == "registry":
                    has_registry = True
                elif role == "manager":
                    has_manager = True

    multi_file_kw = {
        "algorithm": 8, "algorithms": 8,
        "service": 1, "services": 2,
        "route": 1, "routes": 5,
        "endpoint": 3, "endpoints": 6,
        "api": 2,
        "plugin": 1, "plugins": 3,
        "metric": 1, "metrics": 3,
    }
    for kw, count in multi_file_kw.items():
        if kw in goal_lower:
            role_counts["service"] = role_counts.get("service", 0) + count // 4

    role_vec = tuple(role_counts.get(r, 0) for r in _ALL_ROLES)

    return {
        "role_counts": role_counts,
        "total_files": sum(role_counts.values()),
        "create_count": sum(role_counts.values()),
        "modify_count": 0,
        "avg_symbols": 0.0,
        "has_test": has_test,
        "has_service": has_service,
        "has_route": has_route,
        "has_algorithm": has_algorithm,
        "has_collector": has_collector,
        "has_aggregator": has_aggregator,
        "has_generator": has_generator,
        "has_registry": has_registry,
        "has_manager": has_manager,
        "role_vector": role_vec,
    }


def scaffold_fingerprint(scaffold: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract structural fingerprint from a scaffold including DAG metrics."""
    from .scaffold_logic import _declared_scaffold_graph
    from .utils import compute_scaffold_dag_metrics

    graph = _declared_scaffold_graph(scaffold)
    metrics = compute_scaffold_dag_metrics(graph)
    role_counts: dict[str, int] = {}
    for entry in scaffold:
        f = entry.get("file", "")
        for (pat_re, _offset), role in _FILE_ROLE_RE:
            if pat_re.search(f):
                role_counts[role] = role_counts.get(role, 0) + 1
                break

    role_vec = tuple(role_counts.get(r, 0) for r in _ALL_ROLES)
    dag_vec = (
        metrics.get("node_count", 0),
        metrics.get("edge_count", 0),
        metrics.get("critical_path_length", 0),
        metrics.get("max_parallelism", 0),
    )
    return {
        "role_counts": role_counts,
        "role_vector": role_vec,
        "dag_vector": dag_vec,
        "node_count": metrics.get("node_count", 0),
        "edge_count": metrics.get("edge_count", 0),
        "critical_path_length": metrics.get("critical_path_length", 0),
        "max_parallelism": metrics.get("max_parallelism", 0),
    }


def scaffold_structural_similarity(fp_a: dict[str, Any], fp_b: dict[str, Any]) -> float:
    """Compare two scaffold fingerprints using role vectors and DAG metrics (60/40)."""
    from .utils import _cosine

    role_a = list(fp_a.get("role_vector") or ())
    role_b = list(fp_b.get("role_vector") or ())
    max_len = max(len(role_a), len(role_b))
    role_a = role_a + [0] * (max_len - len(role_a))
    role_b = role_b + [0] * (max_len - len(role_b))
    role_sim = _cosine(role_a, role_b)

    dag_a = list(fp_a.get("dag_vector") or ())
    dag_b = list(fp_b.get("dag_vector") or ())
    max_dag = max(len(dag_a), len(dag_b))
    dag_a = dag_a + [0] * (max_dag - len(dag_a))
    dag_b = dag_b + [0] * (max_dag - len(dag_b))
    dag_sim = _cosine(dag_a, dag_b)

    return 0.6 * role_sim + 0.4 * dag_sim


def goal_scaffold_fingerprint_from_text(goal: str) -> dict[str, Any]:
    """Estimate a scaffold fingerprint from goal text for matching stored scaffolds."""
    base = goal_fingerprint_from_text(goal)
    goal_lower = goal.lower()

    node_count = base.get("total_files", 0) or 1

    dep_indicators = ["depends on", "requires", "after", "before", "then", "next", "chain"]
    edge_count = sum(1 for ind in dep_indicators if ind in goal_lower)

    role_vec = base.get("role_vector", ())
    active_roles = sum(1 for r in role_vec if r > 0)
    critical_path_length = max(active_roles, 1)

    plural_kw = ["services", "routes", "controllers", "handlers", "models", "tests"]
    parallelism = 1 + sum(1 for kw in plural_kw if kw in goal_lower)

    dag_vec = (node_count, edge_count, critical_path_length, parallelism)
    base["dag_vector"] = dag_vec
    base["node_count"] = node_count
    base["edge_count"] = edge_count
    base["critical_path_length"] = critical_path_length
    base["max_parallelism"] = parallelism
    return base


def is_scaffold_pattern(pattern: str) -> bool:
    """Detect whether a recipe pattern describes project scaffolding."""
    lower = pattern.lower()
    return any(signal in lower for signal in _SCAFFOLD_SIGNALS)


def recipe_match_components(
    goal: str,
    pattern: str,
    successes: int,
    failures: int,
    updated: float,
    context_files: set[str] | None,
    recipe_files: set[str],
    recipe_strategy: dict[str, Any] | None,
    now: float,
    *,
    w_text: float,
    w_files: float,
    w_success: float,
    w_recency: float,
    w_structural: float,
    recency_half_life: float,
    goal_fingerprint: dict[str, Any] | None = None,
) -> tuple[float, float, dict[str, float]]:
    """Compute text similarity, ranking score, and component breakdown.

    Ranking score mirrors ``retrieve_best_recipe``: text-only when
    ``context_files`` is None; otherwise a weighted composite that also
    includes structural fingerprint similarity when the recipe strategy
    and goal fingerprint are both available. Applies a soft scaffold
    penalty on populated projects.
    """
    text_sim = goal_similarity(goal, pattern)
    if context_files is None:
        return text_sim, text_sim, {"text_similarity": round(text_sim, 3)}

    if recipe_files and context_files:
        file_overlap = len(context_files & recipe_files) / len(context_files | recipe_files)
    else:
        file_overlap = 0.0

    total = successes + failures
    success_ratio = successes / total if total > 0 else 0.5
    recency = 0.5 ** ((now - updated) / recency_half_life)

    struct_sim = 0.0
    if recipe_strategy is not None and goal_fingerprint is not None:
        recipe_fp = strategy_fingerprint(recipe_strategy)
        struct_sim = structural_similarity(goal_fingerprint, recipe_fp)

    score = (
        w_text * text_sim
        + w_files * file_overlap
        + w_success * success_ratio
        + w_recency * recency
        + w_structural * struct_sim
    )
    if is_scaffold_pattern(pattern) and context_files and len(context_files) > 10:
        score *= _SCAFFOLD_PENALTY

    components = {
        "text_similarity": round(text_sim, 3),
        "file_overlap": round(file_overlap, 3),
        "success_ratio": round(success_ratio, 3),
        "recency": round(recency, 3),
        "structural_similarity": round(struct_sim, 3),
    }
    return text_sim, score, components


def sql_in(items: list[str] | tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    """Build an SQL ``IN`` clause plus parameter tuple: ``'IN (?,?)', (a, b)``.

    Raises ValueError on empty input (produces invalid SQL).
    """
    if not items:
        raise ValueError("sql_in requires a non-empty sequence")
    ph = ",".join("?" for _ in items)
    return f"IN ({ph})", tuple(items)
