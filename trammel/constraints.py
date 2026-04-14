"""Constraint parsing and enforcement for plan steps."""

from __future__ import annotations

from typing import Any


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
