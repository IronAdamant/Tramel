"""Component engines for implicit dependency inference.

Split out of :mod:`implicit_deps` to keep both modules under the project's
500-LOC target. Hosts the three helper engines composed by
:class:`~.implicit_deps.ImplicitDependencyGraphEngine`:

- :class:`NamingConventionEngine` — XService→XModel style inferences
- :class:`SharedStateDetector` — modules touching the same files/resources
- :class:`PatternLearner` — frequency-based pattern accumulation
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Any

# ── Naming Convention Rules ──────────────────────────────────────────────────
#
# Loaded from ``trammel/data/patterns.json`` via :mod:`pattern_config`.
# Edit the JSON file to tune inference; no code changes required.
from .pattern_config import get_config as _get_pattern_config

_cfg = _get_pattern_config()
NAMING_CONVENTION_RULES: dict[str, list[tuple[str, float]]] = _cfg["naming_convention_rules"]
DEFAULT_CONVENTION_CONFIDENCE: float = _cfg["default_convention_confidence"]
INFRASTRUCTURE_PATTERNS: list[tuple[str, float]] = _cfg["infrastructure_patterns"]


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
