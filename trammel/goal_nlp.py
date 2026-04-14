"""Goal text analysis: keyword extraction, intent detection, path parsing."""

from __future__ import annotations

import os
import re
from typing import Any

_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "must", "shall", "can",
    "that", "this", "these", "those", "it", "its", "not", "no", "all",
    "any", "each", "every", "some", "into", "about", "up", "out",
    "then", "than", "so", "very", "just", "also", "too", "only", "new",
})

_CREATION_VERBS = frozenset({
    "add", "create", "build", "implement", "introduce", "write",
    "make", "generate", "develop", "establish", "initialize", "scaffold",
    "set", "setup",
})

_REFACTOR_VERBS = frozenset({
    "refactor", "consolidate", "deduplicate", "dry", "simplify", "extract",
    "merge", "reorganize", "cleanup", "clean", "update", "modify", "edit",
    "fix", "rename", "migrate", "rewrite", "split", "reduce", "improve",
})

_CODE_EXT_PATTERN = (
    r"(?:py|js|mjs|cjs|ts|tsx|jsx|go|rs|java|kt|kts|"
    r"c|h|hpp|cpp|cc|cxx|cs|rb|php|sql|md|yaml|yml|json|toml)"
)


def _looks_like_rel_project_path(path: str) -> bool:
    """True if path looks like a relative project file path (conservative)."""
    p = path.strip().replace("\\", "/")
    if not p or ".." in p or p.startswith("/"):
        return False
    return "/" in p or (len(p) > 2 and "." in os.path.basename(p))


def _extract_paths_from_goal(goal: str) -> list[str]:
    """Parse explicit file paths from goal text (backticks, quotes, slash paths).

    Returns deduplicated relative paths normalized with forward slashes.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    ext = _CODE_EXT_PATTERN

    def _push(raw: str) -> None:
        p = raw.strip().replace("\\", "/")
        if not _looks_like_rel_project_path(p) or p in seen:
            return
        seen.add(p)
        ordered.append(p)

    for m in re.finditer(rf"`([^`]+\.{ext})`", goal, re.IGNORECASE):
        _push(m.group(1))
    for m in re.finditer(rf'["\']([^"\']+\.{ext})["\']', goal, re.IGNORECASE):
        _push(m.group(1))
    for m in re.finditer(
        rf"\b((?:[a-zA-Z0-9_.-]+/)+[a-zA-Z0-9_.-]+\.{ext})\b",
        goal,
        re.IGNORECASE,
    ):
        _push(m.group(1))

    return ordered


def _extract_goal_keywords(goal: str) -> set[str]:
    """Extract meaningful keywords from a goal, filtering stop words and verbs."""
    words = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', goal.lower())
    expanded: list[str] = []
    for w in words:
        parts = re.findall(r'[a-z]+|[A-Z][a-z]*', w)
        expanded.extend(p.lower() for p in parts)
    return {
        w for w in expanded
        if w not in _STOP_WORDS and w not in _CREATION_VERBS and len(w) > 2
    }


def _has_refactor_intent(goal: str) -> bool:
    """True when the goal reads as editing existing code rather than greenfield work."""
    words = set(re.findall(r"[a-z]+", goal.lower()))
    return bool(words & _REFACTOR_VERBS)


def _has_creation_intent(goal: str) -> bool:
    """Check if the goal implies creating new files/modules.

    Returns True if:
    - A creation verb is present in the goal, OR
    - The goal contains role-keywords (service, route, plugin, engine, etc.)
      that typically imply new file creation — unless the goal is clearly
      refactor/edit-oriented, in which case role keywords alone are ignored.
    """
    if set(goal.lower().split()) & _CREATION_VERBS:
        return True
    if _has_refactor_intent(goal):
        return False
    goal_lower = goal.lower()
    role_kw = {
        "service", "services", "route", "routes", "controller", "controllers",
        "handler", "handlers", "engine", "engines", "plugin", "plugins",
        "registry", "registries", "collector", "aggregator", "middleware",
        "model", "models", "repository", "repositories", "algorithm", "algorithms",
        "generator", "generators", "workflow", "marketplace", "pipeline",
    }
    words = set(re.findall(r'[a-z]+', goal_lower))
    return bool(words & role_kw)


def _keyword_variants(keywords: set[str]) -> set[str]:
    """Expand keywords with plural/singular variants for fuzzy matching."""
    variants = set(keywords)
    for kw in keywords:
        variants.add(kw + "s")
        variants.add(kw + "es")
        if kw.endswith("s"):
            variants.add(kw[:-1])
        if kw.endswith("es") and len(kw) > 2:
            variants.add(kw[:-2])
    return variants


def _matched_keywords(
    goal_keywords: set[str], candidate_words: set[str],
) -> set[str]:
    """Return which goal keywords match any candidate word (variants + substring + CamelCase).

    Uses three-tier matching:
    1. Exact match with plural/singular variants (original behavior)
    2. Substring containment: keyword appears inside candidate or vice versa
    3. CamelCase token overlap: 'workflowAutomation' matches {'workflow', 'automation'}
    """
    matched: set[str] = set()
    variants = _keyword_variants(goal_keywords)

    if variants & candidate_words:
        matched.update(kw for kw in goal_keywords if _keyword_variants({kw}) & candidate_words)

    all_goal_terms = variants | goal_keywords
    for kw in goal_keywords:
        kw_lc = kw.lower()
        for cw in candidate_words:
            cw_lc = cw.lower()
            if (len(kw_lc) >= 4 and kw_lc in cw_lc) or (len(cw_lc) >= 4 and cw_lc in kw_lc):
                matched.add(kw)

    return matched
