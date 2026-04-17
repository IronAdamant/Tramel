"""Scaffold creation, inference, and step generation."""

from __future__ import annotations

import os
import re
from typing import Any

from .goal_nlp import (
    _extract_paths_from_goal,
    _has_creation_intent,
    _keyword_variants,
    _matched_keywords,
)
from .scaffold_templates import match_scaffold_template
from .utils import (
    compute_scaffold_dag_metrics,
    sha256_json,
    topological_sort,
    validate_scaffold,
)

# Creation-hint helpers live in a dedicated module; re-exported here so
# callers keep using ``from trammel.scaffold_logic import _creation_hints``.
from .scaffold_creation import (  # noqa: E402,F401
    _creation_hints,
    _detect_layered_architecture,
    _directories_for_role_hints,
    _fallback_directories,
    _generate_creation_steps,
    _infer_file_name,
    _sibling_convention_clones,
)


def _scaffold_has_entries(scaffold: list[dict[str, Any]] | None) -> bool:
    """True when scaffold lists at least one file path (non-empty greenfield spec)."""
    if not scaffold:
        return False
    return any(e.get("file") for e in scaffold)


def _existing_paths_for_scaffold(
    analysis_root: str, entries: list[dict[str, Any]],
) -> set[str]:
    """Relative paths under analysis_root that exist on disk (scaffold dep resolution)."""
    out: set[str] = set()
    for entry in entries:
        for path in [entry.get("file")] + list(entry.get("depends_on") or []):
            if not path or not isinstance(path, str):
                continue
            norm = path.replace("\\", "/")
            join = os.path.join(analysis_root, *norm.split("/"))
            full = os.path.normpath(join)
            if os.path.isfile(full):
                out.add(norm)
    return out


def _declared_scaffold_graph(entries: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Build dependency graph from scaffold entries (``file`` -> ``depends_on``)."""
    g: dict[str, list[str]] = {}
    for e in entries:
        f = e.get("file")
        if not f:
            continue
        g[f] = [d for d in (e.get("depends_on") or []) if d]
    for deps in list(g.values()):
        for d in deps:
            g.setdefault(d, [])
    return g


def _scaffold_target_paths(entries: list[dict[str, Any]]) -> list[str]:
    return [e["file"] for e in entries if e.get("file")]


def _scaffold_steps(
    scaffold: list[dict[str, Any]],
    start_index: int,
    existing_files: set[str],
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """Generate ordered create-steps from explicit scaffold specs."""
    file_to_pos: dict[str, int] = {}
    for i, entry in enumerate(scaffold):
        f = entry.get("file", "")
        if f:
            file_to_pos[f] = i

    scaffold_graph: dict[str, list[str]] = {}
    for entry in scaffold:
        f = entry.get("file", "")
        if not f:
            continue
        raw_deps = entry.get("depends_on") or []
        scaffold_graph[f] = [d for d in raw_deps if d]

    ordered = topological_sort(scaffold_graph)

    file_to_step: dict[str, int] = {}
    steps: list[dict[str, Any]] = []
    for f in ordered:
        if f not in file_to_pos:
            continue
        entry = scaffold[file_to_pos[f]]
        action = entry.get("action", "create")
        if action == "create" and f in existing_files:
            continue

        step_idx = start_index + len(steps)
        file_to_step[f] = step_idx

        raw_deps = entry.get("depends_on") or []
        depends_on = [file_to_step[d] for d in raw_deps if d in file_to_step]

        if action == "update":
            desc = entry.get("description") or f"Update {f}"
            if not desc.startswith("Update "):
                desc = f"Update {f} — {desc}"
        else:
            desc = entry.get("description") or f"Create {f}"
            if not desc.startswith("Create "):
                desc = f"Create {f} — {desc}"

        steps.append({
            "step_index": step_idx,
            "file": f,
            "action": action,
            "symbols": [],
            "symbol_count": 0,
            "description": desc,
            "rationale": _scaffold_rationale(entry, raw_deps),
            "depends_on": depends_on,
            "relevance_keyword": 1.0,
            "relevance_graph": 0.0,
            "relevance": 1.0,
            "relevance_tier": "high",
        })

    return steps, scaffold_graph


def strategy_to_scaffold(strategy: dict[str, Any]) -> list[dict[str, Any]]:
    """Build ``scaffold``-style entries from a stored strategy for decompose replay."""
    steps = strategy.get("steps") or []
    idx_to_file: dict[int, str] = {}
    for s in steps:
        si = s.get("step_index")
        f = s.get("file")
        if isinstance(si, int) and f:
            idx_to_file[si] = f

    out: list[dict[str, Any]] = []
    for s in steps:
        f = s.get("file")
        if not f or f == "__project__":
            continue
        action = s.get("action")
        sym = s.get("symbol_count")
        if sym is None:
            sym = len(s.get("symbols") or [])
        if action != "create" and sym != 0:
            continue

        entry: dict[str, Any] = {"file": f}
        desc = s.get("description")
        if desc:
            entry["description"] = desc
        raw_deps = s.get("depends_on") or []
        path_deps: list[str] = []
        for d in raw_deps:
            if isinstance(d, int):
                pf = idx_to_file.get(d)
                if pf:
                    path_deps.append(pf)
            elif isinstance(d, str):
                path_deps.append(d)
        if path_deps:
            entry["depends_on"] = path_deps
        out.append(entry)
    return out


def _scaffold_rationale(entry: dict[str, Any], deps: list[str]) -> str:
    """Build a rationale string for a scaffold step."""
    parts: list[str] = ["scaffold: user-specified target"]
    if deps:
        dep_summary = ", ".join(deps[:3])
        if len(deps) > 3:
            dep_summary += f" (+{len(deps) - 3} more)"
        parts.append(f"depends on {dep_summary}")
    return "; ".join(parts)
