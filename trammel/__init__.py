"""Trammel: dependency-aware planning, strategy exploration, incremental verification, recipe memory."""

from __future__ import annotations

import logging
import os
import shutil
from concurrent.futures import ProcessPoolExecutor
from importlib.metadata import PackageNotFoundError, version as _meta_version
from typing import Any

from .analyzers import (
    CppAnalyzer, GoAnalyzer, JavaAnalyzer, PythonAnalyzer,
    RustAnalyzer, TypeScriptAnalyzer, detect_language,
    get_analyzer,
)
from .analyzers_ext2 import (
    CSharpAnalyzer, DartAnalyzer, PhpAnalyzer, RubyAnalyzer, SwiftAnalyzer, ZigAnalyzer,
)
from .core import Planner
from .implicit_deps import (
    ImplicitDependencyGraphEngine,
    NamingConventionEngine,
    PatternLearner,
    SharedStateDetector,
)
from .strategies import get_strategies, register_strategy
from .harness import ExecutionHarness
from .store import RecipeStore
from .utils import DEFAULT_DB_PATH

try:
    __version__ = _meta_version("trammel")
except PackageNotFoundError:
    __version__ = "dev"


def _run_beam(args: tuple[dict[str, Any], str, list[str] | None, str | None]) -> dict[str, Any]:
    """Run a single beam in a subprocess (top-level for pickling)."""
    beam, base_dir, test_cmd, analyzer_name = args
    a = get_analyzer(analyzer_name) if analyzer_name else None
    h = ExecutionHarness(test_cmd=test_cmd, analyzer=a)
    return h.run_from_base(beam.get("edits") or [], base_dir)


def _run_beams_parallel(
    beams: list[dict[str, Any]],
    base_dir: str,
    test_cmd: list[str] | None,
    analyzer: Any,
) -> list[dict[str, Any]]:
    """Run beams concurrently via ProcessPoolExecutor, with sequential fallback."""
    analyzer_name = getattr(analyzer, "name", None)
    args_list = [(b, base_dir, test_cmd, analyzer_name) for b in beams]
    try:
        workers = max(1, min(len(beams), os.cpu_count() or 4))
        with ProcessPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(_run_beam, args_list))
    except OSError:
        # Fork/exec or resource-limit failure — fallback to sequential
        logging.getLogger(__name__).debug(
            "parallel beam execution failed, falling back to sequential", exc_info=True,
        )
        return [_run_beam(a) for a in args_list]


def plan_and_execute(
    goal: str,
    project_root: str,
    num_beams: int = 3,
    db_path: str = DEFAULT_DB_PATH,
    test_cmd: list[str] | None = None,
    language: str | None = None,
    scope: str | None = None,
) -> dict[str, Any]:
    """Decompose goal, explore beam strategies, verify, and store recipe on success."""
    analyzer = get_analyzer(language) if language else None
    with RecipeStore(db_path) as store:
        planner = Planner(store=store, analyzer=analyzer)
        strategy = planner.decompose(goal, project_root, scope=scope)
        plan_id = store.create_plan(goal, strategy, scaffold=strategy.get("scaffold"))
        store.update_plan_status(plan_id, "running")

        beams = planner.explore_trajectories(strategy, num_beams=num_beams)
        harness = ExecutionHarness(test_cmd=test_cmd, analyzer=analyzer)
        best: dict[str, Any] | None = None
        best_score = -1.0

        base_dir = harness.prepare_base(project_root)
        try:
            outcomes = _run_beams_parallel(beams, base_dir, test_cmd, analyzer)
        finally:
            shutil.rmtree(base_dir, ignore_errors=True)

        for beam, outcome in zip(beams, outcomes):
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
    db_path: str = DEFAULT_DB_PATH,
    language: str | None = None,
    scope: str | None = None,
) -> dict[str, Any]:
    """Return decomposition + beam variants without running the harness."""
    analyzer = get_analyzer(language) if language else None
    with RecipeStore(db_path) as store:
        planner = Planner(store=store, analyzer=analyzer)
        strategy = planner.decompose(goal, project_root, scope=scope)
        beams = planner.explore_trajectories(strategy, num_beams=num_beams)
        return {"strategy": strategy, "beams": beams}


def synthesize(goal: str, strategy: dict[str, Any], db_path: str = DEFAULT_DB_PATH) -> None:
    """Persist a verified strategy as a recipe (caller already validated)."""
    with RecipeStore(db_path) as store:
        store.save_recipe(goal, strategy, True)


__all__ = [
    "DEFAULT_DB_PATH",
    "CSharpAnalyzer",
    "CppAnalyzer",
    "DartAnalyzer",
    "ExecutionHarness",
    "GoAnalyzer",
    "ImplicitDependencyGraphEngine",
    "JavaAnalyzer",
    "NamingConventionEngine",
    "PatternLearner",
    "PhpAnalyzer",
    "Planner",
    "PythonAnalyzer",
    "RecipeStore",
    "RubyAnalyzer",
    "RustAnalyzer",
    "SharedStateDetector",
    "SwiftAnalyzer",
    "TypeScriptAnalyzer",
    "ZigAnalyzer",
    "__version__",
    "detect_language",
    "explore",
    "get_analyzer",
    "get_strategies",
    "plan_and_execute",
    "register_strategy",
    "synthesize",
]
