"""Versioned plan/strategy JSON export for non-MCP external runners.

Produces a self-contained document external orchestrators can load without
the MCP protocol or a live SQLite connection. The on-disk schema is additive:
``format`` + ``format_version`` identify the document; runners should reject
unknown major formats.
"""

from __future__ import annotations

import json
import time
from typing import Any

# Stable identity for exported documents. Bump FORMAT_VERSION when the
# top-level shape changes in a non-backward-compatible way.
EXPORT_FORMAT = "trammel.plan"
EXPORT_FORMAT_VERSION = 1


def _normalize_step(step: dict[str, Any], index: int) -> dict[str, Any]:
    """Project a strategy/plan step into the external-runner shape."""
    deps = step.get("depends_on")
    if not isinstance(deps, list):
        deps = []
    out: dict[str, Any] = {
        "step_index": int(step["step_index"]) if "step_index" in step and step["step_index"] is not None else index,
        "description": str(step.get("description") or ""),
        "rationale": str(step.get("rationale") or ""),
        "depends_on": list(deps),
        "status": str(step.get("status") or "pending"),
    }
    if step.get("file") is not None:
        out["file"] = step.get("file")
    if step.get("id") is not None:
        out["id"] = step.get("id")
    if step.get("symbols") is not None:
        out["symbols"] = step.get("symbols")
    if step.get("edits") is not None:
        out["edits"] = step.get("edits")
    if step.get("verification") is not None:
        out["verification"] = step.get("verification")
    return out


def _write_if_path(doc: dict[str, Any], path: str | None) -> dict[str, Any]:
    if path:
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(doc, fp, indent=2, ensure_ascii=False)
            fp.write("\n")
    return doc


def export_strategy(
    strategy: dict[str, Any],
    *,
    goal: str | None = None,
    path: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Serialize a strategy dict into a versioned export document.

    Parameters
    ----------
    strategy:
        Planner output (``steps``, ``dependency_graph``, optional ``scaffold``).
    goal:
        Human goal string; falls back to ``strategy["goal"]`` when present.
    path:
        Optional filesystem path to write JSON.
    metadata:
        Extra fields nested under ``metadata`` (not merged into the root).
    """
    if not isinstance(strategy, dict):
        raise TypeError("strategy must be a dict")
    raw_steps = strategy.get("steps") or []
    if not isinstance(raw_steps, list):
        raw_steps = []
    steps = [
        _normalize_step(s if isinstance(s, dict) else {}, i)
        for i, s in enumerate(raw_steps)
    ]
    goal_text = goal if goal is not None else strategy.get("goal") or ""
    meta: dict[str, Any] = {}
    for key in ("analysis_meta", "plan_fidelity", "trammel_blind_spots"):
        if key in strategy and strategy[key] is not None:
            meta[key] = strategy[key]
    if metadata:
        meta.update(metadata)

    doc: dict[str, Any] = {
        "format": EXPORT_FORMAT,
        "format_version": EXPORT_FORMAT_VERSION,
        "exported_at": time.time(),
        "goal": str(goal_text),
        "status": "strategy",
        "plan_id": None,
        "steps": steps,
        "strategy": strategy,
        "dependency_graph": strategy.get("dependency_graph") or {},
        "scaffold": strategy.get("scaffold"),
        "constraints": strategy.get("constraints") or [],
        "metadata": meta,
    }
    return _write_if_path(doc, path)


def export_plan(
    plan: dict[str, Any],
    *,
    path: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Serialize a persisted plan (``RecipeStore.get_plan`` shape) for external runners.

    Parameters
    ----------
    plan:
        Dict with at least ``goal`` and ``steps`` (and optionally ``strategy``,
        ``status``, ``id``, ``scaffold``).
    path:
        Optional filesystem path to write JSON.
    metadata:
        Extra fields nested under ``metadata``.
    """
    if not isinstance(plan, dict):
        raise TypeError("plan must be a dict")
    if plan.get("error"):
        # Pass through store/MCP not-found style payloads without inventing data.
        return dict(plan)

    strategy = plan.get("strategy") if isinstance(plan.get("strategy"), dict) else {}
    raw_steps = plan.get("steps") or strategy.get("steps") or []
    if not isinstance(raw_steps, list):
        raw_steps = []
    steps = [
        _normalize_step(s if isinstance(s, dict) else {}, i)
        for i, s in enumerate(raw_steps)
    ]
    meta: dict[str, Any] = {
        "current_step": plan.get("current_step"),
        "total_steps": plan.get("total_steps", len(steps)),
        "created": plan.get("created"),
        "updated": plan.get("updated"),
    }
    if metadata:
        meta.update(metadata)

    doc: dict[str, Any] = {
        "format": EXPORT_FORMAT,
        "format_version": EXPORT_FORMAT_VERSION,
        "exported_at": time.time(),
        "goal": str(plan.get("goal") or ""),
        "status": str(plan.get("status") or "pending"),
        "plan_id": plan.get("id"),
        "steps": steps,
        "strategy": strategy or None,
        "dependency_graph": (strategy or {}).get("dependency_graph") or {},
        "scaffold": plan.get("scaffold") if plan.get("scaffold") is not None else (strategy or {}).get("scaffold"),
        "constraints": (strategy or {}).get("constraints") or [],
        "metadata": meta,
    }
    return _write_if_path(doc, path)


def export_plan_from_store(
    store: Any,
    plan_id: int,
    *,
    path: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load ``plan_id`` from a RecipeStore and export it.

    Returns ``{"error": "plan not found", ...}`` when the id is missing so MCP
    handlers can pass the result through unchanged.
    """
    plan = store.get_plan(int(plan_id))
    if plan is None:
        return {
            "error": "plan not found",
            "format": EXPORT_FORMAT,
            "format_version": EXPORT_FORMAT_VERSION,
            "plan_id": int(plan_id),
        }
    return export_plan(plan, path=path, metadata=metadata)
