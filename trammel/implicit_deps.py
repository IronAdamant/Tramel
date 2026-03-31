"""Implicit dependency inference engine for Trammel decomposition.

This module addresses Trammel's blindness to dependencies that cannot be inferred
from static import analysis alone:
1. Naming convention dependencies (XService → XModel)
2. Shared state coupling (multiple modules reading/writing the same file)
3. Pattern-based inference (common infrastructure patterns)
4. Runtime observation coupling (requires execution tracing)

The engine provides hybrid dependency graphs that combine explicit imports with
inferred implicit dependencies, weighted by confidence.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Any

# ── Naming Convention Rules ──────────────────────────────────────────────────

# Suffix-based dependency rules: source_suffix -> list of expected target suffixes
# Higher confidence when the base name matches (e.g., RecipeService → RecipeModel)
NAMING_CONVENTION_RULES: dict[str, list[tuple[str, float]]] = {
    "Service": [
        ("Model", 0.9),      # RecipeService → RecipeModel
        ("Route", 0.85),     # RecipeService → RecipeRoute
        ("Utils", 0.7),       # Service may use utility functions
    ],
    "Route": [
        ("Service", 0.9),     # RecipeRoute → RecipeService
        ("Model", 0.7),       # Routes often serialize models
    ],
    "Controller": [
        ("Service", 0.85),    # Controller → Service
        ("Model", 0.8),       # Controller → Model
        ("Route", 0.6),       # Controller may define routes
    ],
    "Handler": [
        ("Service", 0.8),     # Handler → Service
        ("Model", 0.75),      # Handler → Model
    ],
    "Engine": [
        ("Model", 0.85),      # Engine operates on models
        ("Service", 0.7),     # Engine may use services
        ("Utils", 0.6),       # Engine may use utilities
    ],
    "Collector": [
        ("Model", 0.8),       # Collector gathers from models
        ("Service", 0.7),     # Collector may push to services
    ],
    "Aggregator": [
        ("Collector", 0.85),  # Aggregator combines collectors
        ("Model", 0.7),
    ],
    "Plugin": [
        ("Registry", 0.8),    # Plugin registers with registry
        ("Service", 0.6),     # Plugin may use services
    ],
    "Registry": [
        ("Plugin", 0.7),      # Registry manages plugins
    ],
    "Manager": [
        ("Service", 0.75),    # Manager coordinates services
        ("Model", 0.6),
    ],
}

# Default confidence for convention matches when suffix isn't in rules
DEFAULT_CONVENTION_CONFIDENCE = 0.5

# Infrastructure patterns: modules that are commonly depended upon
INFRASTRUCTURE_PATTERNS: list[tuple[str, float]] = [
    ("fileStore", 0.7),       # File-based storage abstraction
    ("store", 0.65),          # Generic store
    ("cache", 0.6),           # Caching layer
    ("logger", 0.5),          # Logging utility
    ("config", 0.5),          # Configuration
    ("utils", 0.5),           # Utility modules
    ("helpers", 0.5),         # Helper functions
]


def _extract_base_name(filename: str) -> str:
    """Extract the meaningful base name from a filename (strips common suffixes)."""
    # Remove common extensions
    base = filename
    for ext in (".js", ".ts", ".tsx", ".jsx", ".py", ".go", ".rs", ".java",
                ".kt", ".rb", ".php", ".cs", ".cpp", ".c", ".h"):
        if base.endswith(ext):
            base = base[:-len(ext)]
            break

    # Split on common separators and extract the entity name
    # e.g., "RecipeService.js" → "Recipe"
    parts = re.split(r"[-_]", base)
    if len(parts) > 1:
        # If more than one part, the first capitalized part is likely the entity
        for part in parts:
            if part and part[0].isupper():
                return part

    # CamelCase split: "RecipeService" → "Recipe"
    camel_parts = re.findall(r'[A-Z][a-z]+|[A-Z]+(?=[A-Z]|$)', base)
    if len(camel_parts) > 1:
        return camel_parts[0] if camel_parts else base

    return base


def _extract_suffix(filename: str) -> str | None:
    """Extract the suffix (Service, Route, Model, etc.) from a filename."""
    base = filename
    for ext in (".js", ".ts", ".tsx", ".jsx", ".py", ".go", ".rs", ".java",
                ".kt", ".rb", ".php", ".cs", ".cpp", ".c", ".h"):
        if base.endswith(ext):
            base = base[:-len(ext)]
            break

    # CamelCase suffix: last capitalized segment
    camel_parts = re.findall(r'[A-Z][a-z]+|[A-Z]+(?=[A-Z]|$)', base)
    if camel_parts:
        return camel_parts[-1]

    # Snake_case/kebab-case suffix: last segment after separator
    parts = re.split(r"[-_]", base)
    if len(parts) > 1:
        return parts[-1]

    return None


class NamingConventionEngine:
    """Infer dependencies based on naming conventions.

    Detects patterns like:
    - RecipeService → RecipeModel (Service depends on Model)
    - RecipeRoute → RecipeService (Route depends on Service)
    - OrderController → OrderService, OrderModel
    """

    def __init__(self, rules: dict[str, list[tuple[str, float]]] | None = None) -> None:
        self.rules = rules or NAMING_CONVENTION_RULES

    def infer_dependencies(
        self, source_file: str, existing_files: set[str]
    ) -> list[dict[str, Any]]:
        """Infer dependencies for a source file based on naming conventions.

        Returns list of inferred dependencies with type, target, confidence, and reason.
        """
        inferred: list[dict[str, Any]] = []
        suffix = _extract_suffix(source_file)
        base_name = _extract_base_name(source_file)

        # Only apply naming convention rules if we detected a suffix
        if suffix:
            # Get rules for this suffix
            rule_targets = self.rules.get(suffix, [])

            for target_suffix, base_confidence in rule_targets:
                # Build expected target filename patterns
                target_patterns = [
                    f"{base_name}{target_suffix}",           # RecipeModel
                    f"{base_name.lower()}_{target_suffix.lower()}",  # recipe_model
                    f"{base_name}-{target_suffix.lower()}",   # recipe-model
                ]

                for pattern in target_patterns:
                    # Find matching existing files
                    for ext in (".js", ".ts", ".tsx", ".jsx", ".py", ".go", ".rs"):
                        candidate = f"{pattern}{ext}"
                        if candidate in existing_files:
                            inferred.append({
                                "type": "naming_convention",
                                "source": source_file,
                                "target": candidate,
                                "confidence": base_confidence,
                                "reason": f"{suffix} suffix implies {target_suffix}",
                                "rule": f"{suffix}→{target_suffix}",
                            })
                            break

        # Also check for infrastructure patterns in filename
        for infra_pattern, conf in INFRASTRUCTURE_PATTERNS:
            if infra_pattern.lower() in source_file.lower():
                # Look for generic infrastructure files
                for ext in (".js", ".ts", ".py"):
                    infra_file = f"{infra_pattern}{ext}"
                    if infra_file in existing_files:
                        inferred.append({
                            "type": "infrastructure",
                            "source": source_file,
                            "target": infra_file,
                            "confidence": conf,
                            "reason": f"Common infrastructure dependency",
                            "rule": "infra_pattern",
                        })
                        break

        return inferred

    def infer_for_new_module(
        self, module_name: str, existing_files: set[str]
    ) -> dict[str, Any]:
        """Infer what dependencies a new module would likely have.

        Returns categorized dependencies: mustHave, likelyHave, mayHave.
        """
        suffix = _extract_suffix(module_name)
        base_name = _extract_base_name(module_name)

        must_have: list[dict[str, Any]] = []
        likely_have: list[dict[str, Any]] = []
        may_have: list[dict[str, Any]] = []

        if not suffix:
            return {"must_have": must_have, "likely_have": likely_have, "may_have": may_have}

        rule_targets = self.rules.get(suffix, [])

        for target_suffix, confidence in rule_targets:
            target_patterns = [
                f"{base_name}{target_suffix}",
                f"{base_name.lower()}_{target_suffix.lower()}",
            ]

            for pattern in target_patterns:
                for ext in (".js", ".ts", ".tsx", ".jsx", ".py", ".go", ".rs"):
                    candidate = f"{pattern}{ext}"
                    if candidate in existing_files:
                        dep_info = {
                            "target": candidate,
                            "confidence": confidence,
                            "rule": f"{suffix}→{target_suffix}",
                        }
                        if confidence >= 0.85:
                            must_have.append(dep_info)
                        elif confidence >= 0.7:
                            likely_have.append(dep_info)
                        else:
                            may_have.append(dep_info)
                        break

        # Add infrastructure dependencies
        for infra_pattern, conf in INFRASTRUCTURE_PATTERNS:
            for ext in (".js", ".ts", ".py"):
                infra_file = f"{infra_pattern}{ext}"
                if infra_file in existing_files:
                    may_have.append({
                        "target": infra_file,
                        "confidence": conf,
                        "rule": "infrastructure_pattern",
                    })
                    break

        return {
            "must_have": must_have,
            "likely_have": likely_have,
            "may_have": may_have,
            "trammel_blind_spots": [
                {"type": "naming_convention", "confidence": sum(d["confidence"] for d in must_have) / max(len(must_have), 1)}
            ] if must_have else [],
        }


# ── Shared State Detection ───────────────────────────────────────────────────

# Patterns that indicate file read/write operations
FILE_ACCESS_PATTERNS = [
    re.compile(r"readFile(?:Sync)?\s*\(\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"writeFile(?:Sync)?\s*\(\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"readdir(?:Sync)?\s*\(\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"open\s*\(\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"fs\.readFile(?:Sync)?\s*\(\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"fs\.writeFile(?:Sync)?\s*\(\s*['\"]([^'\"]+)['\"]"),
    # Python patterns
    re.compile(r"open\s*\(\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"Path\s*\(\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"json\.load\s*\(\s*open\s*\(\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"json\.dump\s*\(\s*.*?,\s*open\s*\(\s*['\"]([^'\"]+)['\"]"),
]


class SharedStateDetector:
    """Detect implicit coupling between modules via shared file access.

    Identifies modules that read/write to the same files, indicating tight
    coupling even when they have no explicit import relationship.
    """

    def __init__(self) -> None:
        self._file_access_map: dict[str, set[str]] = defaultdict(set)  # file -> set of modules
        self._module_access_map: dict[str, set[str]] = defaultdict(set)  # module -> set of files

    def analyze_file_access(
        self, project_root: str, module_files: dict[str, str]
    ) -> dict[str, set[str]]:
        """Analyze which modules access which files.

        Args:
            project_root: Root directory of the project
            module_files: Mapping of module name to its file path

        Returns:
            Mapping of data file paths to the modules that access them
        """
        self._file_access_map.clear()
        self._module_access_map.clear()

        # Skip common non-data files
        skip_extensions = {".js", ".ts", ".tsx", ".jsx", ".py", ".go", ".rs",
                          ".java", ".kt", ".rb", ".php", ".cs", ".cpp", ".c", ".h"}

        for module_name, file_path in module_files.items():
            full_path = os.path.join(project_root, file_path)
            if not os.path.isfile(full_path):
                continue

            try:
                with open(full_path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except OSError:
                continue

            for pattern in FILE_ACCESS_PATTERNS:
                for match in pattern.finditer(content):
                    data_path = match.group(1)
                    # Normalize path
                    if data_path.startswith("./"):
                        data_path = data_path[2:]
                    elif data_path.startswith("/"):
                        data_path = data_path[1:]

                    # Skip source code files
                    ext = os.path.splitext(data_path)[1]
                    if ext in skip_extensions:
                        continue

                    # Skip node_modules, .git, etc.
                    if any(ignored in data_path for ignored in ("node_modules", ".git", "venv")):
                        continue

                    self._file_access_map[data_path].add(module_name)
                    self._module_access_map[module_name].add(data_path)

        return dict(self._file_access_map)

    def find_coupled_modules(self, data_file: str) -> list[str]:
        """Find modules that share access to a data file."""
        return sorted(self._file_access_map.get(data_file, set()))

    def infer_shared_state_dependencies(
        self, source_module: str, all_modules: set[str]
    ) -> list[dict[str, Any]]:
        """Infer dependencies based on shared state with other modules.

        If module A writes to shared.json and module B also writes to shared.json,
        they are implicitly coupled - changes to one may affect the other.
        """
        inferred: list[dict[str, Any]] = []
        source_files = self._module_access_map.get(source_module, set())

        for data_file in source_files:
            coupled_modules = self._file_access_map.get(data_file, set()) - {source_module}
            for coupled in coupled_modules:
                if coupled in all_modules:
                    inferred.append({
                        "type": "shared_state",
                        "source": source_module,
                        "target": coupled,
                        "shared_resource": data_file,
                        "confidence": 0.75,
                        "reason": f"Both modules access {data_file}",
                        "coupling_type": "shared_file",
                    })

        return inferred

    def get_shared_state_graph(self) -> dict[str, list[str]]:
        """Get a graph of modules coupled via shared state.

        Returns adjacency list where each module maps to other modules
        it is coupled with via shared file access.
        """
        graph: dict[str, list[str]] = defaultdict(list)
        for data_file, modules in self._file_access_map.items():
            modules_list = sorted(modules)
            for i, mod_a in enumerate(modules_list):
                for mod_b in modules_list[i + 1:]:
                    graph[mod_a].append(mod_b)
                    graph[mod_b].append(mod_a)
        return dict(graph)


# ── Pattern Learning ─────────────────────────────────────────────────────────

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


# ── Implicit Dependency Graph Engine ─────────────────────────────────────────

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
