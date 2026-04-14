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

_ROLE_DIR_SUBSTRINGS = (
    "service", "route", "controller", "model", "test", "schema", "api",
    "handler", "view", "repository", "repo",
)

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

    sep, split_re = "", r'[a-z]+|[A-Z][a-z]*'
    if sum("_" in b for b in bases) > len(bases) // 2:
        sep, split_re = "_", r'[^_]+'
    elif sum("-" in b for b in bases) > len(bases) // 2:
        sep, split_re = "-", r'[^-]+'

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

    if sum(b[:1].isupper() for b in bases) > len(bases) // 2:
        return keyword.capitalize() + ext
    return keyword.lower() + ext


def _fallback_directories(
    goal_keywords: set[str],
    dirs: dict[str, list[str]],
    existing_files: set[str],
) -> list[dict[str, Any]]:
    """Suggest files in fallback role directories when keyword matching finds nothing."""
    suggestions: list[dict[str, Any]] = []
    blob = " ".join(goal_keywords).lower()

    all_extensions = [os.path.splitext(f)[1] for f in existing_files if os.path.splitext(f)[1]]
    default_ext = max(set(all_extensions), key=all_extensions.count) if all_extensions else ".js"

    matching_roles: list[str] = []
    for role in _FALLBACK_ROLE_DIRS:
        role_name = role.split("/")[-1]
        singular = role_name.rstrip("s")
        if role_name in blob or singular in blob:
            matching_roles.append(role)

    if not matching_roles:
        matching_roles = list(_FALLBACK_ROLE_DIRS)

    skip_kw = frozenset({"src", "lib", "app", "index", "main", "test", "the", "add", "new", "file", "files", "module"})

    for role_dir in matching_roles[:5]:
        role_name = role_dir.split("/")[-1]
        singular = role_name.rstrip("s")

        existing_in_dir = dirs.get(role_dir, [])
        siblings = sorted(existing_in_dir)

        relevant_kw = [kw for kw in goal_keywords if kw not in skip_kw]

        for kw in relevant_kw[:3]:
            name = _infer_file_name(kw, siblings)
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


def _detect_layered_architecture(
    goal: str,
    goal_keywords: set[str],
    existing_files: set[str],
    dirs: dict[str, list[str]],
) -> list[dict[str, Any]] | None:
    """Detect if goal implies a layered architecture pattern and generate scaffold."""
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

    domain_kw = None
    for kw in sorted(goal_keywords, key=len, reverse=True):
        if kw in goal_keywords and len(kw) > 3 and kw not in {"service", "services", "route", "routes", "plugin", "plugins"}:
            domain_kw = kw
            break

    if not domain_kw:
        return None

    role_label = matched_pattern["role"]
    role_dir: str | None = None
    for d in sorted(dirs.keys()):
        dl = d.lower()
        if role_label in dl or any(seg in dl for seg in ("src/api", "src/services", "src/utils")):
            if "test" not in dl:
                role_dir = d
                break

    if not role_dir:
        for d in sorted(dirs.keys()):
            if "test" not in d.split("/"):
                role_dir = d
                break

    if not role_dir:
        return None

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


def _creation_hints(
    goal: str,
    goal_keywords: set[str],
    existing_files: set[str],
) -> dict[str, Any] | None:
    """When goal indicates creation intent, return context + suggested new files."""
    if not _has_creation_intent(goal):
        return None

    dirs: dict[str, list[str]] = {}
    for f in existing_files:
        parent = os.path.dirname(f)
        if parent:
            dirs.setdefault(parent, []).append(os.path.basename(f))

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

    kw_variants = _keyword_variants(goal_keywords)
    relevant_dirs: list[str] = []
    for d in sorted(dirs.keys()):
        dir_words = set(re.findall(r'[a-z]+', d.lower()))
        if dir_words & kw_variants:
            relevant_dirs.append(d)

    if not relevant_dirs:
        relevant_dirs = _directories_for_role_hints(goal_keywords, dirs)

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

    goal_entities = hints.get("goal_entities", [])
    entity_summary = ", ".join(goal_entities[:4])

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
            desc = f"Create {path} — implement {kw} module"
            if entity_summary and kw not in entity_summary:
                desc += f" (related: {entity_summary})"

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
