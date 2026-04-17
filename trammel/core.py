"""Dependency-aware decomposition and bounded beam exploration with real strategy branching."""

from __future__ import annotations

import os
import time as _time
from typing import TYPE_CHECKING, Any

from .store import RecipeStore
from .strategies import (
    StrategyEntry, _STRATEGY_REGISTRY, _split_active_skipped,
)
from .project_config import (
    effective_max_files,
    load_project_config,
    merge_focus_globs,
    merge_focus_keywords,
)
from .utils import sha256_json
from .implicit_deps import ImplicitDependencyGraphEngine
from .constraints import _apply_constraints
from .goal_nlp import _compute_ambiguity_score, _extract_goal_keywords, _extract_paths_from_goal, _has_creation_intent
from .scoring import _filter_paths_by_globs, _generate_steps
from .scaffold_logic import (
    _creation_hints,
    _declared_scaffold_graph,
    _existing_paths_for_scaffold,
    _scaffold_has_entries,
    _scaffold_steps,
    _scaffold_target_paths,
    strategy_to_scaffold,
    compute_scaffold_dag_metrics,
    validate_scaffold,
)

if TYPE_CHECKING:
    from .analyzers import LanguageAnalyzer


def _get_analyzer_registry() -> dict[str, type]:
    """Lazy import to avoid circular dependency."""
    from .analyzers import _ANALYZER_REGISTRY
    return _ANALYZER_REGISTRY


class Planner:
    """Analyze a project and turn a goal into a dependency-aware plan.

    Composes a :class:`~.store.RecipeStore` (for recipe/constraint lookup)
    with a :class:`~.analyzers.LanguageAnalyzer` (for import and symbol
    extraction). The two primary entry points are :meth:`decompose`
    (produce a single strategy) and :meth:`explore_trajectories`
    (fan out a strategy into beam variants).
    """

    def __init__(
        self,
        store: RecipeStore | None = None,
        analyzer: LanguageAnalyzer | None = None,
    ) -> None:
        """Initialize with an optional store and analyzer (both auto-created if omitted)."""
        self.store = store or RecipeStore()
        self._analyzer = analyzer

    def _get_analyzer(self, project_root: str) -> LanguageAnalyzer:
        """Return the configured analyzer, or auto-detect language at ``project_root``."""
        if self._analyzer is not None:
            return self._analyzer
        from .analyzers import detect_language
        return detect_language(project_root)

    def decompose(
        self, goal: str, project_root: str,
        scope: str | None = None, relevant_only: bool = False,
        skip_recipes: bool = False, min_relevance: float = 0.0,
        scaffold: list[dict[str, Any]] | None = None,
        expand_repo: bool | None = None,
        focus_keywords: list[str] | None = None,
        focus_globs: list[str] | None = None,
        max_files: int | None = None,
        strict_greenfield: bool = False,
        apply_project_config: bool = True,
        suppress_creation_hints: bool = False,
    ) -> dict[str, Any]:
        """Decompose ``goal`` into a dependency-aware strategy.

        Walks the project's import graph rooted at ``project_root``
        (optionally scoped), applies active constraints, and checks for
        matching recipes (unless ``skip_recipes`` is set). Returns a dict
        with ``steps``, ``dependency_graph``, ``constraints``, and an
        ``analysis_meta`` block that includes ambiguity and DAG metrics.

        For greenfield work, pass an explicit ``scaffold`` list; otherwise
        the planner falls back to heuristic new-file inference, which can
        produce spurious steps on test-heavy projects. Use
        ``suppress_creation_hints=True`` for refactor/update goals.
        """
        t0 = _time.monotonic()

        matched_recipe: dict[str, Any] | None = None
        recipe_scaffold: list[dict[str, Any]] = []
        if not skip_recipes:
            recipe = self.store.retrieve_best_recipe(goal, min_similarity=0.7)
            if recipe:
                recipe.setdefault("_source", "recipe_exact")
                scaffold_from_recipe = strategy_to_scaffold(recipe)
                if scaffold_from_recipe:
                    recipe["scaffold"] = scaffold_from_recipe
                matched_recipe = recipe

        active_constraints = self.store.get_active_constraints()
        proj_cfg: dict[str, Any] = {}
        if apply_project_config:
            proj_cfg = load_project_config(project_root)
        if scope is None and proj_cfg.get("default_scope"):
            scope = proj_cfg["default_scope"]

        goal_keywords = merge_focus_keywords(
            _extract_goal_keywords(goal), focus_keywords, proj_cfg,
        )
        globs = merge_focus_globs(focus_globs, proj_cfg)
        max_files_effective = effective_max_files(max_files, proj_cfg)

        analysis_root = os.path.join(project_root, scope) if scope else project_root

        if not skip_recipes and matched_recipe is None and scaffold is None:
            scaffold_match = self.store.retrieve_best_scaffold_recipe(goal, min_similarity=0.15)
            if scaffold_match and scaffold_match.get("scaffold"):
                sr = scaffold_match["scaffold"]
                if sr and len(sr) >= 4:
                    scaffold = sr
                    matched_recipe = {"_source": "scaffold_recipe", "scaffold": scaffold}

        if strict_greenfield and _has_creation_intent(goal):
            paths = _extract_paths_from_goal(goal)
            rs = matched_recipe.get("scaffold") if matched_recipe else None
            has_recipe_scaffold = isinstance(rs, list) and len(rs) > 0
            if (
                not paths
                and not _scaffold_has_entries(scaffold)
                and not has_recipe_scaffold
            ):
                raise ValueError(
                    "strict_greenfield requires explicit file paths in the goal, a non-empty "
                    "scaffold, or a matching recipe with scaffold steps; otherwise set "
                    "strict_greenfield=false",
                )

        expand_repo_explicit = expand_repo
        if expand_repo is None:
            expand_repo = not _scaffold_has_entries(scaffold)

        plan_fidelity: dict[str, Any] = {
            "strict_greenfield": strict_greenfield,
            "project_config_applied": bool(apply_project_config and proj_cfg),
            "focus_globs": globs,
            "max_files_cap": max_files_effective,
            "suppress_creation_hints": suppress_creation_hints,
        }

        scaffold_was_provided = scaffold is not None

        if scaffold_was_provided and not _scaffold_has_entries(scaffold):
            if _has_creation_intent(goal) and expand_repo_explicit is not True:
                return {
                    "goal": goal,
                    "steps": [],
                    "dependency_graph": {},
                    "constraints": [c.get("description", "") for c in active_constraints],
                    "constraints_applied": [],
                    "goal_fingerprint": sha256_json(goal)[:16],
                    "analysis_meta": {
                        "warning": (
                            "No scaffold provided for greenfield goal. "
                            "Provide a non-empty scaffold or set expand_repo=true for full-repo decomposition."
                        ),
                    },
                    "plan_fidelity": plan_fidelity,
                    "scaffold_applied": 0,
                    "error": "empty_scaffold",
                }

        if scaffold is not None:
            existing_for_validation = (
                _existing_paths_for_scaffold(analysis_root, scaffold)
                if analysis_root else set()
            )
            validation = validate_scaffold(scaffold, existing_for_validation)
            if not validation["valid"]:
                # Partial-plan recovery: return whatever steps can be inferred
                # from the scaffold even when validation issues are present.
                partial = self._decompose_scaffold_only(
                    goal=goal,
                    project_root=project_root,
                    scope=scope,
                    scaffold=scaffold,
                    skip_recipes=skip_recipes,
                    matched_recipe=matched_recipe,
                    active_constraints=active_constraints,
                    t0=t0,
                )
                partial["plan_fidelity"] = plan_fidelity
                partial["analysis_meta"]["scaffold_validation"] = validation
                partial["analysis_meta"]["warning"] = (
                    f"Scaffold validation issue: {validation['error']}. "
                    "Returning partial plan from scaffold only."
                )
                partial["error"] = validation["error"]
                return partial

        # Guard against massive full-repo expansions when no scaffold exists
        if expand_repo and not _scaffold_has_entries(scaffold) and not scaffold_was_provided:
            if max_files_effective is None or max_files_effective > 15:
                max_files_effective = 15
            plan_fidelity["fallback_file_cap"] = max_files_effective

        if not expand_repo:
            out = self._decompose_scaffold_only(
                goal=goal,
                project_root=project_root,
                scope=scope,
                scaffold=scaffold,
                skip_recipes=skip_recipes,
                matched_recipe=matched_recipe,
                active_constraints=active_constraints,
                t0=t0,
                scaffold_validation=validation,
            )
            out["plan_fidelity"] = plan_fidelity
            return out

        analyzer = self._get_analyzer(analysis_root)

        t1 = _time.monotonic()
        symbols = analyzer.collect_symbols(analysis_root)
        t2 = _time.monotonic()
        dep_graph = analyzer.analyze_imports(analysis_root)
        t3 = _time.monotonic()

        all_files = set(symbols) | set(dep_graph)
        if globs:
            kept = _filter_paths_by_globs(all_files, globs)
            symbols = {k: v for k, v in symbols.items() if k in kept}
            dep_graph = {
                k: [d for d in v if d in kept]
                for k, v in dep_graph.items()
                if k in kept
            }
            all_files = set(symbols) | set(dep_graph)
        if not skip_recipes and matched_recipe is None:
            recipe = self.store.retrieve_best_recipe(goal, context_files=all_files, scaffold=scaffold)
            if recipe:
                recipe.setdefault("_source", "recipe_structural")
                scaffold_from_recipe = strategy_to_scaffold(recipe)
                if scaffold_from_recipe:
                    recipe["scaffold"] = scaffold_from_recipe
                matched_recipe = recipe

        near_matches: list[dict[str, Any]] = []
        if not skip_recipes:
            near_matches = self.store.retrieve_near_matches(
                goal, n=3, context_files=all_files, scaffold=scaffold,
            )

        relevant_graph = {
            f: [d for d in deps if d in all_files]
            for f, deps in dep_graph.items()
            if f in all_files
        }

        implicit_engine = ImplicitDependencyGraphEngine()
        implicit_engine.analyze_project(
            analysis_root,
            {f: f for f in all_files},
            dep_graph,
        )
        relevant_graph = implicit_engine.get_hybrid_dependency_graph(relevant_graph)

        from .utils import topological_sort
        file_order = topological_sort(relevant_graph)
        file_order = [f for f in file_order if f in symbols]

        for f in sorted(symbols.keys()):
            if f not in file_order:
                file_order.append(f)

        meta_truncated = False
        if max_files_effective and len(file_order) > max_files_effective:
            file_order = file_order[:max_files_effective]
            meta_truncated = True
            allowed = set(file_order)
            symbols = {k: v for k, v in symbols.items() if k in allowed}
            relevant_graph = {
                f: [d for d in deps if d in allowed]
                for f, deps in relevant_graph.items()
                if f in allowed
            }
            all_files = set(symbols) | set(relevant_graph)

        steps = _generate_steps(
            file_order, symbols, relevant_graph, goal,
            goal_keywords=goal_keywords, relevant_only=relevant_only,
            min_relevance=min_relevance,
        )
        steps, applied = _apply_constraints(steps, active_constraints)

        if relevant_only and goal_keywords:
            steps.sort(key=lambda s: s.get("relevance", 0.0), reverse=True)
            for i, s in enumerate(steps):
                s["step_index"] = i

        inferred_entries = [
            {"file": p, "description": f"Inferred from goal text: {p}"}
            for p in _extract_paths_from_goal(goal)
            if p not in all_files
        ]

        hints: dict[str, Any] | None = None
        effective_scaffold: list[dict[str, Any]] | None = None
        scaffold_was_provided = scaffold is not None

        if scaffold is not None:
            user_files = {e.get("file") for e in scaffold if e.get("file")}
            extra = [e for e in inferred_entries if e["file"] not in user_files]
            effective_scaffold = list(scaffold) + extra
        elif matched_recipe is not None:
            recipe_scaffold = matched_recipe.get("scaffold", [])
            if recipe_scaffold:
                recipe_files = {e.get("file") for e in recipe_scaffold if e.get("file")}
                extra_inferred = [e for e in inferred_entries if e["file"] not in recipe_files]
                effective_scaffold = list(recipe_scaffold) + extra_inferred

        if scaffold is None:
            if not suppress_creation_hints:
                hints = _creation_hints(goal, goal_keywords, all_files)
            if effective_scaffold is not None:
                existing_files = {e.get("file") for e in effective_scaffold if e.get("file")}
                for h in (hints.get("suggested_files", []) if hints else []):
                    if h["path"] not in existing_files and h["path"] not in all_files:
                        effective_scaffold.append({
                            "file": h["path"],
                            "description": f"Creation hint: {h.get('keyword', h['path'])}",
                            "depends_on": h.get("depends_on", []),
                        })
            else:
                effective_scaffold = list(inferred_entries)
                if hints and hints.get("suggested_files"):
                    existing_files = {e["file"] for e in effective_scaffold if e.get("file")}
                    for s in hints["suggested_files"]:
                        if s["path"] not in existing_files and s["path"] not in all_files:
                            effective_scaffold.append({
                                "file": s["path"],
                                "description": f"Creation hint: {s.get('keyword', s['path'])}",
                                "depends_on": s.get("depends_on", []),
                            })

        if effective_scaffold:
            scaffold_steps, scaffold_graph = _scaffold_steps(
                effective_scaffold, start_index=len(steps), existing_files=all_files,
            )
            if scaffold_steps:
                steps.extend(scaffold_steps)
            for f, deps in scaffold_graph.items():
                relevant_graph.setdefault(f, []).extend(deps)

        t4 = _time.monotonic()

        lang_name = getattr(analyzer, "name", "unknown")

        analysis_meta: dict[str, Any] = {
            "language": lang_name,
            "scope": scope,
            "files_analyzed": len(symbols),
            "dep_files": len(relevant_graph),
            "dep_edges": sum(len(v) for v in relevant_graph.values()),
            "timing_s": {
                "symbols": round(t2 - t1, 3),
                "imports": round(t3 - t2, 3),
                "total": round(t4 - t0, 3),
            },
        }
        if meta_truncated:
            analysis_meta["max_files_truncated"] = True
        if lang_name not in _get_analyzer_registry():
            analysis_meta["warning"] = (
                f"Language '{lang_name}' may not have a native analyzer; results may be approximate"
            )
        if scaffold is not None and 'validation' in locals() and validation is not None:
            analysis_meta["scaffold_validation"] = validation
        if effective_scaffold:
            analysis_meta["scaffold_dag_metrics"] = compute_scaffold_dag_metrics(
                _declared_scaffold_graph(effective_scaffold),
            )

        analysis_meta["ambiguity"] = _compute_ambiguity_score(goal)

        # Strategy suggestion based on trajectory data or cold-start heuristics
        suggested = _suggest_strategy(self.store, goal, lang_name)
        if suggested:
            analysis_meta["suggested_strategy"] = suggested

        if expand_repo and dep_graph:
            gap_analysis = implicit_engine.get_gap_analysis(dep_graph)
            analysis_meta["implicit_dependency_analysis"] = {
                "inferred_edges": gap_analysis["summary"]["totalImplicit"],
                "trammel_blind_spots": gap_analysis["summary"]["trammelBlindSpots"],
                "naming_convention_inferences": sum(
                    1 for d in gap_analysis.get("invisibleToStatic", [])
                    if d.get("type") == "naming_convention"
                ),
                "shared_state_inferences": sum(
                    1 for d in gap_analysis.get("invisibleToStatic", [])
                    if d.get("type") == "shared_state"
                ),
                "pattern_based_inferences": sum(
                    1 for d in gap_analysis.get("invisibleToStatic", [])
                    if d.get("type") == "pattern_based"
                ),
            }

        result: dict[str, Any] = {
            "goal": goal,
            "steps": steps,
            "dependency_graph": relevant_graph,
            "constraints": [c.get("description", "") for c in active_constraints],
            "constraints_applied": [c.get("description", "") for c in applied],
            "goal_fingerprint": sha256_json(goal)[:16],
            "analysis_meta": analysis_meta,
            "expand_repo": True,
            "plan_fidelity": plan_fidelity,
        }
        if near_matches:
            result["near_match_recipes"] = near_matches
        if matched_recipe is not None:
            result["recipe"] = matched_recipe.get("_source")
            if matched_recipe.get("_match"):
                result["recipe_match"] = matched_recipe["_match"]
        if scaffold_was_provided:
            result["scaffold_applied"] = len([s for s in steps if s.get("action") == "create"])
            if inferred_entries:
                result["goal_paths_inferred"] = len(inferred_entries)
        elif effective_scaffold and inferred_entries:
            result["goal_paths_inferred"] = len(inferred_entries)
        if hints and not effective_scaffold:
            result["creation_hints"] = hints
        elif hints and effective_scaffold:
            result["creation_hints"] = hints

        if effective_scaffold:
            result["scaffold"] = effective_scaffold

        return result

    def _decompose_scaffold_only(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Delegate to :func:`planner_helpers.decompose_scaffold_only`."""
        from .planner_helpers import decompose_scaffold_only
        return decompose_scaffold_only(self, *args, **kwargs)

    def explore_trajectories(
        self,
        strategy: dict[str, Any],
        num_beams: int = 3,
    ) -> list[dict[str, Any]]:
        """Generate up to ``num_beams`` execution-order variants of ``strategy``.

        Each variant is produced by a registered strategy function (see
        :mod:`strategies`) — bottom-up, top-down, risk-first, and any
        plugins. Variants are ranked by historical success rate from
        stored trajectories. The number of beams is clamped to
        ``max(3, min(12, cpu_count))``.
        """
        from .planner_helpers import explore_trajectories as _explore
        return _explore(self, strategy, num_beams=num_beams)


# Re-export suggest_strategy (moved to planner_helpers) under its legacy name.
from .planner_helpers import suggest_strategy as _suggest_strategy  # noqa: E402,F401
