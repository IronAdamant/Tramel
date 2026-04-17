"""Scaffold-recipe mixin: persist and retrieve reusable scaffold templates.

Separated from :mod:`store_recipes` to keep the main recipe module under the
project's 500-LOC target. Scaffold recipes let Trammel remember the *shape*
of successful greenfield plans (file roles + DAG metrics) so similar future
goals can auto-populate a scaffold.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from typing import TYPE_CHECKING, Any

from .recipe_fingerprints import (
    _FILE_ROLE_RE,
    goal_scaffold_fingerprint_from_text as _goal_scaffold_fingerprint_from_text,
    scaffold_fingerprint as _scaffold_fingerprint,
    scaffold_structural_similarity as _scaffold_structural_similarity,
    sql_in as _sql_in,
)
from .utils import (
    dumps_json, goal_similarity, normalize_goal,
    sha256_json, transaction, unique_trigrams,
)

if TYPE_CHECKING:
    from .store import RecipeStore  # noqa: F401 — documents mixin host


_MAX_PATTERN_LENGTH = 200


class ScaffoldRecipeMixin:
    """Persist and retrieve scaffold-only recipes matched by goal + structure."""

    conn: sqlite3.Connection

    def _init_scaffold_schema(self) -> None:
        """Ensure scaffold_recipes and scaffold_trigrams tables exist (migration-safe)."""
        try:
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS scaffold_recipes ("
                "sig TEXT PRIMARY KEY,"
                "pattern TEXT NOT NULL,"
                "scaffold TEXT NOT NULL,"
                "domain_kw TEXT NOT NULL DEFAULT '',"
                "role_counts TEXT NOT NULL DEFAULT '{}',"
                "successes INTEGER NOT NULL DEFAULT 0,"
                "failures INTEGER NOT NULL DEFAULT 0,"
                "created REAL NOT NULL,"
                "updated REAL NOT NULL"
                ")"
            )
        except sqlite3.OperationalError:
            pass
        try:
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_scaffold_trigrams_tri ON scaffold_trigrams(trigram)"
            )
        except sqlite3.OperationalError:
            pass
        try:
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS scaffold_trigrams ("
                "trigram TEXT NOT NULL,"
                "scaffold_sig TEXT NOT NULL"
                ")"
            )
        except sqlite3.OperationalError:
            pass

    def _extract_scaffold_roles(
        self, scaffold: list[dict[str, Any]]
    ) -> dict[str, int]:
        """Count file roles from scaffold entries using the shared role patterns."""
        role_counts: dict[str, int] = {}
        for entry in scaffold:
            f = entry.get("file", "")
            for (pat_re, _offset), role in _FILE_ROLE_RE:
                if pat_re.search(f):
                    role_counts[role] = role_counts.get(role, 0) + 1
                    break
        return role_counts

    def save_scaffold_recipe(
        self,
        goal: str,
        scaffold: list[dict[str, Any]],
        outcome: bool,
    ) -> None:
        """Save a scaffold template from a successful plan.

        When the LLM provides an explicit scaffold for a goal and the plan
        succeeds, this stores the scaffold as a reusable template matched by
        goal-text similarity and structural role fingerprint — enabling
        auto-scaffold for future similar goals.
        """
        if not scaffold:
            return
        scaffold_key = sorted(
            ({"file": e.get("file", ""), "depends_on": sorted(e.get("depends_on", []))}
             for e in scaffold if e.get("file")),
            key=lambda x: (x["file"], tuple(x["depends_on"])),
        )
        sig = sha256_json(scaffold_key)
        pattern = goal[:_MAX_PATTERN_LENGTH]
        scaffold_json = dumps_json(scaffold)
        role_counts = self._extract_scaffold_roles(scaffold)
        now = time.time()
        col = "successes" if outcome else "failures"
        goal_words = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', goal.lower())
        role_kw = frozenset({
            "add", "create", "build", "implement", "with", "using", "file", "files",
            "service", "services", "route", "routes", "model", "models", "module",
            "endpoint", "endpoints", "api", "plugin", "plugins", "system",
        })
        domain_kw = next(
            (w for w in goal_words if len(w) > 3 and w not in role_kw),
            goal_words[-1] if goal_words else "",
        )
        try:
            with transaction(self.conn):
                self.conn.execute(
                    f"""INSERT INTO scaffold_recipes
                        (sig, pattern, scaffold, domain_kw, role_counts, {col}, created, updated)
                        VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                        ON CONFLICT(sig) DO UPDATE SET
                            {col} = scaffold_recipes.{col} + 1,
                            pattern = excluded.pattern,
                            updated = excluded.updated""",
                    (sig, pattern, scaffold_json, domain_kw, dumps_json(role_counts), now, now),
                )
                self.conn.execute(
                    "DELETE FROM scaffold_trigrams WHERE scaffold_sig = ?", (sig,),
                )
                for t in unique_trigrams(normalize_goal(pattern)):
                    self.conn.execute(
                        "INSERT INTO scaffold_trigrams (trigram, scaffold_sig) VALUES (?, ?)",
                        (t, sig),
                    )
        except sqlite3.OperationalError:
            pass

    def retrieve_best_scaffold_recipe(
        self,
        goal: str,
        min_similarity: float = 0.25,
    ) -> dict[str, Any] | None:
        """Find a scaffold recipe matching the goal.

        Uses trigram index + structural fingerprint (role count vector + DAG
        metrics) so stored scaffolds can match even when goal text differs
        from the stored pattern. Returns the scaffold entries directly, or
        ``None`` if no candidate is above threshold.
        """
        goal_tris = unique_trigrams(normalize_goal(goal))
        if not goal_tris:
            return None
        try:
            tri_in, tri_params = _sql_in(sorted(goal_tris))
            rows = self.conn.execute(
                f"""SELECT sig, pattern, scaffold, role_counts, successes, failures, updated
                    FROM scaffold_recipes WHERE sig IN (
                        SELECT DISTINCT scaffold_sig FROM scaffold_trigrams
                        WHERE trigram {tri_in}
                    )""",
                tri_params,
            ).fetchall()
        except sqlite3.OperationalError:
            return None
        if not rows:
            return None
        goal_fp = _goal_scaffold_fingerprint_from_text(goal)
        best: dict[str, Any] | None = None
        best_score = -1.0
        for row in rows:
            text_sim = goal_similarity(goal, row["pattern"])
            if text_sim < min_similarity:
                continue
            try:
                recipe_scaffold = json.loads(row["scaffold"])
            except (json.JSONDecodeError, TypeError):
                recipe_scaffold = []
            fp_b = _scaffold_fingerprint(recipe_scaffold)
            struct_sim = _scaffold_structural_similarity(goal_fp, fp_b)
            score = 0.4 * struct_sim + 0.35 * text_sim + 0.25 * (
                row["successes"] / (row["successes"] + row["failures"] + 1)
            )
            if score > best_score and score >= min_similarity:
                best_score = score
                try:
                    best = {"scaffold": json.loads(row["scaffold"])}
                except (json.JSONDecodeError, TypeError):
                    best = {"scaffold": []}
                best["match_score"] = round(score, 3)
                best["pattern"] = row["pattern"]
        return best

    def _rebuild_scaffold_trigram_index(self) -> None:
        """Rebuild scaffold_trigrams from all scaffold_recipes patterns."""
        try:
            rows = self.conn.execute("SELECT sig, pattern FROM scaffold_recipes").fetchall()
        except sqlite3.OperationalError:
            return
        if not rows:
            return
        with transaction(self.conn):
            self.conn.execute("DELETE FROM scaffold_trigrams")
            for row in rows:
                for t in unique_trigrams(normalize_goal(row["pattern"])):
                    self.conn.execute(
                        "INSERT INTO scaffold_trigrams (trigram, scaffold_sig) VALUES (?, ?)",
                        (t, row["sig"]),
                    )
