"""Pattern-based dependency inference.

Extracted from :mod:`implicit_deps_engines` to keep that module under the
500-LOC target. :class:`PatternLearner` records per-pair co-occurrence
counts so frequent-enough file pairings become weak inferred dependencies.
"""

from __future__ import annotations

import os
from collections import defaultdict
from typing import Any

from .implicit_deps_engines import _extract_suffix


class PatternLearner:
    """Learn dependency patterns from existing codebase and successful decompositions.

    Analyzes existing code to extract common patterns:
    - Which modules commonly appear together
    - Common dependency chains
    - Infrastructure usage patterns
    """

    def __init__(self) -> None:
        # Direct dependency tracking: source -> {dep -> count}
        self._direct_deps: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        # Co-occurrence pairs: dep -> {co_dep -> count} (things that appear TOGETHER)
        self._dep_pair_cooccurrence: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        # Suffix-based patterns: suffix -> {common_dep -> count}
        self._suffix_patterns: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._dependency_chains: list[list[str]] = []
        self._infra_deps: set[str] = {"fileStore", "store", "cache", "logger", "config", "utils", "helpers", "database", "db"}

    def learn_from_import_graph(
        self, dep_graph: dict[str, list[str]], existing_files: set[str]
    ) -> None:
        """Learn patterns from an existing import dependency graph.

        Builds multiple pattern structures:
        1. Direct dependencies: what each module depends on
        2. Co-occurrence pairs: which deps appear TOGETHER
        3. Suffix-based patterns: what *Service/*Model/etc modules typically depend on
        """
        all_modules: set[str] = set(dep_graph.keys())
        for deps in dep_graph.values():
            all_modules.update(deps)

        for module in all_modules:
            direct_deps = dep_graph.get(module, [])
            if not direct_deps:
                continue

            # Track direct dependencies
            for dep in direct_deps:
                self._direct_deps[module][dep] += 1

            # Track co-occurrence pairs
            dep_set = set(direct_deps)
            for dep_a in dep_set:
                for dep_b in dep_set:
                    if dep_a != dep_b:
                        self._dep_pair_cooccurrence[dep_a][dep_b] += 1

            # Track suffix-based patterns (what does this suffix category commonly depend on)
            suffix = _extract_suffix(module)
            if suffix:
                for dep in direct_deps:
                    self._suffix_patterns[suffix][dep] += 1

        # Extract chains (sequences of dependencies)
        def follow_chain(node: str, visited: set[str]) -> list[str]:
            chain = [node]
            for dep in sorted(dep_graph.get(node, [])):
                if dep not in visited:
                    visited.add(dep)
                    chain.extend(follow_chain(dep, visited))
            return chain

        for start_node in dep_graph.keys():
            if not dep_graph.get(start_node):
                continue
            chain = follow_chain(start_node, {start_node})
            if len(chain) > 1:
                self._dependency_chains.append(chain)

    def learn_infrastructure_patterns(
        self, module: str, dependencies: list[str], existing_files: set[str]
    ) -> None:
        """Learn which infrastructure modules are commonly depended upon.

        Args:
            module: The module doing the depending
            dependencies: List of modules this module depends on
            existing_files: Set of all existing file paths
        """
        infra_indicators = {"store", "cache", "logger", "config", "utils", "helpers",
                            "fileStore", "database", "db", "api", "client"}

        for dep in dependencies:
            dep_lower = dep.lower()
            if any(indicator in dep_lower for indicator in infra_indicators):
                self._infra_deps.add(dep)

    def get_common_patterns(self, min_frequency: int = 2) -> list[dict[str, Any]]:
        """Get common dependency patterns learned from the codebase.

        Args:
            min_frequency: Minimum co-occurrence count to report a pattern

        Returns:
            List of common pattern dictionaries
        """
        patterns: list[dict[str, Any]] = []

        for source, targets in self._direct_deps.items():
            for target, count in targets.items():
                if count >= min_frequency:
                    patterns.append({
                        "source": source,
                        "target": target,
                        "frequency": count,
                        "confidence": min(0.5 + (count * 0.1), 0.95),
                    })

        return sorted(patterns, key=lambda p: p["frequency"], reverse=True)

    def infer_pattern_dependencies(
        self, source_module: str, all_modules: set[str]
    ) -> list[dict[str, Any]]:
        """Infer dependencies based on learned patterns.

        Uses multiple strategies:
        1. Co-occurrence: if source depends on X, what else do X-depending modules depend on?
        2. Suffix-based: what do *Service/*Model modules typically depend on?
        3. Infrastructure: suggest common infrastructure deps
        """
        inferred: list[dict[str, Any]] = []
        seen: set[str] = set()

        # Strategy 1: Co-occurrence from dependencies
        # If RecipeService depends on RecipeModel, what do other modules that depend on *Model also depend on?
        source_deps = self._direct_deps.get(source_module, {})
        for dep in source_deps:
            # What co-occurs with this dependency?
            co_deps = self._dep_pair_cooccurrence.get(dep, {})
            for co_dep, count in co_deps.items():
                if co_dep not in source_deps and co_dep not in seen and co_dep in all_modules:
                    if count >= 2:  # Must appear with dep at least twice
                        inferred.append({
                            "type": "pattern_based",
                            "source": source_module,
                            "target": co_dep,
                            "confidence": min(0.5 + (count * 0.1), 0.9),
                            "reason": f"Co-occurs with {dep} ({count}x)",
                            "pattern_type": "co_occurrence",
                        })
                        seen.add(co_dep)

        # Strategy 2: Suffix-based patterns
        # What do modules with this suffix typically depend on?
        suffix = _extract_suffix(source_module)
        if suffix:
            suffix_deps = self._suffix_patterns.get(suffix, {})
            for target, count in suffix_deps.items():
                if target not in source_deps and target not in seen and target in all_modules:
                    if count >= 2:
                        inferred.append({
                            "type": "pattern_based",
                            "source": source_module,
                            "target": target,
                            "confidence": min(0.4 + (count * 0.1), 0.85),
                            "reason": f"*{suffix} modules often depend on {target} ({count}x)",
                            "pattern_type": "suffix_pattern",
                        })
                        seen.add(target)

        # Strategy 3: Suggest infrastructure dependencies
        for infra in self._infra_deps:
            infra_file = f"{infra}.js"
            if infra_file not in source_deps and infra_file not in seen and infra_file in all_modules:
                inferred.append({
                    "type": "infrastructure",
                    "source": source_module,
                    "target": infra_file,
                    "confidence": 0.65,
                    "reason": "Common infrastructure dependency",
                    "pattern_type": "infrastructure",
                })
                seen.add(infra_file)

        return inferred
