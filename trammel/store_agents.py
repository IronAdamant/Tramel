"""Multi-agent coordination mixin: step claiming, availability, release."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from .utils import transaction

if TYPE_CHECKING:
    import sqlite3


class AgentStoreMixin:
    """Multi-agent step coordination mixed into RecipeStore.

    Expects the composing class to provide:
        conn: sqlite3.Connection
        get_plan(plan_id) -> dict | None
    """

    conn: sqlite3.Connection

    def get_plan(self, plan_id: int) -> dict[str, Any] | None:
        """Provided by composing class."""
        raise NotImplementedError

    _CLAIM_TIMEOUT = 600  # 10 minutes — stale claims auto-expire

    def _is_claimed_by_other(
        self, claimed_by: str | None, claimed_at: float | None, agent_id: str, now: float,
    ) -> bool:
        """Check if a step is actively claimed by a different agent."""
        if not claimed_by or claimed_by == agent_id:
            return False
        return bool(claimed_at and (now - claimed_at) < self._CLAIM_TIMEOUT)

    def _find_conflicting_claims(self, plan_id: int, step_id: int, agent_id: str) -> list[dict[str, Any]]:
        """Find pending steps in other active plans that target the same file path."""
        import re

        step_row = self.conn.execute(
            "SELECT description FROM steps WHERE id = ? AND plan_id = ?",
            (step_id, plan_id),
        ).fetchone()
        if not step_row or not step_row["description"]:
            return []
        desc = step_row["description"]
        # Extract file path from common description patterns like "Create src/x.py" or "Update src/x.py"
        m = re.search(r"(?:Create|Update)\s+([a-zA-Z0-9_./\\~-]+\.[a-zA-Z0-9]+)", desc)
        if not m:
            return []
        target_file = m.group(1).replace("\\", "/")
        # Search other active plans for steps with the same file in description
        rows = self.conn.execute(
            "SELECT s.id, s.plan_id, s.step_index, s.description, p.status "
            "FROM steps s JOIN plans p ON s.plan_id = p.id "
            "WHERE s.plan_id != ? AND p.status IN ('pending','running') "
            "AND s.status = 'pending'",
            (plan_id,),
        ).fetchall()
        conflicts: list[dict[str, Any]] = []
        for r in rows:
            other_desc = r["description"] or ""
            om = re.search(r"(?:Create|Update)\s+([a-zA-Z0-9_./\\~-]+\.[a-zA-Z0-9]+)", other_desc)
            if om and om.group(1).replace("\\", "/") == target_file:
                conflicts.append({
                    "step_id": r["id"],
                    "plan_id": r["plan_id"],
                    "step_index": r["step_index"],
                    "file": target_file,
                })
        return conflicts

    def claim_step(self, plan_id: int, step_id: int, agent_id: str) -> dict[str, Any]:
        """Claim a step for an agent. Returns result dict with claimed bool and optional warning."""
        now = time.time()
        with transaction(self.conn):
            row = self.conn.execute(
                "SELECT status, claimed_by, claimed_at FROM steps WHERE id = ? AND plan_id = ?",
                (step_id, plan_id),
            ).fetchone()
            if not row:
                return {"claimed": False}
            if row["status"] != "pending":
                return {"claimed": False}
            if self._is_claimed_by_other(row["claimed_by"], row["claimed_at"], agent_id, now):
                return {"claimed": False}
            self.conn.execute(
                "UPDATE steps SET claimed_by = ?, claimed_at = ? WHERE id = ?",
                (agent_id, now, step_id),
            )
        result: dict[str, Any] = {"claimed": True}
        conflicts = self._find_conflicting_claims(plan_id, step_id, agent_id)
        if conflicts:
            result["warning"] = (
                f"Other active plan(s) also have pending steps for {conflicts[0]['file']}: "
                + ", ".join(f"plan {c['plan_id']} step {c['step_id']}" for c in conflicts[:3])
            )
        return result

    def release_step(self, step_id: int, agent_id: str) -> None:
        """Release a step claim. Only the owning agent can release."""
        with transaction(self.conn):
            self.conn.execute(
                "UPDATE steps SET claimed_by = NULL, claimed_at = NULL "
                "WHERE id = ? AND claimed_by = ?",
                (step_id, agent_id),
            )

    def get_available_steps(self, plan_id: int, agent_id: str) -> list[dict[str, Any]]:
        """Get steps whose deps are satisfied and aren't claimed by another agent."""
        plan = self.get_plan(plan_id)
        if not plan:
            return []
        now = time.time()
        passed = {s["step_index"] for s in plan["steps"] if s["status"] == "passed"}
        available: list[dict[str, Any]] = []
        for step in plan["steps"]:
            if step["status"] != "pending":
                continue
            if not all(d in passed for d in step.get("depends_on", [])):
                continue
            if self._is_claimed_by_other(step.get("claimed_by"), step.get("claimed_at"), agent_id, now):
                continue
            available.append(step)
        return available
