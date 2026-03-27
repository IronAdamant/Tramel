"""Dependency-aware decomposition and bounded beam exploration with real strategy branching."""

from __future__ import annotations

import math
import os
import re
import time as _time
from typing import TYPE_CHECKING, Any

from .store import RecipeStore
from .strategies import (
    StrategyEntry, _STRATEGY_REGISTRY, _split_active_skipped,
)
from .utils import sha256_json, topological_sort

if TYPE_CHECKING:
    from .analyzers import LanguageAnalyzer


def _get_analyzer_registry() -> dict[str, type]:
    """Lazy import to avoid circular dependency."""
    from .analyzers import _ANALYZER_REGISTRY
    return _ANALYZER_REGISTRY


# ── Goal analysis ────────────────────────────────────────────────────────────

_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "must", "shall", "can",
    "that", "this", "these", "those", "it", "its", "not", "no", "all",
    "any", "each", "every", "some", "into", "about", "up", "out",
    "then", "than", "so", "very", "just", "also", "too", "only", "new",
})

_CREATION_VERBS = frozenset({
    "add", "create", "build", "implement", "introduce", "write",
    "make", "generate", "develop", "establish", "initialize", "scaffold",
    "set", "setup",
})

# When keyword overlap with directory names fails, still suggest role-based dirs.
_ROLE_DIR_SUBSTRINGS = (
    "service", "route", "controller", "model", "test", "schema", "api",
    "handler", "view", "repository", "repo",
)

_CODE_EXT_PATTERN = (
    r"(?:py|js|mjs|cjs|ts|tsx|jsx|go|rs|java|kt|kts|"
    r"c|h|hpp|cpp|cc|cxx|cs|rb|php|sql|md|yaml|yml|json|toml)"
)


def _looks_like_rel_project_path(path: str) -> bool:
    """True if path looks like a relative project file path (conservative)."""
    p = path.strip().replace("\\", "/")
    if not p or ".." in p or p.startswith("/"):
        return False
    return "/" in p or (len(p) > 2 and "." in os.path.basename(p))


def _extract_paths_from_goal(goal: str) -> list[str]:
    """Parse explicit file paths from goal text (backticks, quotes, slash paths).

    Returns deduplicated relative paths normalized with forward slashes.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    ext = _CODE_EXT_PATTERN

    def _push(raw: str) -> None:
        p = raw.strip().replace("\\", "/")
        if not _looks_like_rel_project_path(p) or p in seen:
            return
        seen.add(p)
        ordered.append(p)

    for m in re.finditer(rf"`([^`]+\.{ext})`", goal, re.IGNORECASE):
        _push(m.group(1))
    for m in re.finditer(rf'["\']([^"\']+\.{ext})["\']', goal, re.IGNORECASE):
        _push(m.group(1))
    for m in re.finditer(
        rf"\b((?:[a-zA-Z0-9_.-]+/)+[a-zA-Z0-9_.-]+\.{ext})\b",
        goal,
        re.IGNORECASE,
    ):
        _push(m.group(1))

    return ordered


# Common role directory names to fall back on when project-specific dirs don't match.
# These are used when goal keywords don't match any existing directory paths.
_FALLBACK_ROLE_DIRS = (
    "src/services",
    "src/models",
    "src/routes",
    "src/controllers",
    "src/api",
    "src/handlers",
    "src/lib",
    "src/components",
    "src/features",
)


def _fallback_directories(
    goal_keywords: set[str],
    dirs: dict[str, list[str]],
    existing_files: set[str],
) -> list[dict[str, Any]]:
    """Suggest files in fallback role directories when keyword matching finds nothing.

    When no existing directories match goal keywords, this function suggests new files
    in common role-based directories (src/services, src/models, etc.) using keyword
    patterns to infer appropriate file names.
    """
    suggestions: list[dict[str, Any]] = []
    blob = " ".join(goal_keywords).lower()

    # Detect dominant extension from existing project files
    all_extensions = [os.path.splitext(f)[1] for f in existing_files if os.path.splitext(f)[1]]
    default_ext = max(set(all_extensions), key=all_extensions.count) if all_extensions else ".js"

    # Find which role keywords appear in the goal
    matching_roles: list[str] = []
    for role in _FALLBACK_ROLE_DIRS:
        role_name = role.split("/")[-1]  # "services" -> "service"
        singular = role_name.rstrip("s")
        if role_name in blob or singular in blob:
            matching_roles.append(role)

    # If no explicit role matches, use all fallback dirs
    if not matching_roles:
        matching_roles = list(_FALLBACK_ROLE_DIRS)

    # Keywords to skip (generic terms that create noise)
    skip_kw = frozenset({"src", "lib", "app", "index", "main", "test", "the", "add", "new", "file", "files", "module"})

    # For each role dir, create suggestions using goal keywords
    for role_dir in matching_roles[:5]:
        role_name = role_dir.split("/")[-1]
        singular = role_name.rstrip("s")

        # Get existing files in this specific directory for sibling naming
        existing_in_dir = dirs.get(role_dir, [])
        siblings = sorted(existing_in_dir)

        # Filter keywords to relevant domain terms
        relevant_kw = [kw for kw in goal_keywords if kw not in skip_kw]

        for kw in relevant_kw[:3]:  # Up to 3 keywords per directory
            name = _infer_file_name(kw, siblings)
            # When siblings is empty, _infer_file_name returns just the keyword without extension
            if not siblings:
                name = kw + default_ext
            path = os.path.join(role_dir, name)
            if path not in existing_files:
                suggestions.append({
                    "path": path,
                    "keyword": kw,
                    "directory": role_dir,
                    "inferred_from": siblings[:2] if siblings else [],
                    "fallback": True,
                })

    # Deduplicate by path
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for s in suggestions:
        if s["path"] not in seen:
            seen.add(s["path"])
            deduped.append(s)

    return deduped[:8]


def _directories_for_role_hints(goal_keywords: set[str], dirs: dict[str, list[str]]) -> list[str]:
    """Pick directories whose path segments match common role folder names."""
    if not goal_keywords or not dirs:
        return []
    blob = " ".join(goal_keywords).lower()
    if not any(r in blob for r in _ROLE_DIR_SUBSTRINGS):
        return []
    out: list[str] = []
    for d in sorted(dirs.keys()):
        dl = d.lower().replace("\\", "/")
        if any(seg in dl for seg in _ROLE_DIR_SUBSTRINGS):
            out.append(d)
    return out[:8]


def _extract_goal_keywords(goal: str) -> set[str]:
    """Extract meaningful keywords from a goal, filtering stop words and verbs."""
    words = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', goal.lower())
    expanded: list[str] = []
    for w in words:
        parts = re.findall(r'[a-z]+|[A-Z][a-z]*', w)
        expanded.extend(p.lower() for p in parts)
    return {
        w for w in expanded
        if w not in _STOP_WORDS and w not in _CREATION_VERBS and len(w) > 2
    }


def _has_creation_intent(goal: str) -> bool:
    """Check if the goal implies creating new files/modules.

    Returns True if:
    - A creation verb is present in the goal, OR
    - The goal contains role-keywords (service, route, plugin, engine, etc.)
      that typically imply new file creation
    """
    if set(goal.lower().split()) & _CREATION_VERBS:
        return True
    # Also infer creation intent from role keywords that imply new files
    goal_lower = goal.lower()
    role_kw = {
        "service", "services", "route", "routes", "controller", "controllers",
        "handler", "handlers", "engine", "engines", "plugin", "plugins",
        "registry", "registries", "collector", "aggregator", "middleware",
        "model", "models", "repository", "repositories", "algorithm", "algorithms",
        "generator", "generators", "workflow", "marketplace", "pipeline",
    }
    words = set(re.findall(r'[a-z]+', goal_lower))
    return bool(words & role_kw)


def _keyword_variants(keywords: set[str]) -> set[str]:
    """Expand keywords with plural/singular variants for fuzzy matching."""
    variants = set(keywords)
    for kw in keywords:
        variants.add(kw + "s")
        variants.add(kw + "es")
        if kw.endswith("s"):
            variants.add(kw[:-1])
        if kw.endswith("es") and len(kw) > 2:
            variants.add(kw[:-2])
    return variants


def _matched_keywords(
    goal_keywords: set[str], candidate_words: set[str],
) -> set[str]:
    """Return which goal keywords match any candidate word (variants + substring + CamelCase).

    Uses three-tier matching:
    1. Exact match with plural/singular variants (original behavior)
    2. Substring containment: keyword appears inside candidate or vice versa
    3. CamelCase token overlap: 'workflowAutomation' matches {'workflow', 'automation'}
    """
    matched: set[str] = set()
    variants = _keyword_variants(goal_keywords)

    # Tier 1: exact + variants
    if variants & candidate_words:
        matched.update(kw for kw in goal_keywords if _keyword_variants({kw}) & candidate_words)

    # Tier 2: substring containment (keyword in candidate or candidate in keyword)
    # Also build a set of all goal keywords and variants for fast lookup
    all_goal_terms = variants | goal_keywords
    for kw in goal_keywords:
        kw_lc = kw.lower()
        for cw in candidate_words:
            cw_lc = cw.lower()
            # keyword inside candidate word or vice versa (min length 4 to avoid noise)
            if (len(kw_lc) >= 4 and kw_lc in cw_lc) or (len(cw_lc) >= 4 and cw_lc in kw_lc):
                matched.add(kw)

    return matched


def _dep_indegree_stats(dep_graph: dict[str, list[str]]) -> tuple[dict[str, int], int]:
    """In-degree per file (how many files import it) and max in-degree for normalization."""
    indeg: dict[str, int] = {}
    for deps in dep_graph.values():
        for d in deps:
            indeg[d] = indeg.get(d, 0) + 1
    mx = max(indeg.values()) if indeg else 0
    return indeg, mx


# Blend keyword overlap with import-graph centrality (hub files get credit).
_RELEVANCE_KEYWORD_ALPHA = 0.7


# ── Architecture pattern detection for scaffold inference ─────────────────────

# Role-based directory fragments that imply layered architecture layers.
_LAYER_DIRS: tuple[tuple[str, str], ...] = (
    ("service", "Service layer module"),
    ("services", "Service layer module"),
    ("route", "API route module"),
    ("routes", "API route module"),
    ("controller", "Controller module"),
    ("controllers", "Controller module"),
    ("handler", "Handler module"),
    ("handlers", "Handler module"),
    ("engine", "Engine/core module"),
    ("engines", "Engine/core module"),
    ("algorithm", "Algorithm module"),
    ("algorithms", "Algorithm module"),
    ("collector", "Collector module"),
    ("aggregator", "Aggregator module"),
    ("plugin", "Plugin module"),
    ("plugins", "Plugin module"),
    ("registry", "Registry module"),
    ("middleware", "Middleware module"),
    ("model", "Model module"),
    ("models", "Model module"),
    ("repository", "Repository module"),
    ("repositories", "Repository module"),
    ("util", "Utility module"),
    ("utils", "Utility module"),
)

# Domain keywords that imply specific multi-layer patterns.
_LAYER_PATTERNS: tuple[dict[str, Any], ...] = (
    {
        "keywords": {"similarity", "distance", "comparison", "match"},
        "role": "engine",
        "layers": [
            ("algorithm", "{domain}Algorithms.js"),
            ("engine", "{domain}Vectorizer.js"),
            ("service", "{domain}Service.js"),
            ("route", "{domain}Routes.js"),
        ],
        "test_layers": [
            ("algorithm", "{domain}Algorithms.test.js"),
            ("service", "{domain}Service.test.js"),
        ],
    },
    {
        "keywords": {"optimize", "optimizer", "pareto", "frontier"},
        "role": "service",
        "layers": [
            ("algorithm", "{domain}Optimizer.js"),
            ("service", "{domain}Service.js"),
            ("route", "{domain}Routes.js"),
        ],
        "test_layers": [
            ("algorithm", "{domain}Optimizer.test.js"),
            ("service", "{domain}Service.test.js"),
        ],
    },
    {
        "keywords": {"metric", "metrics", "dashboard", "performance", "monitor"},
        "role": "collector",
        "layers": [
            ("collector", "{domain}Collector.js"),
            ("aggregator", "{domain}Aggregator.js"),
            ("route", "{domain}Routes.js"),
        ],
        "test_layers": [
            ("collector", "{domain}Collector.test.js"),
            ("aggregator", "{domain}Aggregator.test.js"),
        ],
    },
    {
        "keywords": {"plugin", "dynamic", "registry", "extension"},
        "role": "plugin",
        "layers": [
            ("registry", "{domain}Registry.js"),
            ("manager", "{domain}PluginManager.js"),
            ("plugin", "{domain}Plugin.js"),
        ],
        "test_layers": [
            ("registry", "{domain}Registry.test.js"),
        ],
    },
    {
        "keywords": {"openapi", "swagger", "api", "spec", "documentation"},
        "role": "generator",
        "layers": [
            ("generator", "{domain}Generator.js"),
        ],
        "test_layers": [
            ("generator", "{domain}Generator.test.js"),
        ],
    },
)


def _detect_layered_architecture(
    goal: str,
    goal_keywords: set[str],
    existing_files: set[str],
    dirs: dict[str, list[str]],
) -> list[dict[str, Any]] | None:
    """Detect if goal implies a layered architecture pattern and generate scaffold.

    Returns scaffold entries with depends_on chains for multi-layer patterns, or None
    if no clear pattern is detected.
    """
    # Find matching pattern: check if any pattern keyword (or its variants) is in goal keywords
    matched_pattern: dict[str, Any] | None = None
    for pat in _LAYER_PATTERNS:
        for kw in pat["keywords"]:
            variants = {kw, kw + "s", kw.rstrip("s")}
            if variants & goal_keywords:
                matched_pattern = pat
                break
        if matched_pattern:
            break

    if not matched_pattern:
        return None

    # Extract the primary domain keyword
    domain_kw = None
    for kw in sorted(goal_keywords, key=len, reverse=True):
        if kw in goal_keywords and len(kw) > 3 and kw not in {"service", "services", "route", "routes", "plugin", "plugins"}:
            domain_kw = kw
            break

    if not domain_kw:
        return None

    # Find target directory: prefer existing dirs matching the role
    role_dir: str | None = None
    role_label = matched_pattern["role"]
    for d in sorted(dirs.keys()):
        dl = d.lower()
        if role_label in dl or any(seg in dl for seg in ("src/api", "src/services", "src/utils")):
            if "test" not in dl:
                role_dir = d
                break

    if not role_dir:
        # Fallback: find src/ subdir or use first non-test dir
        for d in sorted(dirs.keys()):
            if "test" not in d.split("/"):
                role_dir = d
                break

    if not role_dir:
        return None

    # Build scaffold entries
    scaffold: list[dict[str, Any]] = []
    prev_file: str | None = None

    for layer_type, filename_tpl in matched_pattern["layers"]:
        filename = filename_tpl.format(domain=domain_kw.capitalize())
        path = f"{role_dir}/{filename}"

        if path in existing_files:
            prev_file = path
            continue

        entry: dict[str, Any] = {
            "file": path,
            "description": f"{layer_type}: {filename}",
        }
        if prev_file:
            entry["depends_on"] = [prev_file]
        scaffold.append(entry)
        prev_file = path

    # Add test files
    test_dir = role_dir.replace("src/", "tests/")
    if test_dir == role_dir:
        test_dir = f"{role_dir}.test"
    if "/" in role_dir:
        parts = role_dir.split("/")
        if "src" in parts:
            idx = parts.index("src")
            parts.insert(idx + 1, "tests")
        else:
            parts.insert(0, "tests")
        test_dir = "/".join(parts)

    for layer_type, filename_tpl in matched_pattern["test_layers"]:
        filename = filename_tpl.format(domain=domain_kw.capitalize())
        path = f"{test_dir}/{filename}"

        # Find the layer this test depends on
        layer_filename = filename_tpl.format(domain=domain_kw.capitalize())
        layer_path = f"{role_dir}/{layer_filename}"
        test_entry: dict[str, Any] = {
            "file": path,
            "description": f"test: {filename}",
        }
        if layer_path in existing_files or any(s.get("file") == layer_path for s in scaffold):
            test_entry["depends_on"] = [layer_path]
        scaffold.append(test_entry)

    return scaffold if scaffold else None


def _infer_file_name(keyword: str, siblings: list[str]) -> str:
    """Infer a new filename from a keyword and existing sibling filenames.

    Detects the dominant naming convention (camelCase, snake_case, kebab-case,
    PascalCase) and common suffix from siblings, then applies them to the keyword.
    """
    if not siblings:
        return keyword

    exts = [os.path.splitext(n)[1] for n in siblings if os.path.splitext(n)[1]]
    ext = max(set(exts), key=exts.count) if exts else ""
    bases = [os.path.splitext(n)[0] for n in siblings]

    # Detect separator: underscore, dash, or none (camelCase/PascalCase)
    sep, split_re = "", r'[a-z]+|[A-Z][a-z]*'
    if sum("_" in b for b in bases) > len(bases) // 2:
        sep, split_re = "_", r'[^_]+'
    elif sum("-" in b for b in bases) > len(bases) // 2:
        sep, split_re = "-", r'[^-]+'

    # Common trailing parts across siblings
    suffix_parts: list[str] = []
    if len(bases) >= 2:
        all_parts = [re.findall(split_re, b) for b in bases]
        all_parts = [p for p in all_parts if p]
        if len(all_parts) >= 2:
            for items in zip(*(reversed(p) for p in all_parts)):
                if len(set(items)) == 1:
                    suffix_parts.append(items[0])
                else:
                    break
            suffix_parts.reverse()

    if suffix_parts:
        return keyword.lower() + sep + sep.join(suffix_parts) + ext

    # No common suffix — use dominant casing
    if sum(b[:1].isupper() for b in bases) > len(bases) // 2:
        return keyword.capitalize() + ext
    return keyword.lower() + ext


def _creation_hints(
    goal: str,
    goal_keywords: set[str],
    existing_files: set[str],
) -> dict[str, Any] | None:
    """When goal indicates creation intent, return context + suggested new files."""
    if not _has_creation_intent(goal):
        return None

    # Build directory -> contents from existing files
    dirs: dict[str, list[str]] = {}
    for f in existing_files:
        parent = os.path.dirname(f)
        if parent:
            dirs.setdefault(parent, []).append(os.path.basename(f))

    # Try layered architecture detection first (Issue 1 fix: detect multi-layer patterns)
    layered = _detect_layered_architecture(goal, goal_keywords, existing_files, dirs)
    if layered:
        return {
            "creation_intent": True,
            "goal_entities": sorted(goal_keywords),
            "relevant_directories": [],
            "directory_structure": {},
            "suggested_files": [{"path": e["file"], "keyword": e["file"].split("/")[-1].split(".")[0], "directory": os.path.dirname(e["file"]), "inferred_from": [], "layered": True, "depends_on": e.get("depends_on", [])} for e in layered],
            "layered_scaffold": layered,
        }

    # Find directories relevant to goal keywords
    kw_variants = _keyword_variants(goal_keywords)
    relevant_dirs: list[str] = []
    for d in sorted(dirs.keys()):
        dir_words = set(re.findall(r'[a-z]+', d.lower()))
        if dir_words & kw_variants:
            relevant_dirs.append(d)

    if not relevant_dirs:
        relevant_dirs = _directories_for_role_hints(goal_keywords, dirs)

    # Infer suggested new files from goal keywords + sibling naming patterns
    suggested: list[dict[str, Any]] = []
    for d in relevant_dirs:
        siblings = sorted(dirs.get(d, []))
        dir_words = set(re.findall(r'[a-z]+', d.lower()))
        qualifiers = goal_keywords - dir_words
        for kw in sorted(qualifiers):
            name = _infer_file_name(kw, siblings)
            path = os.path.join(d, name)
            if path not in existing_files:
                suggested.append({
                    "path": path,
                    "keyword": kw,
                    "directory": d,
                    "inferred_from": siblings[:3],
                })

    # When no relevant directories found, use fallback role directories
    if not suggested:
        suggested = _fallback_directories(goal_keywords, dirs, existing_files)

    suggested = suggested[:8]

    return {
        "creation_intent": True,
        "goal_entities": sorted(goal_keywords),
        "relevant_directories": relevant_dirs,
        "directory_structure": {
            d: sorted(dirs[d]) for d in relevant_dirs
        } if relevant_dirs else {},
        "suggested_files": suggested,
    }


def _generate_creation_steps(
    hints: dict[str, Any] | None,
    start_index: int,
) -> list[dict[str, Any]]:
    """Generate 'create' steps from creation hints' suggested files."""
    if not hints:
        return []
    suggested = hints.get("suggested_files", [])
    if not suggested:
        return []

    # P5: Build goal context for descriptions
    goal_entities = hints.get("goal_entities", [])
    entity_summary = ", ".join(goal_entities[:4])

    # Map file path -> step index for dependency resolution
    file_to_step: dict[str, int] = {}
    steps: list[dict[str, Any]] = []

    for s in suggested:
        path = s["path"]
        kw = s["keyword"]
        inferred = s.get("inferred_from", [])
        is_layered = s.get("layered", False)
        step_idx = start_index + len(steps)
        file_to_step[path] = step_idx

        if is_layered:
            rationale = f"Layered architecture pattern: {s.get('directory', os.path.dirname(path))}"
            desc = s.get("description", f"Create {path}")
        else:
            rationale = (
                f"Inferred from goal keyword '{kw}' + directory pattern "
                f"(siblings: {', '.join(inferred)})"
                if inferred
                else f"Inferred from goal keyword '{kw}'"
            )
            # P5: Goal-aware description instead of bare "Create {path}"
            desc = f"Create {path} — implement {kw} module"
            if entity_summary and kw not in entity_summary:
                desc += f" (related: {entity_summary})"

        # Resolve depends_on from layered scaffold (file paths -> step indices)
        raw_deps: list[str] = s.get("depends_on", [])
        resolved_deps = [file_to_step[d] for d in raw_deps if d in file_to_step]

        steps.append({
            "step_index": step_idx,
            "file": path,
            "action": "create",
            "symbols": [],
            "symbol_count": 0,
            "description": desc,
            "rationale": rationale,
            "depends_on": resolved_deps,
            "relevance": 1.0,
        })
    return steps


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


def _scaffold_steps(
    scaffold: list[dict[str, Any]],
    start_index: int,
    existing_files: set[str],
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """Generate ordered create-steps from explicit scaffold specs.

    Returns (steps, dependency_graph) where dependency_graph maps scaffold
    file paths to their declared dependencies (for merging into the main graph).
    """
    # Index: scaffold file path -> position in scaffold list
    file_to_pos: dict[str, int] = {}
    for i, entry in enumerate(scaffold):
        f = entry.get("file", "")
        if f:
            file_to_pos[f] = i

    # Build dependency graph from scaffold entries
    scaffold_graph: dict[str, list[str]] = {}
    for entry in scaffold:
        f = entry.get("file", "")
        if not f:
            continue
        raw_deps = entry.get("depends_on") or []
        scaffold_graph[f] = [d for d in raw_deps if d]

    # Topological sort scaffold entries so dependencies come first
    ordered = topological_sort(scaffold_graph)

    # Map scaffold file -> step index (offset by start_index)
    file_to_step: dict[str, int] = {}
    steps: list[dict[str, Any]] = []
    for f in ordered:
        if f not in file_to_pos:
            continue  # dependency target that's an existing file, not a scaffold entry
        entry = scaffold[file_to_pos[f]]
        if f in existing_files:
            continue  # skip files that already exist

        step_idx = start_index + len(steps)
        file_to_step[f] = step_idx

        # Resolve depends_on to step indices (both scaffold and existing-file steps)
        raw_deps = entry.get("depends_on") or []
        depends_on = [file_to_step[d] for d in raw_deps if d in file_to_step]

        desc = entry.get("description") or f"Create {f}"
        if not desc.startswith("Create "):
            desc = f"Create {f} — {desc}"

        steps.append({
            "step_index": step_idx,
            "file": f,
            "action": "create",
            "symbols": [],
            "symbol_count": 0,
            "description": desc,
            "rationale": _scaffold_rationale(entry, raw_deps),
            "depends_on": depends_on,
            "relevance": 1.0,
        })

    return steps, scaffold_graph


def strategy_to_scaffold(strategy: dict[str, Any]) -> list[dict[str, Any]]:
    """Build ``scaffold``-style entries from a stored strategy for decompose replay.

    Includes steps with ``action == 'create'`` or zero symbols (new-file placeholders),
    maps integer ``depends_on`` indices to file paths, and preserves string path deps.
    """
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


def _score_relevance(
    filepath: str,
    sym_names: list[str],
    goal_keywords: set[str],
    indegree: dict[str, int],
    max_indegree: int,
) -> float:
    """Score how relevant a file is to the goal (0.0 to 1.0).

    Uses improved fuzzy keyword matching that handles:
    - Plural/singular variants (original)
    - Substring containment (keyword inside path word or vice versa)
    - CamelCase token splitting for compound identifiers
    """
    if not goal_keywords:
        return 1.0
    # Extract words from filepath: standard lowercase words + CamelCase splits
    path_words_raw = set(re.findall(r'[a-z]+', filepath.lower()))
    # Also split CamelCase/PascalCase: workflowAutomationEngine -> workflow, automation, engine
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

    # Partial match bonus: if any goal keyword is a substring of a path/sym word, give partial credit
    partial_credit = 0.0
    for kw in goal_keywords:
        if kw not in matched:
            kw_lc = kw.lower()
            for cw in all_candidate_words:
                if len(kw_lc) >= 3 and (kw_lc in cw or cw in kw_lc):
                    partial_credit += 0.5  # half credit for substring matches
                    break
    partial_credit = min(partial_credit, 0.3)  # cap partial credit at 0.3

    keyword_score = min(keyword_ratio + partial_credit, 1.0)

    if max_indegree <= 0:
        graph_boost = 0.0
    else:
        raw = indegree.get(filepath, 0)
        graph_boost = math.log(1 + raw) / math.log(1 + max_indegree)
    return (
        _RELEVANCE_KEYWORD_ALPHA * keyword_score
        + (1.0 - _RELEVANCE_KEYWORD_ALPHA) * graph_boost
    )


# ── Step generation ──────────────────────────────────────────────────────────

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

        relevance = (
            _score_relevance(filepath, sym_names, goal_keywords, indeg, max_in)
            if goal_keywords else None
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
            "rationale": _step_rationale(dep_files, sym_names, relevance),
            "depends_on": depends_on,
        }
        if relevance is not None:
            step["relevance"] = round(relevance, 3)
        steps.append(step)

    # Spread scores within this batch so similarly-ranked files do not cluster (plan prioritization)
    if goal_keywords and len(steps) > 1:
        rel_vals = [s["relevance"] for s in steps if "relevance" in s]
        if len(rel_vals) >= 2:
            lo, hi = min(rel_vals), max(rel_vals)
            if hi > lo:
                for s in steps:
                    if "relevance" in s:
                        r = s["relevance"]
                        s["relevance"] = round((r - lo) / (hi - lo), 3)

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


# ── Constraint enforcement ────────────────────────────────────────────────────

def _parse_constraints(
    constraints: list[dict[str, Any]],
) -> tuple[set[str], list[tuple[str, str]], list[tuple[str, str]], list[str], list[dict[str, Any]]]:
    """Categorize constraints by type.

    Returns (avoid_files, required_orderings, incompatible_pairs, required_files, applied).
    """
    applied: list[dict[str, Any]] = []
    avoid_files: set[str] = set()
    required_orderings: list[tuple[str, str]] = []
    incompatible_pairs: list[tuple[str, str]] = []
    required_files: list[str] = []

    for c in constraints:
        ctx = c.get("context", {})
        ctype = c.get("type", "")
        if ctype == "avoid" and ctx.get("file"):
            avoid_files.add(ctx["file"])
            applied.append(c)
        elif ctype == "dependency":
            before = ctx.get("before") or ctx.get("dependency")
            after = ctx.get("after") or ctx.get("dependent")
            if before and after:
                required_orderings.append((before, after))
                applied.append(c)
        elif ctype == "incompatible":
            file_a = ctx.get("file_a") or ctx.get("file")
            file_b = ctx.get("file_b") or ctx.get("other")
            if file_a and file_b:
                incompatible_pairs.append((file_a, file_b))
                applied.append(c)
        elif ctype == "requires" and (ctx.get("file") or ctx.get("prerequisite")):
            required_files.append(ctx.get("file") or ctx["prerequisite"])
            applied.append(c)

    return avoid_files, required_orderings, incompatible_pairs, required_files, applied


def _mark_avoided(steps: list[dict[str, Any]], avoid_files: set[str]) -> list[dict[str, Any]]:
    """Mark steps targeting avoided files as skipped."""
    result: list[dict[str, Any]] = []
    for step in steps:
        f = step.get("file", "")
        if f in avoid_files:
            skipped = step.copy()
            skipped["status"] = "skipped"
            skipped["skip_reason"] = f"constraint: avoid {f}"
            result.append(skipped)
        else:
            result.append(step)
    return result


def _inject_orderings(steps: list[dict[str, Any]], orderings: list[tuple[str, str]]) -> None:
    """Inject dependency edges from ordering constraints (mutates steps in place)."""
    file_to_idx = {f: i for i, s in enumerate(steps) if (f := s.get("file")) is not None}
    for before, after in orderings:
        if before in file_to_idx and after in file_to_idx:
            after_step = steps[file_to_idx[after]]
            deps = list(after_step.get("depends_on", []))
            before_idx = file_to_idx[before]
            if before_idx not in deps:
                after_step["depends_on"] = deps + [before_idx]


def _mark_incompatible(steps: list[dict[str, Any]], pairs: list[tuple[str, str]]) -> None:
    """Record incompatible-pair metadata on steps (mutates steps in place)."""
    for file_a, file_b in pairs:
        for step in steps:
            f = step.get("file", "")
            if f == file_a:
                step.setdefault("incompatible_with", []).append(file_b)
            elif f == file_b:
                step.setdefault("incompatible_with", []).append(file_a)


def _add_prerequisites(steps: list[dict[str, Any]], required_files: list[str]) -> None:
    """Append placeholder steps for missing prerequisite files (mutates list)."""
    existing = {s.get("file") for s in steps}
    for prereq in required_files:
        if prereq not in existing:
            steps.append({
                "step_index": len(steps),
                "file": prereq,
                "symbols": [],
                "symbol_count": 0,
                "description": f"Required prerequisite: {prereq}",
                "rationale": "Added by 'requires' constraint",
                "depends_on": [],
            })


def _apply_constraints(
    steps: list[dict[str, Any]],
    constraints: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Enforce active constraints on steps.

    Returns (modified_steps, applied_constraints).
    """
    if not constraints:
        return steps, []

    avoid_files, orderings, incompat, prereqs, applied = _parse_constraints(constraints)
    filtered = _mark_avoided(steps, avoid_files)
    _inject_orderings(filtered, orderings)
    _mark_incompatible(filtered, incompat)
    _add_prerequisites(filtered, prereqs)
    return filtered, applied


# ── Planner ──────────────────────────────────────────────────────────────────

class Planner:
    def __init__(
        self,
        store: RecipeStore | None = None,
        analyzer: LanguageAnalyzer | None = None,
    ) -> None:
        self.store = store or RecipeStore()
        self._analyzer = analyzer

    def _get_analyzer(self, project_root: str) -> LanguageAnalyzer:
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
    ) -> dict[str, Any]:
        t0 = _time.monotonic()

        # Fast path: exact text match without project scan
        # P1: skip_recipes bypasses both recipe gates; fast path uses stricter threshold
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
        goal_keywords = _extract_goal_keywords(goal)

        analysis_root = os.path.join(project_root, scope) if scope else project_root

        # Fix 1: scaffold recipe lookup — before heavy analysis (no project scan).
        if not skip_recipes and matched_recipe is None and scaffold is None:
            scaffold_match = self.store.retrieve_best_scaffold_recipe(goal)
            if scaffold_match and scaffold_match.get("scaffold"):
                sr = scaffold_match["scaffold"]
                if sr:
                    scaffold = sr

        # Default: scaffold-only (no full-repo symbol/import scan) when scaffold has entries.
        # Set expand_repo=true to merge scaffold steps with full decomposition (legacy behavior).
        if expand_repo is None:
            expand_repo = not _scaffold_has_entries(scaffold)

        if not expand_repo:
            return self._decompose_scaffold_only(
                goal=goal,
                project_root=project_root,
                scope=scope,
                scaffold=scaffold,
                skip_recipes=skip_recipes,
                matched_recipe=matched_recipe,
                active_constraints=active_constraints,
                t0=t0,
            )

        analyzer = self._get_analyzer(analysis_root)

        t1 = _time.monotonic()
        symbols = analyzer.collect_symbols(analysis_root)
        t2 = _time.monotonic()
        dep_graph = analyzer.analyze_imports(analysis_root)
        t3 = _time.monotonic()

        # Structural recipe match: try again with file context
        all_files = set(symbols) | set(dep_graph)
        if not skip_recipes and matched_recipe is None:
            recipe = self.store.retrieve_best_recipe(goal, context_files=all_files)
            if recipe:
                recipe.setdefault("_source", "recipe_structural")
                scaffold_from_recipe = strategy_to_scaffold(recipe)
                if scaffold_from_recipe:
                    recipe["scaffold"] = scaffold_from_recipe
                matched_recipe = recipe

        # Collect near-miss recipes for reference
        near_matches: list[dict[str, Any]] = []
        if not skip_recipes:
            near_matches = self.store.retrieve_near_matches(
                goal, n=3, context_files=all_files,
            )

        # Build steps from existing project files
        relevant_graph = {
            f: [d for d in deps if d in all_files]
            for f, deps in dep_graph.items()
            if f in all_files
        }

        file_order = topological_sort(relevant_graph)
        file_order = [f for f in file_order if f in symbols]

        for f in sorted(symbols.keys()):
            if f not in file_order:
                file_order.append(f)

        steps = _generate_steps(
            file_order, symbols, relevant_graph, goal,
            goal_keywords=goal_keywords, relevant_only=relevant_only,
            min_relevance=min_relevance,
        )
        steps, applied = _apply_constraints(steps, active_constraints)

        # Fix 3: when relevant_only, sort by relevance DESC so most-relevant files
        # appear first instead of discarding below-threshold files entirely
        if relevant_only and goal_keywords:
            steps.sort(key=lambda s: s.get("relevance", 0.0), reverse=True)
            # Re-index after sort
            for i, s in enumerate(steps):
                s["step_index"] = i

        # Paths explicitly mentioned in goal text
        inferred_entries = [
            {"file": p, "description": f"Inferred from goal text: {p}"}
            for p in _extract_paths_from_goal(goal)
            if p not in all_files
        ]

        # Determine scaffold: explicit user scaffold > recipe scaffold > creation hints
        # If scaffold arg is provided (including []), use it as base
        # Otherwise, if we have a matched recipe with scaffold files, use those
        # Finally, always attempt _creation_hints to supplement any gaps
        hints: dict[str, Any] | None = None
        effective_scaffold: list[dict[str, Any]] | None = None
        scaffold_was_provided = scaffold is not None  # track even if scaffold=[]

        if scaffold is not None:
            # User explicitly provided scaffold
            user_files = {e.get("file") for e in scaffold if e.get("file")}
            extra = [e for e in inferred_entries if e["file"] not in user_files]
            effective_scaffold = list(scaffold) + extra
        elif matched_recipe is not None:
            # Use recipe scaffold as base, then supplement with hints
            recipe_scaffold = matched_recipe.get("scaffold", [])
            if recipe_scaffold:
                recipe_files = {e.get("file") for e in recipe_scaffold if e.get("file")}
                extra_inferred = [e for e in inferred_entries if e["file"] not in recipe_files]
                effective_scaffold = list(recipe_scaffold) + extra_inferred

        # Always run creation_hints to catch goal keywords the recipe might miss
        # (regardless of _has_creation_intent — the hint function itself is the gate)
        if scaffold is None:
            hints = _creation_hints(goal, goal_keywords, all_files)
            hint_files = {s["path"] for s in hints.get("suggested_files", [])} if hints else set()
            if effective_scaffold is not None:
                # Merge: add hint files not already in effective_scaffold
                existing_files = {e.get("file") for e in effective_scaffold if e.get("file")}
                for h in (hints.get("suggested_files", []) if hints else []):
                    if h["path"] not in existing_files and h["path"] not in all_files:
                        effective_scaffold.append({
                            "file": h["path"],
                            "description": f"Creation hint: {h.get('keyword', h['path'])}",
                            "depends_on": h.get("depends_on", []),
                        })
            else:
                # No recipe scaffold: prepend explicit goal paths, then add hints
                # Explicit paths (from backticks/quotes) always take priority over inferred hints
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

        # Apply effective scaffold (user-provided or recipe+hints merged)
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
        if lang_name not in _get_analyzer_registry():
            analysis_meta["warning"] = (
                f"Language '{lang_name}' may not have a native analyzer; results may be approximate"
            )

        result: dict[str, Any] = {
            "goal": goal,
            "steps": steps,
            "dependency_graph": relevant_graph,
            "constraints": [c.get("description", "") for c in active_constraints],
            "constraints_applied": [c.get("description", "") for c in applied],
            "goal_fingerprint": sha256_json(goal)[:16],
            "analysis_meta": analysis_meta,
            "expand_repo": True,
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
            # Explicit goal paths were used (even without user scaffold arg)
            result["goal_paths_inferred"] = len(inferred_entries)
        if hints and not effective_scaffold:
            result["creation_hints"] = hints
        elif hints and effective_scaffold:
            # Surface hint metadata even when merged with recipe scaffold
            result["creation_hints"] = hints

        # Always surface the effective scaffold so callers can persist it for
        # future scaffold_recipe matching (Fix 1)
        if effective_scaffold:
            result["scaffold"] = effective_scaffold

        return result

    def _decompose_scaffold_only(
        self,
        goal: str,
        project_root: str,
        scope: str | None,
        scaffold: list[dict[str, Any]] | None,
        skip_recipes: bool,
        matched_recipe: dict[str, Any] | None,
        active_constraints: list[dict[str, Any]],
        t0: float,
    ) -> dict[str, Any]:
        """Dependency steps derived only from scaffold + goal path inference (no repo-wide scan)."""
        analysis_root = os.path.join(project_root, scope) if scope else project_root
        analyzer = self._get_analyzer(analysis_root)
        lang_name = getattr(analyzer, "name", "unknown")

        scaffold_list = list(scaffold) if scaffold else []
        user_files = {e.get("file") for e in scaffold_list if e.get("file")}
        base_existing = _existing_paths_for_scaffold(analysis_root, scaffold_list)
        inferred_entries = [
            {"file": p, "description": f"Inferred from goal text: {p}"}
            for p in _extract_paths_from_goal(goal)
            if p not in base_existing
        ]
        extra = [e for e in inferred_entries if e["file"] not in user_files]
        effective_scaffold = scaffold_list + extra

        all_files = _existing_paths_for_scaffold(analysis_root, effective_scaffold)

        scaffold_steps, scaffold_graph = _scaffold_steps(
            effective_scaffold, start_index=0, existing_files=all_files,
        )
        steps: list[dict[str, Any]] = list(scaffold_steps)
        relevant_graph: dict[str, list[str]] = {}
        for f, deps in scaffold_graph.items():
            relevant_graph.setdefault(f, []).extend(deps)

        steps, applied = _apply_constraints(steps, active_constraints)

        near_matches: list[dict[str, Any]] = []
        if not skip_recipes:
            ctx_files = {e.get("file") for e in effective_scaffold if e.get("file")}
            near_matches = self.store.retrieve_near_matches(
                goal, n=3, context_files=ctx_files,
            )

        t4 = _time.monotonic()

        analysis_meta: dict[str, Any] = {
            "language": lang_name,
            "scope": scope,
            "files_analyzed": 0,
            "dep_files": len(relevant_graph),
            "dep_edges": sum(len(v) for v in relevant_graph.values()),
            "timing_s": {
                "symbols": 0.0,
                "imports": 0.0,
                "total": round(t4 - t0, 3),
            },
            "scaffold_only": True,
        }
        if lang_name not in _get_analyzer_registry():
            analysis_meta["warning"] = (
                f"Language '{lang_name}' may not have a native analyzer; results may be approximate"
            )

        result: dict[str, Any] = {
            "goal": goal,
            "steps": steps,
            "dependency_graph": relevant_graph,
            "constraints": [c.get("description", "") for c in active_constraints],
            "constraints_applied": [c.get("description", "") for c in applied],
            "goal_fingerprint": sha256_json(goal)[:16],
            "analysis_meta": analysis_meta,
            "expand_repo": False,
        }
        if near_matches:
            result["near_match_recipes"] = near_matches
        if matched_recipe is not None:
            result["recipe"] = matched_recipe.get("_source")
            if matched_recipe.get("_match"):
                result["recipe_match"] = matched_recipe["_match"]
        result["scaffold_applied"] = len([s for s in steps if s.get("action") == "create"])
        if inferred_entries:
            result["goal_paths_inferred"] = len(inferred_entries)
        if effective_scaffold:
            result["scaffold"] = effective_scaffold
        return result

    def explore_trajectories(
        self,
        strategy: dict[str, Any],
        num_beams: int = 3,
    ) -> list[dict[str, Any]]:
        cores = os.cpu_count() or 4
        cap = max(3, min(12, cores))
        n = min(num_beams, cap)
        steps = strategy.get("steps", [])
        dep_graph = strategy.get("dependency_graph", {})

        # Build ordered variants from registry
        entries = list(_STRATEGY_REGISTRY.values())

        # Sort strategies by historical success rate
        stats = self.store.get_strategy_stats()
        def _success_rate(entry: StrategyEntry) -> float:
            pair = stats.get(entry.name)
            if pair is None:
                return -1.0  # no history: keep registration order
            succ, fail = pair
            return succ / (succ + fail + 1)
        entries = sorted(entries, key=_success_rate, reverse=True)

        ordered_variants = [
            (e.name, e.description, e.fn(steps, dep_graph)) for e in entries
        ]
        if not ordered_variants:
            return []

        beams: list[dict[str, Any]] = []
        for i in range(n):
            variant_name, variant_desc, ordered = ordered_variants[i % len(ordered_variants)]
            active, skipped = _split_active_skipped(ordered)
            beam: dict[str, Any] = {
                "beam_id": i,
                "variant": variant_name,
                "variant_description": variant_desc,
                "steps": ordered,
                "edits": [
                    {"step_index": s.get("step_index", j), "path": s.get("file"), "task": s}
                    for j, s in enumerate(active)
                ],
                "skipped": skipped,
            }
            beams.append(beam)

        return beams
