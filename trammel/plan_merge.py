"""Plan merging: detect conflicts and merge two plans into a unified strategy."""

from __future__ import annotations

from typing import Any

from .utils import topological_sort


def _build_step_graph(steps: list[dict[str, Any]]) -> dict[int, list[int]]:
    """Build dependency graph from step indices."""
    graph: dict[int, list[int]] = {}
    for s in steps:
        idx = s.get("step_index", 0)
        deps = s.get("depends_on", [])
        graph[idx] = [d for d in deps if isinstance(d, int)]
    return graph


def _detect_cycles(graph: dict[int, list[int]]) -> list[int] | None:
    """Return a cycle if one exists, else None."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in graph}

    def dfs(node: int, path: list[int]) -> list[int] | None:
        color[node] = GRAY
        for dep in graph.get(node, []):
            if dep not in color:
                continue
            if color.get(dep, WHITE) == GRAY:
                start = path.index(dep)
                return path[start:] + [dep]
            if color.get(dep, WHITE) == WHITE:
                cycle = dfs(dep, path + [dep])
                if cycle:
                    return cycle
        color[node] = BLACK
        return None

    for n in graph:
        if color[n] == WHITE:
            cycle = dfs(n, [n])
            if cycle:
                return cycle
    return None


def detect_plan_conflicts(
    plan_a_steps: list[dict[str, Any]],
    plan_b_steps: list[dict[str, Any]],
) -> dict[str, Any]:
    """Detect conflicts between two plans.

    Returns:
        {
            "conflicts": [...],
            "severity": "none" | "low" | "medium" | "high" | "critical",
        }
    """
    conflicts: list[dict[str, Any]] = []
    severity_score = 0

    a_files: dict[str, list[dict[str, Any]]] = {}
    for s in plan_a_steps:
        f = s.get("file")
        if f:
            a_files.setdefault(f, []).append(s)

    b_files: dict[str, list[dict[str, Any]]] = {}
    for s in plan_b_steps:
        f = s.get("file")
        if f:
            b_files.setdefault(f, []).append(s)

    # File overlap
    overlap = set(a_files) & set(b_files)
    for f in overlap:
        a_actions = {s.get("action", "modify") for s in a_files[f]}
        b_actions = {s.get("action", "modify") for s in b_files[f]}
        clashes = False
        if ("create" in a_actions and "update" in b_actions) or ("update" in a_actions and "create" in b_actions):
            clashes = True
        if ("delete" in a_actions) or ("delete" in b_actions):
            clashes = True
        conflicts.append({
            "type": "file_overlap",
            "file": f,
            "plan_a_actions": sorted(a_actions),
            "plan_b_actions": sorted(b_actions),
            "clash": clashes,
        })
        severity_score += 3 if clashes else 1

    # Dependency inversion: Plan A depends on file deleted by Plan B
    a_deps = {d for s in plan_a_steps for d in (s.get("depends_on") or []) if isinstance(d, int)}
    b_deletes = {s.get("step_index") for s in plan_b_steps if s.get("action") == "delete"}
    for idx in a_deps & b_deletes:
        conflicts.append({
            "type": "dependency_inversion",
            "step_index": idx,
            "message": f"Plan A depends on step {idx} which Plan B deletes",
        })
        severity_score += 2

    # Action clash: Plan B deletes file Plan A creates
    a_creates = {s.get("file") for s in plan_a_steps if s.get("action") == "create"}
    b_deletes_files = {s.get("file") for s in plan_b_steps if s.get("action") == "delete"}
    for f in a_creates & b_deletes_files:
        conflicts.append({
            "type": "action_clash",
            "file": f,
            "message": f"Plan A creates {f} but Plan B deletes it",
        })
        severity_score += 4

    if severity_score >= 8:
        severity = "critical"
    elif severity_score >= 5:
        severity = "high"
    elif severity_score >= 3:
        severity = "medium"
    elif severity_score > 0:
        severity = "low"
    else:
        severity = "none"

    return {"conflicts": conflicts, "severity": severity}


def merge_plans(
    plan_a_steps: list[dict[str, Any]],
    plan_b_steps: list[dict[str, Any]],
    strategy: str = "sequential",
) -> dict[str, Any]:
    """Merge two plans using the given strategy.

    Strategies:
        sequential: all of A, then all of B (renumbered).
        interleave: topological merge respecting both DAGs.
        priority: A wins on overlaps; conflicting B steps skipped.
        unified: if two steps target the same file with same action, merge them.
    """
    conflict_report = detect_plan_conflicts(plan_a_steps, plan_b_steps)

    if strategy == "sequential":
        merged = _merge_sequential(plan_a_steps, plan_b_steps)
    elif strategy == "interleave":
        merged = _merge_interleave(plan_a_steps, plan_b_steps)
    elif strategy == "priority":
        merged = _merge_priority(plan_a_steps, plan_b_steps)
    elif strategy == "unified":
        merged = _merge_unified(plan_a_steps, plan_b_steps)
    else:
        raise ValueError(f"Unknown merge strategy: {strategy}")

    # Validate merged DAG
    graph = _build_step_graph(merged)
    cycle = _detect_cycles(graph)
    cycle_introduced = cycle is not None

    return {
        "merged_steps": merged,
        "conflicts": conflict_report["conflicts"],
        "severity": conflict_report["severity"],
        "cycle_introduced": cycle_introduced,
        "cycle": cycle,
        "strategy": strategy,
    }


def _renumber_steps(steps: list[dict[str, Any]], offset: int) -> list[dict[str, Any]]:
    """Return copies of steps with step_index shifted by offset."""
    old_to_new: dict[int, int] = {}
    for s in steps:
        old = s.get("step_index", 0)
        old_to_new[old] = offset + len(old_to_new)

    result: list[dict[str, Any]] = []
    for s in steps:
        old = s.get("step_index", 0)
        new_idx = old_to_new[old]
        new_deps = [old_to_new[d] for d in (s.get("depends_on") or []) if isinstance(d, int) and d in old_to_new]
        result.append({**s, "step_index": new_idx, "depends_on": new_deps})
    return result


def _merge_sequential(
    plan_a_steps: list[dict[str, Any]],
    plan_b_steps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    a = _renumber_steps(plan_a_steps, 0)
    offset = len(a)
    b = _renumber_steps(plan_b_steps, offset)
    # B steps that had deps on A steps (by file matching) should also depend on the A step
    # For simplicity, sequential just adds a global ordering: all B depend on all last A steps
    # with no outgoing edges
    last_a = {s["step_index"] for s in a}
    for s in a:
        for d in s.get("depends_on", []):
            last_a.discard(d)
    for s in b:
        deps = set(s.get("depends_on", []))
        deps.update(last_a)
        s["depends_on"] = sorted(deps)
    return a + b


def _merge_interleave(
    plan_a_steps: list[dict[str, Any]],
    plan_b_steps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    a = _renumber_steps(plan_a_steps, 0)
    offset = len(a)
    b = _renumber_steps(plan_b_steps, offset)

    # Build combined graph
    all_steps = a + b
    graph: dict[str, list[str]] = {}
    idx_to_step: dict[str, dict[str, Any]] = {}
    for s in all_steps:
        sid = f"s{s['step_index']}"
        idx_to_step[sid] = s
        graph[sid] = [f"s{d}" for d in (s.get("depends_on") or []) if isinstance(d, int)]

    # Add file-based cross-dependencies: if B creates a file that A depends on,
    # or vice versa, respect that ordering
    file_to_step: dict[str, str] = {}
    for sid, s in idx_to_step.items():
        f = s.get("file")
        if f and s.get("action") == "create":
            file_to_step[f] = sid

    for sid, s in idx_to_step.items():
        f = s.get("file")
        if f and f in file_to_step and file_to_step[f] != sid:
            creator = file_to_step[f]
            if creator not in graph.get(sid, []):
                graph.setdefault(sid, []).append(creator)

    order = topological_sort(graph)
    ordered_steps = [idx_to_step[sid] for sid in order if sid in idx_to_step]

    # Reassign step_index to match order
    old_to_new: dict[int, int] = {}
    for i, s in enumerate(ordered_steps):
        old_to_new[s["step_index"]] = i
    for s in ordered_steps:
        s["step_index"] = old_to_new[s["step_index"]]
        s["depends_on"] = [old_to_new[d] for d in (s.get("depends_on") or []) if isinstance(d, int) and d in old_to_new]

    return ordered_steps


def _merge_priority(
    plan_a_steps: list[dict[str, Any]],
    plan_b_steps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    a_files = {s.get("file") for s in plan_a_steps if s.get("file")}
    b_filtered = [s for s in plan_b_steps if s.get("file") not in a_files]
    return _merge_sequential(plan_a_steps, b_filtered)


def _merge_unified(
    plan_a_steps: list[dict[str, Any]],
    plan_b_steps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    # Index A steps by file+action
    a_index: dict[tuple[str, str], dict[str, Any]] = {}
    for s in plan_a_steps:
        f = s.get("file")
        action = s.get("action", "modify")
        if f:
            a_index[(f, action)] = s

    unified_a = list(plan_a_steps)
    extra_b: list[dict[str, Any]] = []
    for s in plan_b_steps:
        f = s.get("file")
        action = s.get("action", "modify")
        key = (f, action) if f else None
        if key and key in a_index:
            # Merge depends_on
            a_step = a_index[key]
            merged_deps = set(a_step.get("depends_on", [])) | set(d for d in (s.get("depends_on") or []) if isinstance(d, int))
            a_step["depends_on"] = sorted(merged_deps)
        else:
            extra_b.append(s)

    return _merge_sequential(unified_a, extra_b)
