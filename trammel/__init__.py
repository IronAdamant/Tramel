"""Trammel: dependency-aware planning, strategy exploration, incremental verification, recipe memory."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as _meta_version
from typing import Any

from .analyzers import PythonAnalyzer, TypeScriptAnalyzer, detect_language
from .core import Planner, get_strategies, register_strategy
from .harness import ExecutionHarness
from .store import RecipeStore

try:
    __version__ = _meta_version("trammel")
except PackageNotFoundError:
    __version__ = "dev"


def plan_and_execute(
    goal: str,
    project_root: str,
    num_beams: int = 3,
    db_path: str = "trammel.db",
    test_cmd: list[str] | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    """Decompose goal, explore beam strategies, verify, and store recipe on success."""
    from .analyzers import get_analyzer
    analyzer = get_analyzer(language) if language else None
    with RecipeStore(db_path) as store:
        planner = Planner(store=store, analyzer=analyzer)
        strategy = planner.decompose(goal, project_root)
        plan_id = store.create_plan(goal, strategy)
        store.update_plan_status(plan_id, "running")

        beams = planner.explore_trajectories(strategy, num_beams=num_beams, store=store)
        harness = ExecutionHarness(test_cmd=test_cmd, analyzer=analyzer)
        best: dict[str, Any] | None = None
        best_score = -1.0

        for beam in beams:
            edits = beam.get("edits") or []
            outcome = harness.run(edits, project_root)
            store.log_trajectory(
                plan_id,
                beam["beam_id"],
                beam.get("variant", "default"),
                outcome.get("steps_completed", len(beam.get("steps", []))),
                outcome,
                failure_reason=outcome.get("failure_reason"),
            )
            sc = float(outcome.get("score", 0.0))
            if outcome.get("success") and (best is None or sc > best_score):
                best_score = sc
                best = {"strategy": strategy, "outcome": outcome, "beam": beam}

        if best:
            store.save_recipe(goal, best["strategy"], True)
            store.update_plan_status(plan_id, "completed")
            return {"status": "ok", **best, "plan_id": plan_id}

        store.update_plan_status(plan_id, "failed")
        return {"status": "failed", "reason": "no passing trajectory", "plan_id": plan_id}


def explore(
    goal: str,
    project_root: str,
    num_beams: int = 3,
    db_path: str = "trammel.db",
    language: str | None = None,
) -> dict[str, Any]:
    """Return decomposition + beam variants without running the harness."""
    from .analyzers import get_analyzer
    analyzer = get_analyzer(language) if language else None
    with RecipeStore(db_path) as store:
        planner = Planner(store=store, analyzer=analyzer)
        strategy = planner.decompose(goal, project_root)
        beams = planner.explore_trajectories(strategy, num_beams=num_beams, store=store)
        return {"strategy": strategy, "beams": beams}


def synthesize(goal: str, strategy: dict[str, Any], db_path: str = "trammel.db") -> None:
    """Persist a verified strategy as a recipe (caller already validated)."""
    with RecipeStore(db_path) as store:
        store.save_recipe(goal, strategy, True)


__all__ = [
    "ExecutionHarness",
    "Planner",
    "PythonAnalyzer",
    "RecipeStore",
    "TypeScriptAnalyzer",
    "__version__",
    "detect_language",
    "explore",
    "get_strategies",
    "plan_and_execute",
    "register_strategy",
    "synthesize",
]
