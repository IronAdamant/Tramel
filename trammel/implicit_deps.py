"""Implicit dependency inference for Trammel decomposition.

Addresses Trammel's blindness to dependencies that cannot be inferred from
static import analysis alone:

1. Naming convention dependencies (XService → XModel)
2. Shared state coupling (multiple modules reading/writing the same file)
3. Pattern-based inference (common infrastructure patterns)
4. Runtime observation coupling (requires execution tracing)

The component engines live in :mod:`implicit_deps_engines`; this module
wires them into :class:`ImplicitDependencyGraphEngine` which produces
hybrid dependency graphs combining explicit imports with inferred
implicit dependencies, weighted by confidence.
"""

from __future__ import annotations

import os
from collections import defaultdict
from typing import Any

from .implicit_deps_engines import (
    NAMING_CONVENTION_RULES,
    NamingConventionEngine,
    SharedStateDetector,
    _extract_base_name,
    _extract_suffix,
)
from .pattern_learner import PatternLearner

__all__ = [
    "NAMING_CONVENTION_RULES",
    "NamingConventionEngine",
    "PatternLearner",
    "SharedStateDetector",
    "ImplicitDependencyGraphEngine",
]


class ImplicitDependencyGraphEngine:
    """Main engine for inferring implicit dependencies.

    Combines naming convention inference, shared state detection,
    and pattern learning to provide a complete dependency view.

    Usage:
        engine = ImplicitDependencyGraphEngine()
        engine.analyze_project(project_root, module_files)

        # Get implicit dependencies for a module
        implicit_deps = engine.get_implicit_dependencies(module_name)

        # Get hybrid graph combining explicit + implicit
        hybrid_graph = engine.get_hybrid_dependency_graph(explicit_graph)
    """

    def __init__(
        self,
        convention_engine: NamingConventionEngine | None = None,
        shared_state_detector: SharedStateDetector | None = None,
        pattern_learner: PatternLearner | None = None,
    ) -> None:
        self.naming_engine = convention_engine or NamingConventionEngine()
        self.shared_state = shared_state_detector or SharedStateDetector()
        self.pattern_learner = pattern_learner or PatternLearner()
        self._project_root: str | None = None
        self._existing_files: set[str] = set()
        self._module_files: dict[str, str] = {}

    def analyze_project(
        self,
        project_root: str,
        module_files: dict[str, str],
        dep_graph: dict[str, list[str]] | None = None,
    ) -> None:
        """Analyze a project to build implicit dependency knowledge.

        Args:
            project_root: Root directory of the project
            module_files: Mapping of module name to file path
            dep_graph: Optional existing import dependency graph for pattern learning
        """
        self._project_root = project_root
        self._module_files = module_files
        self._existing_files = set(module_files.values())

        # Analyze shared state
        self.shared_state.analyze_file_access(project_root, module_files)

        # Learn from dependency graph if provided
        if dep_graph:
            self.pattern_learner.learn_from_import_graph(dep_graph, self._existing_files)

    def get_implicit_dependencies(
        self,
        source_file: str,
        explicit_deps: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Get all implicit dependencies for a source file.

        Combines:
        1. Naming convention dependencies
        2. Shared state dependencies
        3. Pattern-based dependencies

        Args:
            source_file: The file to get dependencies for
            explicit_deps: Explicit dependencies already known (to avoid duplicates)

        Returns:
            List of inferred dependencies sorted by confidence
        """
        explicit_deps = set(explicit_deps or [])
        all_modules = set(self._module_files.values())

        inferred: list[dict[str, Any]] = []

        # 1. Naming convention inference
        convention_deps = self.naming_engine.infer_dependencies(source_file, all_modules)
        for dep in convention_deps:
            if dep["target"] not in explicit_deps:
                inferred.append(dep)

        # 2. Shared state inference
        shared_deps = self.shared_state.infer_shared_state_dependencies(source_file, all_modules)
        for dep in shared_deps:
            if dep["target"] not in explicit_deps:
                inferred.append(dep)

        # 3. Pattern-based inference
        pattern_deps = self.pattern_learner.infer_pattern_dependencies(source_file, all_modules)
        for dep in pattern_deps:
            if dep["target"] not in explicit_deps:
                inferred.append(dep)

        # Sort by confidence descending
        inferred.sort(key=lambda d: d["confidence"], reverse=True)

        return inferred

    def get_hybrid_dependency_graph(
        self,
        explicit_graph: dict[str, list[str]],
    ) -> dict[str, list[str]]:
        """Combine explicit and implicit dependencies into a hybrid graph.

        Args:
            explicit_graph: Dict mapping files to their explicit dependencies

        Returns:
            Hybrid graph with both explicit and inferred dependencies
        """
        hybrid: dict[str, list[str]] = {k: list(v) for k, v in explicit_graph.items()}

        all_files = set(hybrid.keys())
        for source, deps in hybrid.items():
            all_files.update(deps)

        # Track which deps we've already added
        seen_deps: dict[str, set[str]] = defaultdict(set)
        for source, deps in explicit_graph.items():
            seen_deps[source] = set(deps)

        # Add implicit dependencies
        for source in hybrid.keys():
            implicit_deps = self.get_implicit_dependencies(source, list(seen_deps[source]))
            for dep_info in implicit_deps:
                target = dep_info["target"]
                if target not in seen_deps[source]:
                    hybrid.setdefault(source, []).append(target)
                    seen_deps[source].add(target)

        return hybrid

    def get_gap_analysis(
        self, explicit_graph: dict[str, list[str]]
    ) -> dict[str, Any]:
        """Analyze gaps between explicit dependencies and total inferred dependencies.

        Returns:
            Dictionary with gap analysis including:
            - invisibleToStatic: Dependencies only visible via implicit inference
            - trammelCanInfer: Dependencies Trammel can already detect
            - trammelBlindSpots: Dependencies Trammel cannot see
        """
        all_files = set(explicit_graph.keys())
        for deps in explicit_graph.values():
            all_files.update(deps)

        invisible_to_static: list[dict[str, Any]] = []
        trammel_blind_spots: list[dict[str, Any]] = []

        # Collect all implicit deps
        all_implicit: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

        for source in all_files:
            implicit_deps = self.get_implicit_dependencies(source)
            for dep_info in implicit_deps:
                target = dep_info["target"]
                if target not in explicit_graph.get(source, []):
                    if target in all_files:  # Only consider project files
                        all_implicit[source][target] = dep_info

        # Categorize
        for source, targets in all_implicit.items():
            for target, dep_info in targets.items():
                gap_entry = {
                    "module": source,
                    "dep": target,
                    "reason": dep_info["reason"],
                    "confidence": dep_info["confidence"],
                    "type": dep_info["type"],
                }

                if dep_info["type"] == "naming_convention":
                    trammel_blind_spots.append(gap_entry)
                    invisible_to_static.append(gap_entry)
                elif dep_info["type"] == "shared_state":
                    trammel_blind_spots.append(gap_entry)
                    invisible_to_static.append(gap_entry)
                elif dep_info["type"] == "pattern_based":
                    trammel_blind_spots.append(gap_entry)
                    invisible_to_static.append(gap_entry)

        return {
            "invisibleToStatic": invisible_to_static,
            "trammelBlindSpots": trammel_blind_spots,
            "summary": {
                "totalImplicit": len(invisible_to_static),
                "trammelBlindSpots": len(trammel_blind_spots),
                "trammelCanInfer": len(explicit_graph),
            },
        }

    def suggest_dependencies_for_new_module(
        self, module_name: str
    ) -> dict[str, Any]:
        """Suggest what dependencies a new module should have.

        Uses naming conventions and learned patterns to recommend dependencies.

        Args:
            module_name: Name of the new module (e.g., "RecipeService.js")

        Returns:
            Dictionary with must_have, likely_have, may_have dependencies
        """
        all_modules = set(self._module_files.values())

        # Get naming convention suggestions
        naming_suggestion = self.naming_engine.infer_for_new_module(module_name, all_modules)

        # Enhance with pattern learning
        may_have = list(naming_suggestion.get("may_have", []))
        for pattern in self.pattern_learner.get_common_patterns(min_frequency=3):
            if pattern["target"] not in [d["target"] for d in may_have]:
                if pattern["target"] in all_modules:
                    may_have.append({
                        "target": pattern["target"],
                        "confidence": pattern["confidence"] * 0.8,
                        "rule": "learned_pattern",
                    })

        return {
            **naming_suggestion,
            "may_have": may_have,
        }
