"""Optional project-local settings: .trammel.json and pyproject [tool.trammel] (stdlib only)."""

from __future__ import annotations

import json
import os
from typing import Any

def _read_trammel_json(project_root: str) -> dict[str, Any]:
    path = os.path.join(project_root, ".trammel.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def _read_pyproject_trammel(project_root: str) -> dict[str, Any]:
    path = os.path.join(project_root, "pyproject.toml")
    if not os.path.isfile(path):
        return {}
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        return {}
    try:
        with open(path, "rb") as fp:
            data = tomllib.load(fp)
    except (OSError, ValueError):
        return {}
    tool = data.get("tool")
    if not isinstance(tool, dict):
        return {}
    tr = tool.get("trammel")
    return tr if isinstance(tr, dict) else {}


def _normalize_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Keep only known keys with safe types."""
    out: dict[str, Any] = {}
    if isinstance(raw.get("default_scope"), str) and raw["default_scope"].strip():
        out["default_scope"] = raw["default_scope"].strip().replace("\\", "/")
    fk = raw.get("focus_keywords")
    if isinstance(fk, list):
        out["focus_keywords"] = [str(x).strip() for x in fk if str(x).strip()]
    fg = raw.get("focus_globs")
    if isinstance(fg, list):
        out["focus_globs"] = [str(x).strip() for x in fg if str(x).strip()]
    mf = raw.get("max_files")
    if isinstance(mf, int) and mf > 0:
        out["max_files"] = mf
    tc = raw.get("test_cmd")
    if isinstance(tc, list) and all(isinstance(x, str) for x in tc):
        out["test_cmd"] = list(tc)
    return out


def load_project_config(project_root: str) -> dict[str, Any]:
    """Merge `[tool.trammel]` from pyproject.toml with `.trammel.json` (JSON overrides)."""
    merged: dict[str, Any] = {}
    merged.update(_normalize_config(_read_pyproject_trammel(project_root)))
    merged.update(_normalize_config(_read_trammel_json(project_root)))
    return merged


def merge_focus_keywords(
    goal_keywords: set[str],
    explicit: list[str] | None,
    config: dict[str, Any],
) -> set[str]:
    """Union goal keywords with API and config `focus_keywords`."""
    extra = list(explicit or []) + list(config.get("focus_keywords") or [])
    if not extra:
        return goal_keywords
    merged = set(goal_keywords)
    for w in extra:
        w = w.strip().lower()
        if len(w) > 2:
            merged.add(w)
    return merged


def merge_focus_globs(
    globs: list[str] | None,
    config: dict[str, Any],
) -> list[str]:
    """Combine API `focus_globs` with config (API first, then config for extras)."""
    out: list[str] = []
    seen: set[str] = set()
    for g in (globs or []) + list(config.get("focus_globs") or []):
        g = g.strip()
        if g and g not in seen:
            seen.add(g)
            out.append(g)
    return out


def effective_max_files(
    arg: int | None,
    config: dict[str, Any],
) -> int | None:
    """Prefer explicit decompose arg over config."""
    if arg is not None and arg > 0:
        return arg
    mf = config.get("max_files")
    return mf if isinstance(mf, int) and mf > 0 else None
