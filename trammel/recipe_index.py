"""Inverted word-index + MinHash LSH for recipe retrieval (stdlib only)."""

from __future__ import annotations

import hashlib
import math
import re
import sqlite3
from collections import Counter
from typing import Any


def _tokenize(text: str) -> list[str]:
    """Extract lowercase word tokens (min length 3) from text."""
    return [w.lower() for w in re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', text) if len(w) > 2]


def _minhash_signature(text: str, num_hashes: int = 64) -> tuple[int, ...]:
    """Compute a MinHash signature for a text using purely stdlib hashlib."""
    words = set(_tokenize(text))
    if not words:
        return tuple([0] * num_hashes)
    sig: list[int] = []
    for i in range(num_hashes):
        min_val = float("inf")
        for w in words:
            h = int(hashlib.md5(f"{i}:{w}".encode()).hexdigest(), 16)
            if h < min_val:
                min_val = h
        sig.append(int(min_val))
    return tuple(sig)


class RecipeIndexMixin:
    """Inverted word index + MinHash LSH for recipe similarity search.

    Expects the composing class to provide:
        conn: sqlite3.Connection
    """

    conn: sqlite3.Connection

    def _init_recipe_index_schema(self) -> None:
        """Ensure index tables exist."""
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS recipe_terms ("
            "term TEXT NOT NULL, recipe_sig TEXT NOT NULL, count INTEGER NOT NULL DEFAULT 1)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_recipe_terms_term "
            "ON recipe_terms(term, recipe_sig)"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS recipe_signatures ("
            "recipe_sig TEXT PRIMARY KEY, sig TEXT NOT NULL)"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS recipe_index_meta ("
            "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )

    def _index_recipe_terms(self, sig: str, goal: str) -> None:
        """Index tokenized goal text for a recipe signature."""
        self.conn.execute("DELETE FROM recipe_terms WHERE recipe_sig = ?", (sig,))
        words = _tokenize(goal)
        for word, count in Counter(words).items():
            self.conn.execute(
                "INSERT INTO recipe_terms (term, recipe_sig, count) VALUES (?, ?, ?)",
                (word, sig, count),
            )

    def _index_recipe_minhash(self, sig: str, goal: str) -> None:
        """Store MinHash signature for a recipe signature."""
        minhash = _minhash_signature(goal)
        self.conn.execute(
            "INSERT OR REPLACE INTO recipe_signatures (recipe_sig, sig) VALUES (?, ?)",
            (sig, ",".join(str(x) for x in minhash)),
        )

    def _remove_recipe_index(self, sig: str) -> None:
        """Remove index entries for a recipe signature."""
        self.conn.execute("DELETE FROM recipe_terms WHERE recipe_sig = ?", (sig,))
        self.conn.execute("DELETE FROM recipe_signatures WHERE recipe_sig = ?", (sig,))

    def search_recipes_by_terms(
        self, goal: str, top_k: int = 20,
    ) -> list[tuple[str, float]]:
        """TF-IDF cosine-approximation search over indexed recipe goal text.

        Returns list of (recipe_sig, score) sorted descending.
        """
        words = _tokenize(goal)
        if not words:
            return []

        placeholders = ",".join("?" * len(words))
        df_rows = self.conn.execute(
            f"SELECT term, COUNT(DISTINCT recipe_sig) AS df "
            f"FROM recipe_terms WHERE term IN ({placeholders}) GROUP BY term",
            tuple(words),
        ).fetchall()
        df_map = {r["term"]: r["df"] for r in df_rows}

        total_docs_row = self.conn.execute(
            "SELECT COUNT(DISTINCT recipe_sig) FROM recipe_terms"
        ).fetchone()
        total_docs = total_docs_row[0] if total_docs_row else 0
        if total_docs == 0:
            return []

        query_tf = Counter(words)
        term_rows = self.conn.execute(
            f"SELECT recipe_sig, term, count FROM recipe_terms WHERE term IN ({placeholders})",
            tuple(words),
        ).fetchall()

        scores: dict[str, float] = {}
        for row in term_rows:
            sig, term, doc_count = row["recipe_sig"], row["term"], row["count"]
            df = df_map.get(term, 1)
            idf = math.log((total_docs + 1) / (df + 1)) + 1.0
            weight = doc_count * idf * query_tf[term]
            scores[sig] = scores.get(sig, 0.0) + weight

        query_norm = sum(
            (query_tf[w] * (math.log((total_docs + 1) / (df_map.get(w, 1) + 1)) + 1.0)) ** 2
            for w in words
        ) ** 0.5
        if query_norm > 0:
            for sig in scores:
                scores[sig] /= query_norm

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_scores[:top_k]

    def search_recipes_by_minhash(
        self, goal: str, threshold: float = 0.5, top_n: int = 20,
    ) -> list[tuple[str, float]]:
        """MinHash Jaccard-approximation search over indexed recipes.

        Returns list of (recipe_sig, estimated_jaccard) sorted descending.
        """
        query_sig = _minhash_signature(goal)
        rows = self.conn.execute("SELECT recipe_sig, sig FROM recipe_signatures").fetchall()
        candidates: list[tuple[str, float]] = []
        for row in rows:
            sig = row["recipe_sig"]
            stored = tuple(int(x) for x in row["sig"].split(","))
            if len(stored) != len(query_sig):
                continue
            matches = sum(1 for a, b in zip(query_sig, stored) if a == b)
            sim = matches / len(query_sig)
            if sim >= threshold:
                candidates.append((sig, sim))
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:top_n]

    def backfill_recipe_index(self) -> dict[str, int]:
        """Index all recipes that lack term entries. Returns counts."""
        indexed = {
            r["recipe_sig"]
            for r in self.conn.execute("SELECT DISTINCT recipe_sig FROM recipe_terms").fetchall()
        }
        rows = self.conn.execute("SELECT sig, pattern FROM recipes").fetchall()
        added = 0
        for row in rows:
            sig = row["sig"]
            if sig in indexed:
                continue
            goal = row["pattern"]
            self._index_recipe_terms(sig, goal)
            self._index_recipe_minhash(sig, goal)
            added += 1
        return {"recipes_checked": len(rows), "indexed": added}
