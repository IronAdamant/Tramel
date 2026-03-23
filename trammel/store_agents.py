"""Multi-agent coordination mixin: step claiming, availability, release."""

from __future__ import annotations

import time
from typing import Any

from .utils import transaction


class AgentStoreMixin:
    """Multi-agent step coordination mixed into RecipeStore."""

    _CLAIM_TIMEOUT = 600  # 10 minutes — stale claims auto-expire

    def _is_claimed_by_other(
        self, claimed_by: str | None, claimed_at: float | None, agent_id: str, now: float,
    ) -> bool:
        """Check if a step is actively claimed by a different agent."""
        if not claimed_by or claimed_by == agent_id:
            return False
        return bool(claimed_at and (now - claimed_at) < self._CLAIM_TIMEOUT)

    def claim_step(self, plan_id: int, step_id: int, agent_id: str) -> bool:
        """Claim a step for an agent. Returns False if already claimed by another."""
        now = time.time()
        with transaction(self.conn):
            row = self.conn.execute(
                "SELECT claimed_by, claimed_at FROM steps WHERE id = ? AND plan_id = ?",
                (step_id, plan_id),
            ).fetchone()
            if not row:
                return False
            if self._is_claimed_by_other(row[0], row[1], agent_id, now):
                return False
            self.conn.execute(
                "UPDATE steps SET claimed_by = ?, claimed_at = ? WHERE id = ?",
                (agent_id, now, step_id),
            )
        return True

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
