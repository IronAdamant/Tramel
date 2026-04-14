"""Explicit scaffold templates for common architectural patterns.

Replaces heuristic layered-architecture detection with typed, deterministic
 templates that LLMs and users can inspect and extend.
"""

from __future__ import annotations

from typing import Any

# Common architectural patterns expressed as scaffolds.
# Each template defines:
#   - name: identifier
#   - role_keywords: words that must appear in the goal to trigger this template
#   - files: list of scaffold entries with {domain} placeholder
_SCAFFOLD_TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "similarity_engine",
        "role_keywords": {"similarity", "distance", "comparison", "match", "vector"},
        "files": [
            {"file": "src/algorithms/{domain}Algorithms.js", "role": "algorithm"},
            {"file": "src/engines/{domain}Vectorizer.js", "role": "engine", "depends_on": ["src/algorithms/{domain}Algorithms.js"]},
            {"file": "src/services/{domain}Service.js", "role": "service", "depends_on": ["src/engines/{domain}Vectorizer.js"]},
            {"file": "src/routes/{domain}Routes.js", "role": "route", "depends_on": ["src/services/{domain}Service.js"]},
            {"file": "tests/{domain}Algorithms.test.js", "role": "test", "depends_on": ["src/algorithms/{domain}Algorithms.js"]},
            {"file": "tests/{domain}Service.test.js", "role": "test", "depends_on": ["src/services/{domain}Service.js"]},
        ],
    },
    {
        "name": "optimization_engine",
        "role_keywords": {"optimize", "optimizer", "pareto", "frontier", "improve"},
        "files": [
            {"file": "src/algorithms/{domain}Optimizer.js", "role": "algorithm"},
            {"file": "src/services/{domain}Service.js", "role": "service", "depends_on": ["src/algorithms/{domain}Optimizer.js"]},
            {"file": "src/routes/{domain}Routes.js", "role": "route", "depends_on": ["src/services/{domain}Service.js"]},
            {"file": "tests/{domain}Optimizer.test.js", "role": "test", "depends_on": ["src/algorithms/{domain}Optimizer.js"]},
            {"file": "tests/{domain}Service.test.js", "role": "test", "depends_on": ["src/services/{domain}Service.js"]},
        ],
    },
    {
        "name": "metric_dashboard",
        "role_keywords": {"metric", "metrics", "dashboard", "performance", "monitor"},
        "files": [
            {"file": "src/collectors/{domain}Collector.js", "role": "collector"},
            {"file": "src/aggregators/{domain}Aggregator.js", "role": "aggregator", "depends_on": ["src/collectors/{domain}Collector.js"]},
            {"file": "src/routes/{domain}Routes.js", "role": "route", "depends_on": ["src/aggregators/{domain}Aggregator.js"]},
            {"file": "tests/{domain}Collector.test.js", "role": "test", "depends_on": ["src/collectors/{domain}Collector.js"]},
            {"file": "tests/{domain}Aggregator.test.js", "role": "test", "depends_on": ["src/aggregators/{domain}Aggregator.js"]},
        ],
    },
    {
        "name": "plugin_system",
        "role_keywords": {"plugin", "plugins", "dynamic", "registry", "extension"},
        "files": [
            {"file": "src/registry/{domain}Registry.js", "role": "registry"},
            {"file": "src/managers/{domain}PluginManager.js", "role": "manager", "depends_on": ["src/registry/{domain}Registry.js"]},
            {"file": "src/plugins/{domain}Plugin.js", "role": "plugin", "depends_on": ["src/managers/{domain}PluginManager.js"]},
            {"file": "tests/{domain}Registry.test.js", "role": "test", "depends_on": ["src/registry/{domain}Registry.js"]},
        ],
    },
    {
        "name": "openapi_generator",
        "role_keywords": {"openapi", "swagger", "api", "spec", "documentation", "generator"},
        "files": [
            {"file": "src/generators/{domain}Generator.js", "role": "generator"},
            {"file": "tests/{domain}Generator.test.js", "role": "test", "depends_on": ["src/generators/{domain}Generator.js"]},
        ],
    },
    {
        "name": "crud_service",
        "role_keywords": {"service", "services", "route", "routes", "model", "models", "crud", "api"},
        "files": [
            {"file": "src/models/{domain}.js", "role": "model"},
            {"file": "src/services/{domain}Service.js", "role": "service", "depends_on": ["src/models/{domain}.js"]},
            {"file": "src/routes/{domain}Routes.js", "role": "route", "depends_on": ["src/services/{domain}Service.js"]},
            {"file": "tests/{domain}.test.js", "role": "test", "depends_on": ["src/routes/{domain}Routes.js"]},
        ],
    },
]


def _detect_role_keywords(goal_keywords: set[str], role_keywords: set[str]) -> bool:
    """True if any goal keyword matches a role keyword (including simple variants)."""
    variants: set[str] = set()
    for kw in goal_keywords:
        variants.add(kw)
        variants.add(kw + "s")
        if kw.endswith("s"):
            variants.add(kw[:-1])
    return bool(variants & role_keywords)


def _extract_domain_keyword(
    goal_keywords: set[str], reserved: set[str] = frozenset(),
) -> str | None:
    """Pick the longest meaningful keyword as the domain name."""
    for kw in sorted(goal_keywords, key=len, reverse=True):
        if len(kw) > 3 and kw not in reserved:
            return kw
    return None


def _resolve_template_directories(
    files: list[dict[str, Any]],
    dirs: dict[str, list[str]],
    existing_files: set[str],
) -> list[dict[str, Any]]:
    """Map template file paths onto existing directories where possible.

    Falls back to the path as-written if no directory mapping is found.
    """
    out: list[dict[str, Any]] = []
    dir_keys = set(dirs.keys())

    for entry in files:
        path = entry["file"]
        role = entry.get("role", "")
        role_dir = None

        # Try to find an existing directory matching the role
        for d in sorted(dir_keys):
            dl = d.lower().replace("\\", "/")
            if role in dl or (role.rstrip("s") in dl and role != "test"):
                if "test" not in dl.split("/") or role == "test":
                    role_dir = d
                    break

        if role_dir is None:
            # Fallback heuristics for well-known structures
            if role == "test":
                role_dir = "tests"
            elif role == "model":
                role_dir = "src/models"
            elif role == "service":
                role_dir = "src/services"
            elif role == "route":
                role_dir = "src/routes"
            elif role == "algorithm":
                role_dir = "src/algorithms"
            elif role == "engine":
                role_dir = "src/engines"
            elif role == "collector":
                role_dir = "src/collectors"
            elif role == "aggregator":
                role_dir = "src/aggregators"
            elif role == "registry":
                role_dir = "src/registry"
            elif role == "manager":
                role_dir = "src/managers"
            elif role == "plugin":
                role_dir = "src/plugins"
            elif role == "generator":
                role_dir = "src/generators"
            else:
                role_dir = "src"

        # Replace directory prefix in path
        parts = path.split("/")
        if len(parts) > 1:
            new_path = "/".join([role_dir] + parts[1:])
        else:
            new_path = path

        new_entry = dict(entry, file=new_path)
        if "depends_on" in entry:
            new_deps = []
            for dep in entry["depends_on"]:
                dep_parts = dep.split("/")
                if len(dep_parts) > 1:
                    # Use same role_dir mapping for dependencies
                    dep_role = None
                    for d in sorted(dir_keys):
                        dl = d.lower().replace("\\", "/")
                        for role_candidate in ("model", "service", "route", "algorithm", "engine", "collector", "aggregator", "registry", "manager", "plugin", "generator"):
                            if role_candidate in dl:
                                if dep_parts[0].endswith("s") and dep_parts[0].startswith("src/"):
                                    prefix = dep_parts[0]
                                    break
                    # Simple substitution: replace the src/ROLE prefix with our mapped role_dir
                    dep_role_dir = None
                    for rc in ("models", "services", "routes", "algorithms", "engines", "collectors", "aggregators", "registry", "managers", "plugins", "generators", "tests"):
                        if dep.startswith(f"src/{rc}/"):
                            mapped = rc
                            if mapped == "models":
                                mapped = "src/models"
                            elif mapped == "services":
                                mapped = "src/services"
                            elif mapped == "routes":
                                mapped = "src/routes"
                            elif mapped == "algorithms":
                                mapped = "src/algorithms"
                            elif mapped == "engines":
                                mapped = "src/engines"
                            elif mapped == "collectors":
                                mapped = "src/collectors"
                            elif mapped == "aggregators":
                                mapped = "src/aggregators"
                            elif mapped == "registry":
                                mapped = "src/registry"
                            elif mapped == "managers":
                                mapped = "src/managers"
                            elif mapped == "plugins":
                                mapped = "src/plugins"
                            elif mapped == "generators":
                                mapped = "src/generators"
                            elif mapped == "tests":
                                mapped = "tests"
                            dep_role_dir = mapped
                            break
                    if dep_role_dir:
                        new_dep = "/".join([dep_role_dir] + dep_parts[2:])
                    else:
                        new_dep = dep
                    new_deps.append(new_dep)
                else:
                    new_deps.append(dep)
            new_entry["depends_on"] = new_deps

        out.append(new_entry)

    return out


def match_scaffold_template(
    goal: str,
    goal_keywords: set[str],
    existing_files: set[str],
    dirs: dict[str, list[str]],
) -> list[dict[str, Any]] | None:
    """Match goal against registered scaffold templates and return populated entries."""
    reserved = {
        "service", "services", "route", "routes", "plugin", "plugins",
        "model", "models", "test", "tests", "add", "new", "create",
        "file", "files", "module", "modules",
    }
    domain_kw = _extract_domain_keyword(goal_keywords, reserved)
    if not domain_kw:
        return None

    for template in _SCAFFOLD_TEMPLATES:
        if _detect_role_keywords(goal_keywords, template["role_keywords"]):
            files = [
                dict(e, file=e["file"].format(domain=domain_kw.capitalize()))
                for e in template["files"]
            ]
            # Fix dependency paths with domain placeholder
            for e in files:
                if "depends_on" in e:
                    e["depends_on"] = [d.format(domain=domain_kw.capitalize()) for d in e["depends_on"]]

            files = _resolve_template_directories(files, dirs, existing_files)

            # Skip files that already exist; preserve depends_on chain continuity
            existing_set = existing_files
            scaffold: list[dict[str, Any]] = []
            prev_file: str | None = None
            for entry in files:
                path = entry["file"]
                if path in existing_set:
                    prev_file = path
                    continue
                new_entry: dict[str, Any] = {
                    "file": path,
                    "description": f"{entry.get('role', 'file')}: {path.split('/')[-1]}",
                }
                if prev_file and prev_file not in (entry.get("depends_on") or []):
                    raw_deps = list(entry.get("depends_on", []))
                    if raw_deps:
                        # Ensure previous non-skipped file is in chain
                        if prev_file not in raw_deps:
                            raw_deps.append(prev_file)
                    else:
                        raw_deps = [prev_file]
                    new_entry["depends_on"] = raw_deps
                elif entry.get("depends_on"):
                    new_entry["depends_on"] = list(entry["depends_on"])
                scaffold.append(new_entry)
                prev_file = path

            return scaffold if scaffold else None

    return None
