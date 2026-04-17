"""Load pattern configuration from ``trammel/data/patterns.json``.

Centralizes the previously-inline naming-convention rules, infrastructure
patterns, and file/goal role regex tables so they can be tuned without
code changes. Values are parsed into the same in-memory shapes callers
expected before externalization, so existing call sites are unchanged.
"""

from __future__ import annotations

import json
import os
from typing import Any


_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_PATH = os.path.join(_THIS_DIR, "data", "patterns.json")


def _tuple_pairs(raw: Any, context: str) -> list[tuple[str, float]]:
    """Convert a JSON list of [str, number] pairs to list[tuple[str, float]]."""
    if not isinstance(raw, list):
        raise ValueError(f"{context}: expected list, got {type(raw).__name__}")
    out: list[tuple[str, float]] = []
    for i, entry in enumerate(raw):
        if not (isinstance(entry, list) and len(entry) == 2):
            raise ValueError(f"{context}[{i}]: expected [str, number] pair")
        name, weight = entry
        if not isinstance(name, str) or not isinstance(weight, (int, float)):
            raise ValueError(f"{context}[{i}]: expected [str, number], got {entry!r}")
        out.append((name, float(weight)))
    return out


def load_pattern_config(path: str | None = None) -> dict[str, Any]:
    """Return the parsed pattern config as validated Python objects.

    Raises :class:`ValueError` if the file is missing required keys or has
    malformed entries (fail loud — these drive inference across the repo).
    """
    resolved = path or _DEFAULT_PATH
    with open(resolved, encoding="utf-8") as f:
        raw = json.load(f)

    required = (
        "naming_convention_rules",
        "default_convention_confidence",
        "infrastructure_patterns",
        "file_role_patterns",
        "goal_role_patterns",
    )
    missing = [k for k in required if k not in raw]
    if missing:
        raise ValueError(f"patterns.json missing required keys: {missing}")

    naming_rules: dict[str, list[tuple[str, float]]] = {}
    for suffix, targets in raw["naming_convention_rules"].items():
        if not isinstance(suffix, str):
            raise ValueError(f"naming_convention_rules: non-str suffix {suffix!r}")
        naming_rules[suffix] = _tuple_pairs(targets, f"naming_convention_rules[{suffix!r}]")

    infra = _tuple_pairs(raw["infrastructure_patterns"], "infrastructure_patterns")

    file_roles = _tuple_pairs_str_str(raw["file_role_patterns"], "file_role_patterns")
    goal_roles = _tuple_pairs_str_str(raw["goal_role_patterns"], "goal_role_patterns")

    return {
        "naming_convention_rules": naming_rules,
        "default_convention_confidence": float(raw["default_convention_confidence"]),
        "infrastructure_patterns": infra,
        "file_role_patterns": tuple(file_roles),
        "goal_role_patterns": tuple(goal_roles),
    }


def _tuple_pairs_str_str(raw: Any, context: str) -> list[tuple[str, str]]:
    """Convert a JSON list of [str, str] pairs to list[tuple[str, str]]."""
    if not isinstance(raw, list):
        raise ValueError(f"{context}: expected list, got {type(raw).__name__}")
    out: list[tuple[str, str]] = []
    for i, entry in enumerate(raw):
        if not (isinstance(entry, list) and len(entry) == 2
                and isinstance(entry[0], str) and isinstance(entry[1], str)):
            raise ValueError(f"{context}[{i}]: expected [str, str] pair, got {entry!r}")
        out.append((entry[0], entry[1]))
    return out


_CONFIG: dict[str, Any] | None = None


def get_config() -> dict[str, Any]:
    """Return the cached pattern config (loaded on first access)."""
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = load_pattern_config()
    return _CONFIG
