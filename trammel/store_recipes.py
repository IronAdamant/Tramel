"""Recipe mixin: save, retrieve, list, prune recipes with trigram + composite scoring."""

from __future__ import annotations

import json
import os
import re
import time
from typing import TYPE_CHECKING, Any

from .utils import (
    dumps_json, goal_similarity, normalize_goal,
    sha256_json, transaction, unique_trigrams,
)

if TYPE_CHECKING:
    import sqlite3
    from .store import RecipeStore  # noqa: F401 — documents mixin host


_MAX_PATTERN_LENGTH = 200
_MAX_LOG_GOAL_LENGTH = 100
_NEAR_PERFECT_SIMILARITY = 0.9999

# ── Structural fingerprinting for recipe matching (Fix 2) ─────────────────────

# File-role patterns: tuples of (regex_on_path, role_label).
_FILE_ROLE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"[/\\]services?[/\\]", "service"),
    (r"[/\\]routes?[/\\]", "route"),
    (r"[/\\]controllers?[/\\]", "controller"),
    (r"[/\\]handlers?[/\\]", "handler"),
    (r"[/\\]engines?[/\\]", "engine"),
    (r"[/\\]algorithms?[/\\]", "algorithm"),
    (r"[/\\]models?[/\\]", "model"),
    (r"[/\\]repositories?[/\\]", "repository"),
    (r"[/\\]middleware[/\\]", "middleware"),
    (r"[/\\]plugins?[/\\]", "plugin"),
    (r"[/\\]registries?[/\\]", "registry"),
    (r"[/\\]collectors?[/\\]", "collector"),
    (r"[/\\]aggregators?[/\\]", "aggregator"),
    (r"[/\\]generators?[/\\]", "generator"),
    (r"[/\\]utils?[/\\]", "util"),
    (r"[/\\]lib[/\\]", "lib"),
    (r"[/\\]schemas?[/\\]", "schema"),
    (r"[/\.]test\.", "test"),
    (r"[/\.]spec\.", "spec"),
    (r"[/\\]tests?[/\\]", "test"),
    (r"[/\.]config\.", "config"),
    (r"[/\.]index\.", "entry"),
)

_FILE_ROLE_RE: list[tuple[tuple[str, int], str]] = [
    ((re.compile(pat, re.IGNORECASE), offset), role)
    for offset, (pat, role) in enumerate(_FILE_ROLE_PATTERNS)
]


def _strategy_fingerprint(strategy: dict[str, Any]) -> dict[str, Any]:
    """Extract structural features from a strategy for structural matching.

    Returns a fingerprint dict with:
    - role_counts: {role_label: count} for each file-role detected
    - total_files: total step file count
    - create_count: how many steps are "create" actions
    - modify_count: how many steps are not "create"
    - avg_symbols_per_file: mean symbol_count across steps
    - has_test: bool (any test file detected)
    - has_service: bool (any service file detected)
    - has_route: bool (any route file detected)
    - has_algorithm: bool (any algorithm/engine file detected)
    - role_vector: sorted (role, count) pairs as a tuple for cosine comparison
    """
    steps = strategy.get("steps", [])
    if not steps:
        return {
            "role_counts": {}, "total_files": 0, "create_count": 0,
            "modify_count": 0, "avg_symbols": 0.0,
            "has_test": False, "has_service": False, "has_route": False,
            "has_algorithm": False, "role_vector": (),
        }

    role_counts: dict[str, int] = {}
    total_syms = 0
    has_test = has_service = has_route = has_algorithm = False
    create_count = modify_count = 0

    for s in steps:
        f = s.get("file", "")
        action = s.get("action", "")
        if action == "create":
            create_count += 1
        else:
            modify_count += 1

        sym_count = s.get("symbol_count", 0)
        if sym_count is None:
            sym_count = len(s.get("symbols", []))
        total_syms += sym_count

        # Role detection
        for (pat_re, _offset), role in _FILE_ROLE_RE:
            if pat_re.search(f):
                role_counts[role] = role_counts.get(role, 0) + 1
                if role == "test":
                    has_test = True
                elif role == "service":
                    has_service = True
                elif role == "route":
                    has_route = True
                elif role in ("algorithm", "engine"):
                    has_algorithm = True
                break

    avg_syms = total_syms / len(steps) if steps else 0.0

    # Build a fixed-width role vector for cosine similarity
    ALL_ROLES = (
        "algorithm", "engine", "service", "route", "controller", "handler",
        "model", "repository", "middleware", "plugin", "registry",
        "collector", "aggregator", "generator", "util", "test", "other",
    )
    role_vec = tuple(role_counts.get(r, 0) for r in ALL_ROLES)

    return {
        "role_counts": role_counts,
        "total_files": len(steps),
        "create_count": create_count,
        "modify_count": modify_count,
        "avg_symbols": round(avg_syms, 2),
        "has_test": has_test,
        "has_service": has_service,
        "has_route": has_route,
        "has_algorithm": has_algorithm,
        "role_vector": role_vec,
    }


def _structural_similarity(fp_a: dict[str, Any], fp_b: dict[str, Any]) -> float:
    """Cosine similarity between two structural fingerprints.

    Compares role vectors, plus bonus for matching structural boolean flags.
    Returns 0.0–1.0.
    """
    from .utils import _cosine

    vec_a = list(fp_a.get("role_vector") or ())
    vec_b = list(fp_b.get("role_vector") or ())
    max_len = max(len(vec_a), len(vec_b))
    vec_a = vec_a + [0] * (max_len - len(vec_a))
    vec_b = vec_b + [0] * (max_len - len(vec_b))

    vec_sim = _cosine(vec_a, vec_b)

    # Bonus for matching structural features
    bonus = 0.0
    structural_keys = (
        "has_test", "has_service", "has_route", "has_algorithm",
        "has_collector", "has_aggregator", "has_generator",
    )
    for k in structural_keys:
        if fp_a.get(k) and fp_b.get(k):
            bonus += 0.05
    bonus = min(bonus, 0.2)  # Cap bonus at 0.2

    return min(vec_sim + bonus, 1.0)


def _goal_fingerprint_from_text(goal: str) -> dict[str, Any]:
    """Derive a structural fingerprint from goal text alone (no strategy needed).

    Detects role keywords in the goal text and estimates file-role counts,
    enabling structural recipe matching even for goals without a prior strategy.
    """
    goal_lower = goal.lower()
    role_counts: dict[str, int] = {}
    has_test = has_service = has_route = has_algorithm = False
    has_collector = has_aggregator = has_generator = has_registry = has_manager = False

    for (pat_re, _offset), role in _FILE_ROLE_RE:
        matches = pat_re.findall(goal_lower)
        if matches:
            role_counts[role] = role_counts.get(role, 0) + len(matches)
            if role == "test":
                has_test = True
            elif role == "service":
                has_service = True
            elif role == "route":
                has_route = True
            elif role in ("algorithm", "engine"):
                has_algorithm = True

    # Detect layered architecture keywords that imply multiple files per role
    layered_kw = {
        "similarity": [("algorithm", 1), ("engine", 1), ("service", 1), ("route", 1)],
        "optimize": [("algorithm", 1), ("service", 1), ("route", 1)],
        "metric": [("collector", 1), ("aggregator", 1), ("route", 1)],
        "plugin": [("registry", 1), ("manager", 1), ("plugin", 1)],
        "openapi": [("generator", 1)],
    }
    for kw, layers in layered_kw.items():
        if kw in goal_lower:
            for role, count in layers:
                role_counts[role] = role_counts.get(role, 0) + count
                if role == "test":
                    has_test = True
                elif role == "service":
                    has_service = True
                elif role == "route":
                    has_route = True
                elif role in ("algorithm", "engine"):
                    has_algorithm = True
                elif role == "collector":
                    has_collector = True  # noqa: F821 — defined by first loop
                elif role == "aggregator":
                    has_aggregator = True  # noqa: F821
                elif role == "generator":
                    has_generator = True  # noqa: F821
                elif role == "registry":
                    has_registry = True  # noqa: F821
                elif role == "manager":
                    has_manager = True  # noqa: F821

    # Detect plural/collective keywords that imply multiple files
    multi_file_kw = {
        "algorithm": 8, "algorithms": 8,
        "service": 1, "services": 2,
        "route": 1, "routes": 5,
        "endpoint": 3, "endpoints": 6,
        "api": 2,
        "plugin": 1, "plugins": 3,
        "metric": 1, "metrics": 3,
    }
    for kw, count in multi_file_kw.items():
        if kw in goal_lower:
            role_counts["service"] = role_counts.get("service", 0) + count // 4

    ALL_ROLES = (
        "algorithm", "engine", "service", "route", "controller", "handler",
        "model", "repository", "middleware", "plugin", "registry",
        "collector", "aggregator", "generator", "util", "test", "other",
    )
    role_vec = tuple(role_counts.get(r, 0) for r in ALL_ROLES)

    return {
        "role_counts": role_counts,
        "total_files": sum(role_counts.values()),
        "create_count": sum(role_counts.values()),
        "modify_count": 0,
        "avg_symbols": 0.0,
        "has_test": has_test,
        "has_service": has_service,
        "has_route": has_route,
        "has_algorithm": has_algorithm,
        "has_collector": has_collector,
        "has_aggregator": has_aggregator,
        "has_generator": has_generator,
        "has_registry": has_registry,
        "has_manager": has_manager,
        "role_vector": role_vec,
    }

# P3: Scaffold detection — reject scaffold recipes on populated projects
_SCAFFOLD_SIGNALS = frozenset({
    "scaffold", "initialize", "setup", "set up", "from scratch", "bootstrap",
    "new project", "phase 1", "build phase", "create project", "start project",
})
_SCAFFOLD_PENALTY = 0.25


def _is_scaffold_pattern(pattern: str) -> bool:
    """Detect whether a recipe pattern describes project scaffolding."""
    lower = pattern.lower()
    return any(signal in lower for signal in _SCAFFOLD_SIGNALS)


def _recipe_match_components(
    goal: str,
    pattern: str,
    successes: int,
    failures: int,
    updated: float,
    context_files: set[str] | None,
    recipe_files: set[str],
    recipe_strategy: dict[str, Any] | None,
    now: float,
    *,
    w_text: float,
    w_files: float,
    w_success: float,
    w_recency: float,
    w_structural: float,
    recency_half_life: float,
    goal_fingerprint: dict[str, Any] | None = None,
) -> tuple[float, float, dict[str, float]]:
    """Text similarity, ranking score, and component dict.

    Ranking score mirrors ``retrieve_best_recipe``: text-only when
    ``context_files`` is None; otherwise weighted composite (with scaffold
    penalty when applicable). Structural fingerprint similarity is included
    when both recipe_strategy and goal_fingerprint are available (Fix 2).
    """
    text_sim = goal_similarity(goal, pattern)
    if context_files is None:
        return text_sim, text_sim, {"text_similarity": round(text_sim, 3)}

    if recipe_files and context_files:
        file_overlap = len(context_files & recipe_files) / len(context_files | recipe_files)
    else:
        file_overlap = 0.0

    total = successes + failures
    success_ratio = successes / total if total > 0 else 0.5
    recency = 0.5 ** ((now - updated) / recency_half_life)

    # Structural fingerprint similarity (Fix 2): compare strategy architectures
    struct_sim = 0.0
    if recipe_strategy is not None and goal_fingerprint is not None:
        recipe_fp = _strategy_fingerprint(recipe_strategy)
        struct_sim = _structural_similarity(goal_fingerprint, recipe_fp)

    score = (
        w_text * text_sim
        + w_files * file_overlap
        + w_success * success_ratio
        + w_recency * recency
        + w_structural * struct_sim
    )
    if _is_scaffold_pattern(pattern) and context_files and len(context_files) > 10:
        score *= _SCAFFOLD_PENALTY

    components = {
        "text_similarity": round(text_sim, 3),
        "file_overlap": round(file_overlap, 3),
        "success_ratio": round(success_ratio, 3),
        "recency": round(recency, 3),
        "structural_similarity": round(struct_sim, 3),
    }
    return text_sim, score, components


def _sql_in(items: list[str] | tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    """Build an SQL IN clause and parameter tuple: ``'IN (?,?,?)' , (a, b, c)``.

    Raises ValueError on empty input (produces invalid SQL).
    """
    if not items:
        raise ValueError("_sql_in requires a non-empty sequence")
    ph = ",".join("?" for _ in items)
    return f"IN ({ph})", tuple(items)


class RecipeStoreMixin:
    """Recipe-related methods mixed into RecipeStore.

    Expects the composing class to provide:
        conn: sqlite3.Connection
        log_event(event_type, detail, value) -> None
    """

    conn: sqlite3.Connection

    # Fields stripped from strategy before computing the content-addressed sig.
    # These are volatile (change every run) or ephemeral (only meaningful during
    # a single session) and must not cause duplicate recipe entries.
    _VOLATILE_STRATEGY_KEYS = frozenset({"_source", "analysis_meta"})

    def log_event(self, event_type: str, detail: str = "", value: float | None = None) -> None:
        """Provided by composing class."""
        raise NotImplementedError

    @classmethod
    def _stable_strategy_sig(cls, strategy: dict[str, Any]) -> str:
        """Compute a content-addressed sig from the stable subset of a strategy.

        Strips volatile fields (timing data, source tags) so that the same
        decomposition always produces the same sig regardless of when it ran.
        """
        stable = {k: v for k, v in strategy.items() if k not in cls._VOLATILE_STRATEGY_KEYS}
        return sha256_json(stable)

    def _insert_trigrams(self, sig: str, tris: set[str]) -> None:
        """Insert trigram index entries for a recipe."""
        if tris:
            self.conn.executemany(
                "INSERT INTO recipe_trigrams (trigram, recipe_sig) VALUES (?, ?)",
                [(t, sig) for t in tris],
            )

    @staticmethod
    def _extract_step_files(strategy: dict[str, Any]) -> set[str]:
        """Extract file paths from strategy steps."""
        return {f for s in strategy.get("steps", []) if (f := s.get("file"))}

    def _insert_file_entries(self, sig: str, files: set[str]) -> None:
        """Insert file entries for a recipe."""
        if files:
            self.conn.executemany(
                "INSERT INTO recipe_files (recipe_sig, file_path) VALUES (?, ?)",
                [(sig, f) for f in files],
            )

    def _rebuild_trigram_index(self) -> None:
        """Rebuild recipe_trigrams using normalized goal text for synonym-aware matching."""
        rows = self.conn.execute("SELECT sig, pattern FROM recipes").fetchall()
        if not rows:
            return
        with transaction(self.conn):
            self.conn.execute("DELETE FROM recipe_trigrams")
            for row in rows:
                self._insert_trigrams(row["sig"], unique_trigrams(normalize_goal(row["pattern"])))

    def _backfill_files(self) -> None:
        """Populate recipe_files for recipes that lack file entries."""
        orphans = self.conn.execute(
            "SELECT sig, strategy FROM recipes WHERE sig NOT IN "
            "(SELECT DISTINCT recipe_sig FROM recipe_files)"
        ).fetchall()
        if not orphans:
            return
        with transaction(self.conn):
            for row in orphans:
                sig, strategy_str = row["sig"], row["strategy"]
                try:
                    strategy = json.loads(strategy_str)
                except (json.JSONDecodeError, TypeError):
                    continue
                self._insert_file_entries(sig, self._extract_step_files(strategy))

    # ── Recipes ──────────────────────────────────────────────────────────────

    def save_recipe(
        self,
        goal: str,
        strategy: dict[str, Any],
        outcome: bool,
        constraints: list[dict[str, Any]] | None = None,
    ) -> None:
        sig = self._stable_strategy_sig(strategy)
        pattern = goal[:_MAX_PATTERN_LENGTH]
        strat_json = dumps_json(strategy)
        const_json = dumps_json(constraints or [])
        now = time.time()
        col = "successes" if outcome else "failures"
        extra = ", constraints = excluded.constraints" if outcome else ""
        with transaction(self.conn):
            self.conn.execute(
                f"""INSERT INTO recipes (sig, pattern, strategy, constraints, {col}, created, updated)
                    VALUES (?, ?, ?, ?, 1, ?, ?)
                    ON CONFLICT(sig) DO UPDATE SET
                        {col} = recipes.{col} + 1,
                        pattern = excluded.pattern{extra},
                        updated = excluded.updated""",
                (sig, pattern, strat_json, const_json, now, now),
            )
            self.conn.execute(
                "DELETE FROM recipe_trigrams WHERE recipe_sig = ?", (sig,),
            )
            self._insert_trigrams(sig, unique_trigrams(normalize_goal(pattern)))
            self.conn.execute(
                "DELETE FROM recipe_files WHERE recipe_sig = ?", (sig,),
            )
            self._insert_file_entries(sig, self._extract_step_files(strategy))

    _W_TEXT = 0.35
    _W_FILES = 0.20
    _W_SUCCESS = 0.15
    _W_RECENCY = 0.15
    _W_STRUCTURAL = 0.15  # Fix 2: structural fingerprint similarity
    _RECENCY_HALF_LIFE = 30 * 86400  # 30 days in seconds

    def retrieve_best_recipe(
        self,
        goal: str,
        min_similarity: float = 0.55,
        context_files: set[str] | None = None,
    ) -> dict[str, Any] | None:
        goal_tris = unique_trigrams(normalize_goal(goal))
        if not goal_tris:
            return None
        tri_in, tri_params = _sql_in(sorted(goal_tris))
        candidate_sigs = self.conn.execute(
            f"SELECT DISTINCT recipe_sig FROM recipe_trigrams WHERE trigram {tri_in}",
            tri_params,
        ).fetchall()
        if not candidate_sigs:
            return None
        sig_list = [row["recipe_sig"] for row in candidate_sigs]
        sig_in, sig_params = _sql_in(sig_list)
        cur = self.conn.execute(
            f"SELECT sig, pattern, strategy, successes, failures, updated FROM recipes "
            f"WHERE sig {sig_in}",
            sig_params,
        )
        # Batch-fetch file paths for all candidates to avoid N+1 queries
        candidates = cur.fetchall()
        sig_files: dict[str, set[str]] = {}
        if context_files is not None and candidates:
            all_sigs = [row["sig"] for row in candidates]
            file_in, file_params = _sql_in(all_sigs)
            file_rows = self.conn.execute(
                f"SELECT recipe_sig, file_path FROM recipe_files WHERE recipe_sig {file_in}",
                file_params,
            ).fetchall()
            for frow in file_rows:
                sig_files.setdefault(frow["recipe_sig"], set()).add(frow["file_path"])

        # Fix 2: compute goal structural fingerprint once when context_files is available
        goal_fp: dict[str, Any] | None = None
        if context_files is not None:
            goal_fp = _goal_fingerprint_from_text(goal)

        best: dict[str, Any] | None = None
        best_score = -1.0
        best_meta: dict[str, Any] = {}
        now = time.time()
        for row in candidates:
            sig, pattern = row["sig"], row["pattern"]
            strategy_str, succ, fail, updated = row["strategy"], row["successes"], row["failures"], row["updated"]
            recipe_files = sig_files.get(sig, set()) if context_files is not None else set()

            # Parse strategy once for structural fingerprinting
            recipe_strategy: dict[str, Any] | None = None
            if goal_fp is not None:
                try:
                    recipe_strategy = json.loads(strategy_str)
                except (json.JSONDecodeError, TypeError):
                    recipe_strategy = None

            text_sim, score, components = _recipe_match_components(
                goal, pattern, succ, fail, updated,
                context_files, recipe_files, recipe_strategy, now,
                w_text=self._W_TEXT, w_files=self._W_FILES,
                w_success=self._W_SUCCESS, w_recency=self._W_RECENCY,
                w_structural=self._W_STRUCTURAL,
                recency_half_life=self._RECENCY_HALF_LIFE,
                goal_fingerprint=goal_fp,
            )
            if text_sim < min_similarity:
                continue

            # Floor: reject weak composite matches on the structural path
            if context_files is not None and score < 0.35:
                continue

            if score > best_score:
                try:
                    candidate = json.loads(strategy_str)
                except (json.JSONDecodeError, TypeError):
                    continue
                best_score = score
                best = candidate
                best_meta = {
                    "sig": sig[:12],
                    "pattern": pattern,
                    "match_score": round(score, 3),
                    "match_components": components,
                    "successes": succ,
                    "failures": fail,
                }
                if context_files is None and text_sim >= _NEAR_PERFECT_SIMILARITY:
                    break

        if best is not None:
            self.log_event("recipe_hit", goal[:_MAX_LOG_GOAL_LENGTH], best_score)
            best["_match"] = best_meta
        else:
            self.log_event("recipe_miss", goal[:_MAX_LOG_GOAL_LENGTH])
        return best

    def retrieve_near_matches(
        self,
        goal: str,
        n: int = 3,
        min_score: float = 0.15,
        context_files: set[str] | None = None,
        min_composite: float = 0.35,
    ) -> list[dict[str, Any]]:
        """Return top-N near-miss recipe candidates for reference.

        Surfaces recipes that are related but below the auto-match threshold,
        helping decompose inform the caller about potentially relevant past work.

        When ``context_files`` is set (project file paths from analysis), ranking
        uses the same composite score as ``retrieve_best_recipe`` (text + file
        overlap + success + recency + structural), with ``min_composite`` as a floor.
        Each entry includes ``score`` (text similarity, for backward compatibility),
        ``match_score`` (composite when ``context_files`` is set), and
        ``match_components`` when structural scoring applies.
        """
        goal_tris = unique_trigrams(normalize_goal(goal))
        if not goal_tris:
            return []
        tri_in, tri_params = _sql_in(sorted(goal_tris))
        candidate_sigs = self.conn.execute(
            f"SELECT DISTINCT recipe_sig FROM recipe_trigrams WHERE trigram {tri_in}",
            tri_params,
        ).fetchall()
        if not candidate_sigs:
            return []
        sig_list = [row["recipe_sig"] for row in candidate_sigs]
        sig_in, sig_params = _sql_in(sig_list)
        rows = self.conn.execute(
            f"SELECT sig, pattern, strategy, successes, failures, updated FROM recipes WHERE sig {sig_in}",
            sig_params,
        ).fetchall()
        sig_files: dict[str, set[str]] = {}
        if context_files is not None and rows:
            all_sigs = [row["sig"] for row in rows]
            file_in, file_params = _sql_in(all_sigs)
            file_rows = self.conn.execute(
                f"SELECT recipe_sig, file_path FROM recipe_files WHERE recipe_sig {file_in}",
                file_params,
            ).fetchall()
            for frow in file_rows:
                sig_files.setdefault(frow["recipe_sig"], set()).add(frow["file_path"])

        # Fix 2: compute goal structural fingerprint once when context_files is available
        goal_fp: dict[str, Any] | None = None
        if context_files is not None:
            goal_fp = _goal_fingerprint_from_text(goal)

        now = time.time()
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            sig = row["sig"]
            pattern = row["pattern"]
            strategy_str = row["strategy"]
            succ, fail, updated = row["successes"], row["failures"], row["updated"]
            recipe_files = sig_files.get(sig, set()) if context_files is not None else set()

            # Parse strategy for structural fingerprinting
            recipe_strategy: dict[str, Any] | None = None
            if goal_fp is not None and strategy_str:
                try:
                    recipe_strategy = json.loads(strategy_str)
                except (json.JSONDecodeError, TypeError):
                    recipe_strategy = None

            text_sim, rank_score, components = _recipe_match_components(
                goal, pattern, succ, fail, updated,
                context_files, recipe_files, recipe_strategy, now,
                w_text=self._W_TEXT, w_files=self._W_FILES,
                w_success=self._W_SUCCESS, w_recency=self._W_RECENCY,
                w_structural=self._W_STRUCTURAL,
                recency_half_life=self._RECENCY_HALF_LIFE,
                goal_fingerprint=goal_fp,
            )
            if text_sim < min_score:
                continue
            if context_files is not None and rank_score < min_composite:
                continue

            entry: dict[str, Any] = {
                "sig": sig[:12],
                "pattern": pattern,
                "score": round(text_sim, 3),
                "successes": succ,
                "failures": fail,
            }
            if context_files is not None:
                entry["match_score"] = round(rank_score, 3)
                entry["match_components"] = components
            scored.append((rank_score if context_files is not None else text_sim, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:n]]

    def list_recipes(self, limit: int = 20) -> list[dict[str, Any]]:
        """List stored recipes with pattern, counts, and file paths."""
        rows = self.conn.execute(
            "SELECT sig, pattern, successes, failures, updated "
            "FROM recipes ORDER BY updated DESC LIMIT ?",
            (limit,),
        ).fetchall()
        if not rows:
            return []
        # Batch-fetch all file paths for the returned recipes
        sigs = [r["sig"] for r in rows]
        sig_in, sig_params = _sql_in(sigs)
        file_rows = self.conn.execute(
            f"SELECT recipe_sig, file_path FROM recipe_files WHERE recipe_sig {sig_in}",
            sig_params,
        ).fetchall()
        sig_files: dict[str, list[str]] = {}
        for frow in file_rows:
            sig_files.setdefault(frow["recipe_sig"], []).append(frow["file_path"])
        return [
            {
                "sig": r["sig"][:12],
                "pattern": r["pattern"],
                "successes": r["successes"],
                "failures": r["failures"],
                "files": sig_files.get(r["sig"], []),
                "updated": r["updated"],
            }
            for r in rows
        ]

    def prune_recipes(self, max_age_days: int = 90, min_success_ratio: float = 0.1) -> int:
        """Remove stale, low-quality recipes. Returns count of pruned recipes."""
        cutoff = time.time() - (max_age_days * 86400)
        pruned = [
            row["sig"] for row in self.conn.execute(
                "SELECT sig FROM recipes WHERE updated < ? AND "
                "(successes + failures = 0 OR CAST(successes AS REAL) / (successes + failures) < ?)",
                (cutoff, min_success_ratio),
            ).fetchall()
        ]
        if not pruned:
            return 0
        prune_in, prune_params = _sql_in(pruned)
        with transaction(self.conn):
            self.conn.execute(f"DELETE FROM recipe_trigrams WHERE recipe_sig {prune_in}", prune_params)
            self.conn.execute(f"DELETE FROM recipe_files WHERE recipe_sig {prune_in}", prune_params)
            self.conn.execute(f"DELETE FROM recipes WHERE sig {prune_in}", prune_params)
        return len(pruned)

    def validate_recipes(self, project_root: str) -> dict[str, Any]:
        """Check recipe file entries against current project. Remove stale entries.

        Returns {recipes_checked, files_removed, recipes_invalidated}.
        Recipes whose files are entirely missing are pruned.
        """
        rows = self.conn.execute(
            "SELECT DISTINCT recipe_sig FROM recipe_files"
        ).fetchall()
        # Batch-fetch all file entries
        all_file_rows = self.conn.execute(
            "SELECT recipe_sig, file_path FROM recipe_files"
        ).fetchall()
        sig_files: dict[str, list[str]] = {}
        for frow in all_file_rows:
            sig_files.setdefault(frow["recipe_sig"], []).append(frow["file_path"])

        files_removed = 0
        invalidated: list[str] = []
        stale_pairs: list[tuple[str, str]] = []
        for row in rows:
            sig = row["recipe_sig"]
            file_list = sig_files.get(sig, [])
            missing = [f for f in file_list if not os.path.isfile(os.path.join(project_root, f))]
            if not missing:
                continue
            stale_pairs.extend((sig, f) for f in missing)
            files_removed += len(missing)
            if len(missing) == len(file_list):
                invalidated.append(sig)
        # Single transaction for all removals
        if stale_pairs or invalidated:
            with transaction(self.conn):
                if stale_pairs:
                    self.conn.executemany(
                        "DELETE FROM recipe_files WHERE recipe_sig = ? AND file_path = ?",
                        stale_pairs,
                    )
                if invalidated:
                    inv_in, inv_params = _sql_in(invalidated)
                    self.conn.execute(f"DELETE FROM recipe_trigrams WHERE recipe_sig {inv_in}", inv_params)
                    self.conn.execute(f"DELETE FROM recipes WHERE sig {inv_in}", inv_params)
        return {
            "recipes_checked": len(rows),
            "files_removed": files_removed,
            "recipes_invalidated": len(invalidated),
        }
