"""Step relevance scoring and step generation."""

from __future__ import annotations

import fnmatch
import math
import os
import re
from typing import Any

from .goal_nlp import _matched_keywords

_RELEVANCE_KEYWORD_ALPHA = 0.7


def _dep_indegree_stats(dep_graph: dict[str, list[str]]) -> tuple[dict[str, int], int]:
    """In-degree per file (how many files import it) and max in-degree for normalization."""
    indeg: dict[str, int] = {}
    for deps in dep_graph.values():
        for d in deps:
            indeg[d] = indeg.get(d, 0) + 1
    mx = max(indeg.values()) if indeg else 0
    return indeg, mx


def _relevance_components(
    filepath: str,
    sym_names: list[str],
    goal_keywords: set[str],
    indegree: dict[str, int],
    max_indegree: int,
) -> tuple[float, float, float]:
    """Return (keyword_score, graph_boost, composite) in [0,1] for prioritization and tiers."""
    if not goal_keywords:
        return 1.0, 0.0, 1.0
    path_words_raw = set(re.findall(r'[a-z]+', filepath.lower()))
    path_words_raw.update(
        p.lower() for p in re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|$)', filepath) if len(p) > 2
    )
    sym_words: set[str] = set()
    for s in sym_names:
        sym_words.update(
            p.lower() for p in re.findall(r'[a-z]+|[A-Z][a-z]*', s) if len(p) > 2
        )
    all_candidate_words = path_words_raw | sym_words
    matched = _matched_keywords(goal_keywords, all_candidate_words)
    keyword_ratio = len(matched) / max(1, len(goal_keywords))

    partial_credit = 0.0
    for kw in goal_keywords:
        if kw not in matched:
            kw_lc = kw.lower()
            for cw in all_candidate_words:
                if len(kw_lc) >= 3 and (kw_lc in cw or cw in kw_lc):
                    partial_credit += 0.5
                    break
    partial_credit = min(partial_credit, 0.3)

    keyword_score = min(keyword_ratio + partial_credit, 1.0)

    if max_indegree <= 0:
        graph_boost = 0.0
    else:
        raw = indegree.get(filepath, 0)
        graph_boost = math.log(1 + raw) / math.log(1 + max_indegree)
    composite = (
        _RELEVANCE_KEYWORD_ALPHA * keyword_score
        + (1.0 - _RELEVANCE_KEYWORD_ALPHA) * graph_boost
    )
    return keyword_score, graph_boost, composite


def _score_relevance(
    filepath: str,
    sym_names: list[str],
    goal_keywords: set[str],
    indegree: dict[str, int],
    max_indegree: int,
) -> float:
    """Composite relevance (backward compatible)."""
    _, _, c = _relevance_components(
        filepath, sym_names, goal_keywords, indegree, max_indegree,
    )
    return c


def _relevance_tier(normalized_composite: float) -> str:
    """Tier label after batch normalization of composite scores."""
    if normalized_composite >= 0.66:
        return "high"
    if normalized_composite >= 0.33:
        return "medium"
    return "low"


def _filter_paths_by_globs(paths: set[str], globs: list[str]) -> set[str]:
    """Keep paths matching any glob (POSIX-style via fnmatch)."""
    if not globs:
        return paths
    out: set[str] = set()
    for p in paths:
        norm = p.replace("\\", "/")
        for g in globs:
            g = g.replace("\\", "/")
            if fnmatch.fnmatch(norm, g) or fnmatch.fnmatch(os.path.basename(norm), g):
                out.add(p)
                break
    return out


def _step_description(
    filepath: str, sym_names: list[str], goal_keywords: set[str] | None = None,
) -> str:
    sym_summary = ", ".join(sym_names[:5])
    if len(sym_names) > 5:
        sym_summary += f" (+{len(sym_names) - 5} more)"
    if goal_keywords:
        path_words = set(re.findall(r'[a-z]+', filepath.lower()))
        sym_words: set[str] = set()
        for s in sym_names:
            sym_words.update(
                p.lower() for p in re.findall(r'[a-z]+|[A-Z][a-z]*', s) if len(p) > 2
            )
        relevant = _matched_keywords(goal_keywords, path_words | sym_words)
        if relevant:
            context = ", ".join(sorted(relevant))
            return f"Modify {filepath} for {context}: {sym_summary}"
    return f"Modify {filepath}: {sym_summary}"


def _step_rationale(
    dep_files: list[str], sym_names: list[str], relevance: float | None = None,
) -> str:
    parts: list[str] = []
    if dep_files:
        summary = ", ".join(dep_files[:3])
        if len(dep_files) > 3:
            summary += f" (+{len(dep_files) - 3} more)"
        parts.append(f"depends on {summary}")
    parts.append(f"contains {len(sym_names)} symbol(s)")
    if relevance is not None:
        parts.append(f"goal relevance: {relevance:.0%}")
    return "; ".join(parts)


def _generate_steps(
    file_order: list[str],
    symbols: dict[str, list[str]],
    dep_graph: dict[str, list[str]],
    goal: str,
    *,
    goal_keywords: set[str] | None = None,
    relevant_only: bool = False,
    min_relevance: float = 0.0,
) -> list[dict[str, Any]]:
    """Generate plan steps from ordered files, their symbols, and dependency info."""
    steps: list[dict[str, Any]] = []
    file_to_step: dict[str, int] = {}

    indeg, max_in = _dep_indegree_stats(dep_graph)

    for filepath in file_order:
        sym_names = symbols.get(filepath, [])
        if not sym_names:
            continue

        kw_s = gr_s = comp = None
        if goal_keywords:
            kw_s, gr_s, comp = _relevance_components(
                filepath, sym_names, goal_keywords, indeg, max_in,
            )

        step_idx = len(steps)
        file_to_step[filepath] = step_idx

        dep_files = dep_graph.get(filepath, [])
        depends_on = [file_to_step[d] for d in dep_files if d in file_to_step]

        step: dict[str, Any] = {
            "step_index": step_idx,
            "file": filepath,
            "symbols": sym_names,
            "symbol_count": len(sym_names),
            "description": _step_description(filepath, sym_names, goal_keywords),
            "rationale": _step_rationale(dep_files, sym_names, comp),
            "depends_on": depends_on,
        }
        if goal_keywords and kw_s is not None and gr_s is not None and comp is not None:
            step["relevance_keyword"] = round(kw_s, 3)
            step["relevance_graph"] = round(gr_s, 3)
            step["relevance"] = round(comp, 3)
        steps.append(step)

    if goal_keywords:
        rel_vals = [s["relevance"] for s in steps if "relevance" in s]
        if len(rel_vals) >= 2:
            lo, hi = min(rel_vals), max(rel_vals)
            if hi > lo:
                for s in steps:
                    if "relevance" in s:
                        r = s["relevance"]
                        s["relevance"] = round((r - lo) / (hi - lo), 3)
        for s in steps:
            if "relevance" in s:
                s["relevance_tier"] = _relevance_tier(s["relevance"])

    if not steps:
        steps = [{
            "step_index": 0,
            "file": "__project__",
            "symbols": ["root"],
            "symbol_count": 1,
            "description": goal[:100],
            "rationale": "No symbols found; treating as whole-project task",
            "depends_on": [],
        }]

    return steps
