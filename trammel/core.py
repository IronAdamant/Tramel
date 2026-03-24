"""Dependency-aware decomposition and bounded beam exploration with real strategy branching."""

from __future__ import annotations

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
    """Check if the goal implies creating new files/modules."""
    return bool(set(goal.lower().split()) & _CREATION_VERBS)


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
    """Return which goal keywords match any candidate word (with plural/singular)."""
    matched: set[str] = set()
    for kw in goal_keywords:
        if {kw, kw + "s", kw.rstrip("s")} & candidate_words:
            matched.add(kw)
    return matched


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

    # Find directories relevant to goal keywords
    kw_variants = _keyword_variants(goal_keywords)
    relevant_dirs: list[str] = []
    for d in sorted(dirs.keys()):
        dir_words = set(re.findall(r'[a-z]+', d.lower()))
        if dir_words & kw_variants:
            relevant_dirs.append(d)

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
    suggested = suggested[:5]

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

    steps: list[dict[str, Any]] = []
    for s in suggested:
        path = s["path"]
        kw = s["keyword"]
        inferred = s.get("inferred_from", [])
        rationale = (
            f"Inferred from goal keyword '{kw}' + directory pattern "
            f"(siblings: {', '.join(inferred)})"
            if inferred
            else f"Inferred from goal keyword '{kw}'"
        )
        steps.append({
            "step_index": start_index + len(steps),
            "file": path,
            "action": "create",
            "symbols": [],
            "symbol_count": 0,
            "description": f"Create {path}",
            "rationale": rationale,
            "depends_on": [],
            "relevance": 1.0,
        })
    return steps


def _score_relevance(
    filepath: str, sym_names: list[str], goal_keywords: set[str],
) -> float:
    """Score how relevant a file is to the goal (0.0 to 1.0)."""
    if not goal_keywords:
        return 1.0
    path_words = set(re.findall(r'[a-z]+', filepath.lower()))
    sym_words: set[str] = set()
    for s in sym_names:
        sym_words.update(
            p.lower() for p in re.findall(r'[a-z]+|[A-Z][a-z]*', s) if len(p) > 2
        )
    return len(_matched_keywords(goal_keywords, path_words | sym_words)) / len(goal_keywords)


# ── Step generation ──────────────────────────────────────────────────────────

def _generate_steps(
    file_order: list[str],
    symbols: dict[str, list[str]],
    dep_graph: dict[str, list[str]],
    goal: str,
    *,
    goal_keywords: set[str] | None = None,
    relevant_only: bool = False,
) -> list[dict[str, Any]]:
    """Generate plan steps from ordered files, their symbols, and dependency info."""
    steps: list[dict[str, Any]] = []
    file_to_step: dict[str, int] = {}

    for filepath in file_order:
        sym_names = symbols.get(filepath, [])
        if not sym_names:
            continue

        relevance = _score_relevance(filepath, sym_names, goal_keywords) if goal_keywords else None
        if relevant_only and relevance is not None and relevance == 0.0:
            continue

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
    ) -> dict[str, Any]:
        t0 = _time.monotonic()

        # Fast path: exact text match without project scan
        recipe = self.store.retrieve_best_recipe(goal)
        if recipe:
            recipe.setdefault("_source", "recipe_exact")
            return recipe

        active_constraints = self.store.get_active_constraints()
        goal_keywords = _extract_goal_keywords(goal)

        analysis_root = os.path.join(project_root, scope) if scope else project_root
        analyzer = self._get_analyzer(analysis_root)

        t1 = _time.monotonic()
        symbols = analyzer.collect_symbols(analysis_root)
        t2 = _time.monotonic()
        dep_graph = analyzer.analyze_imports(analysis_root)
        t3 = _time.monotonic()

        # Structural recipe match: try again with file context
        all_files = set(symbols) | set(dep_graph)
        recipe = self.store.retrieve_best_recipe(goal, context_files=all_files)
        if recipe:
            recipe.setdefault("_source", "recipe_structural")
            return recipe

        # Collect near-miss recipes for reference
        near_matches = self.store.retrieve_near_matches(goal, n=3)

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
        )
        steps, applied = _apply_constraints(steps, active_constraints)

        # Creation hints + concrete "Create" steps for new-file goals
        hints = _creation_hints(goal, goal_keywords, all_files)
        creation_steps = _generate_creation_steps(hints, start_index=len(steps))
        if creation_steps:
            steps.extend(creation_steps)

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
        }
        if near_matches:
            result["near_match_recipes"] = near_matches
        if hints:
            result["creation_hints"] = hints

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
