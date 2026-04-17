"""Plan, step, and compound-operation mixin for RecipeStore.

Split out of :mod:`store` to keep that module under the project's 500-LOC
target. Hosts plan CRUD, plan merging, step updates, resume/progress
queries, and the ``complete_plan`` compound operation.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import TYPE_CHECKING, Any

from .utils import dumps_json, transaction

if TYPE_CHECKING:
    from .store import RecipeStore  # noqa: F401 — documents mixin host


_STEP_COLUMNS = (
    "id, plan_id, step_index, description, rationale, depends_on, "
    "status, edits_json, verification, constraints_found, claimed_by, claimed_at, created"
)


def _step_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a step row to a dictionary with parsed JSON fields."""
    return {
        "id": row["id"], "plan_id": row["plan_id"],
        "step_index": row["step_index"],
        "description": row["description"], "rationale": row["rationale"],
        "depends_on": json.loads(row["depends_on"]),
        "status": row["status"], "edits": json.loads(row["edits_json"]),
        "verification": json.loads(row["verification"]) if row["verification"] else None,
        "constraints_found": json.loads(row["constraints_found"]),
        "claimed_by": row["claimed_by"], "claimed_at": row["claimed_at"],
        "created": row["created"],
    }


class PlanStoreMixin:
    """Plan + step CRUD, resumption, merging, and plan completion."""

    conn: sqlite3.Connection

    # ── Plans ────────────────────────────────────────────────────────────────

    @staticmethod
    def _validate_plan_steps(steps: list[dict[str, Any]]) -> None:
        """Validate step dependencies for cycles before plan creation.

        Raises ValueError if the step dependency graph contains a cycle.
        """
        # Build graph: step_index -> list of dependency step indices
        graph: dict[int, list[int]] = {}
        for i, step in enumerate(steps):
            idx = step.get("step_index", i)
            deps = step.get("depends_on", [])
            graph[idx] = [d for d in deps if isinstance(d, int)]

        # DFS cycle detection
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {idx: WHITE for idx in graph}

        def dfs(node: int, path: list[int]) -> list[int] | None:
            color[node] = GRAY
            for dep in graph.get(node, []):
                if dep not in color:
                    continue
                if color.get(dep, WHITE) == GRAY:
                    cycle_start = path.index(dep)
                    return path[cycle_start:] + [dep]
                if color.get(dep, WHITE) == WHITE:
                    cycle = dfs(dep, path + [dep])
                    if cycle:
                        return cycle
            color[node] = BLACK
            return None

        for idx in graph:
            if color[idx] == WHITE:
                cycle = dfs(idx, [idx])
                if cycle:
                    cycle_str = " → ".join(str(x) for x in cycle)
                    raise ValueError(f"circular_dependency detected in plan steps: {cycle_str}")

    def merge_plans(
        self,
        plan_a_id: int,
        plan_b_id: int,
        strategy: str = "sequential",
    ) -> dict[str, Any]:
        """Merge two plans into a unified strategy with conflict detection."""
        from .plan_merge import merge_plans as _merge_plans_impl

        plan_a = self.get_plan(plan_a_id)
        plan_b = self.get_plan(plan_b_id)
        if plan_a is None:
            return {"error": "plan_a not found"}
        if plan_b is None:
            return {"error": "plan_b not found"}

        result = _merge_plans_impl(plan_a.get("steps", []), plan_b.get("steps", []), strategy=strategy)
        merged_strategy = {
            "steps": result["merged_steps"],
            "dependency_graph": {},
        }
        scaffold = list(plan_a.get("scaffold", [])) + list(plan_b.get("scaffold", []))
        new_plan_id = self.create_plan(
            f"Merged plan {plan_a_id} + {plan_b_id}",
            merged_strategy,
            scaffold=scaffold,
        )
        result["plan_id"] = new_plan_id
        return result

    def create_plan(self, goal: str, strategy: dict[str, Any], scaffold: list[dict[str, Any]] | None = None) -> int:
        now = time.time()
        plan_steps = strategy.get("steps", [])
        self._validate_plan_steps(plan_steps)
        scaffold_json = dumps_json(scaffold or [])
        with transaction(self.conn):
            cur = self.conn.execute(
                "INSERT INTO plans (goal, strategy, scaffold, status, current_step, total_steps, created, updated) "
                "VALUES (?, ?, ?, 'pending', 0, ?, ?, ?)",
                (goal, dumps_json(strategy), scaffold_json, len(plan_steps), now, now),
            )
            plan_id = int(cur.lastrowid)
            for i, step in enumerate(plan_steps):
                self.conn.execute(
                    "INSERT INTO steps (plan_id, step_index, description, rationale, depends_on, status, created) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (plan_id, i, step.get("description", ""), step.get("rationale", ""),
                     dumps_json(step.get("depends_on", [])), "pending", now),
                )
        return plan_id

    def get_plan(self, plan_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT id, goal, strategy, scaffold, status, current_step, total_steps, created, updated "
            "FROM plans WHERE id = ?",
            (plan_id,),
        ).fetchone()
        if not row:
            return None
        steps = self.conn.execute(
            f"SELECT {_STEP_COLUMNS} FROM steps WHERE plan_id = ? ORDER BY step_index",
            (plan_id,),
        ).fetchall()
        return {
            "id": row["id"], "goal": row["goal"],
            "strategy": json.loads(row["strategy"]),
            "scaffold": json.loads(row["scaffold"]) if row["scaffold"] else [],
            "status": row["status"], "current_step": row["current_step"],
            "total_steps": row["total_steps"],
            "created": row["created"], "updated": row["updated"],
            "steps": [_step_to_dict(s) for s in steps],
        }

    def update_plan_status(self, plan_id: int, status: str) -> None:
        with transaction(self.conn):
            self.conn.execute(
                "UPDATE plans SET status = ?, updated = ? WHERE id = ?",
                (status, time.time(), plan_id),
            )
        if status == "completed":
            plan = self.get_plan(plan_id)
            if plan is not None:
                outcome = True
                self.save_recipe(plan["goal"], plan["strategy"], outcome)
                scaffold = plan.get("scaffold", [])
                if scaffold:
                    self.save_scaffold_recipe(plan["goal"], scaffold, outcome)

    def list_plans(self, status: str | None = None) -> list[dict[str, Any]]:
        query = ("SELECT id, goal, status, current_step, total_steps, created, updated "
                 "FROM plans")
        params: tuple[str, ...] = ()
        if status is not None:
            query += " WHERE status = ?"
            params = (status,)
        rows = self.conn.execute(query + " ORDER BY id DESC", params).fetchall()
        return [
            {
                "id": r["id"], "goal": r["goal"], "status": r["status"],
                "current_step": r["current_step"], "total_steps": r["total_steps"],
                "created": r["created"], "updated": r["updated"],
            }
            for r in rows
        ]

    # ── Steps ────────────────────────────────────────────────────────────────

    def update_step(
        self,
        step_id: int,
        status: str,
        edits: list[dict[str, Any]] | None = None,
        verification: dict[str, Any] | None = None,
        constraints_found: list[dict[str, Any]] | None = None,
    ) -> None:
        updates = ["status = ?"]
        params: list[Any] = [status]
        if edits is not None:
            updates.append("edits_json = ?")
            params.append(dumps_json(edits))
        if verification is not None:
            updates.append("verification = ?")
            params.append(dumps_json(verification))
        if constraints_found is not None:
            updates.append("constraints_found = ?")
            params.append(dumps_json(constraints_found))
        params.append(step_id)
        with transaction(self.conn):
            self.conn.execute(
                f"UPDATE steps SET {', '.join(updates)} WHERE id = ?", tuple(params)
            )
        # Auto-record failure patterns when step fails with verification data
        if status == "failed" and verification:
            fa = verification.get("failure_analysis", {})
            if fa.get("file") and fa.get("error_type"):
                self.record_failure_pattern(
                    fa["file"], fa["error_type"], fa.get("message", ""),
                )

    def update_steps_batch(
        self,
        updates: list[dict[str, Any]],
    ) -> int:
        """Batch-update multiple steps in a single transaction.

        Each entry should have: step_id, status.  Optionally: edits, verification.
        Designed for P6 single-agent workflows where per-step record_step is overhead.

        Returns count of steps updated.
        """
        if not updates:
            return 0
        count = 0
        failure_patterns: list[tuple[str, str, str]] = []
        with transaction(self.conn):
            for entry in updates:
                step_id = entry["step_id"]
                status = entry["status"]
                cols = ["status = ?"]
                params: list[Any] = [status]
                if entry.get("edits") is not None:
                    cols.append("edits_json = ?")
                    params.append(dumps_json(entry["edits"]))
                if entry.get("verification") is not None:
                    cols.append("verification = ?")
                    params.append(dumps_json(entry["verification"]))
                params.append(step_id)
                self.conn.execute(
                    f"UPDATE steps SET {', '.join(cols)} WHERE id = ?", tuple(params),
                )
                count += 1
                if status == "failed" and entry.get("verification"):
                    fa = entry["verification"].get("failure_analysis", {})
                    if fa.get("file") and fa.get("error_type"):
                        failure_patterns.append(
                            (fa["file"], fa["error_type"], fa.get("message", "")),
                        )
        for file_path, error_type, message in failure_patterns:
            self.record_failure_pattern(file_path, error_type, message)
        return count

    def get_step(self, step_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            f"SELECT {_STEP_COLUMNS} FROM steps WHERE id = ?",
            (step_id,),
        ).fetchone()
        return _step_to_dict(row) if row else None

    def get_plan_progress(self, plan_id: int) -> dict[str, Any] | None:
        """Get plan state with accumulated edits from passed steps for resumption."""
        plan = self.get_plan(plan_id)
        if plan is None:
            return None
        prior_edits: list[dict[str, Any]] = []
        next_step_index = 0
        for step in plan["steps"]:
            if step["status"] == "passed":
                prior_edits.extend(step.get("edits") or [])
                next_step_index = step["step_index"] + 1
            else:
                break
        remaining = [s for s in plan["steps"] if s["step_index"] >= next_step_index]
        return {
            **plan,
            "prior_edits": prior_edits,
            "next_step_index": next_step_index,
            "remaining_steps": remaining,
            "completed_count": next_step_index,
        }

    # ── Compound operations ────────────────────────────────────────────────

    def complete_plan(
        self,
        plan_id: int,
        outcome: bool,
        step_status: str = "passed",
    ) -> dict[str, Any]:
        """Finalize a plan in one call: batch-update pending steps, set plan
        status, and save the strategy as a recipe.

        Designed for single-agent workflows where per-step claim/record/verify
        overhead is disproportionate.

        Args:
            plan_id: Plan to complete.
            outcome: True if the work succeeded (saves recipe as success).
            step_status: Status to assign to all still-pending steps
                         ("passed" or "skipped").  Already-recorded steps
                         are left untouched.

        Returns:
            Summary dict with counts and the recipe sig.
        """
        plan = self.get_plan(plan_id)
        if plan is None:
            return {"error": "plan not found"}

        now = time.time()
        steps_updated = 0
        with transaction(self.conn):
            for step in plan["steps"]:
                if step["status"] == "pending":
                    self.conn.execute(
                        "UPDATE steps SET status = ? WHERE id = ?",
                        (step_status, step["id"]),
                    )
                    steps_updated += 1

            plan_status = "completed" if outcome else "failed"
            self.conn.execute(
                "UPDATE plans SET status = ?, updated = ? WHERE id = ?",
                (plan_status, now, plan_id),
            )

        strategy = plan["strategy"]
        self.save_recipe(plan["goal"], strategy, outcome)

        # Fix 1: save scaffold recipe when plan succeeded with an explicit scaffold
        scaffold = plan.get("scaffold", [])
        if outcome and scaffold:
            self.save_scaffold_recipe(plan["goal"], scaffold, outcome)

        # Auto-persist trajectory data so strategy recommendations become data-driven
        strategy_variant = (
            strategy.get("variant", "complete_plan")
            if isinstance(strategy, dict) else "complete_plan"
        )
        total_steps = len(plan.get("steps", []))
        self.log_trajectory(
            plan_id=plan_id,
            beam_id=0,
            strategy_variant=strategy_variant,
            steps_completed=total_steps,
            outcome={"success": outcome, "steps_completed": total_steps, "source": "complete_plan"},
            failure_reason=None if outcome else "plan_completed_with_failure",
        )

        return {
            "plan_id": plan_id,
            "plan_status": plan_status,
            "steps_updated": steps_updated,
            "recipe_saved": outcome,
            "scaffold_saved": bool(outcome and scaffold),
        }
