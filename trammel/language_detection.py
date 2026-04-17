"""Project language auto-detection.

Split out of :mod:`analyzers` to keep that module under the project's
500-LOC target. Priority order (highest first):

1. Explicit ``language`` in ``.trammel.json``
2. Unambiguous config files (``Cargo.toml``, ``go.mod``, ``pyproject.toml``
   with a ``[project]`` table, etc.)
3. Source-file extension count

Functions in this module are re-exported through :mod:`analyzers` so
``from trammel.analyzers import detect_language`` keeps working.
"""

from __future__ import annotations

import json
import os

from .analyzer_engine import CppAnalyzer, JavaAnalyzer
from .utils import _is_ignored_dir


def _detect_from_config(project_root: str) -> str | None:
    """Detect language from project config files (more reliable than extension counting).

    Priority: unambiguous config files first, then language-specific, then ambiguous.
    """
    def has(f: str) -> bool:
        return os.path.isfile(os.path.join(project_root, f))
    if has("Cargo.toml"):
        return "rust"
    if has("go.mod"):
        return "go"
    if has("Package.swift"):
        return "swift"
    if has("build.zig"):
        return "zig"
    if has("pubspec.yaml"):
        return "dart"
    if has("tsconfig.json"):
        return "typescript"
    if has("CMakeLists.txt") or has("SConstruct"):
        return "cpp"
    try:
        csharp_match = any(f.endswith((".csproj", ".sln")) for f in os.listdir(project_root))
    except OSError:
        csharp_match = False
    if csharp_match:
        return "csharp"
    if has("setup.py") or has("setup.cfg"):
        return "python"
    if has("pyproject.toml"):
        try:
            with open(os.path.join(project_root, "pyproject.toml"), encoding="utf-8") as fp:
                if "[project]" in fp.read():
                    return "python"
        except OSError:
            pass
    if has("Gemfile"):
        return "ruby"
    if has("composer.json"):
        return "php"
    if has("package.json"):
        return "javascript"
    for gradle in ("build.gradle", "build.gradle.kts", "pom.xml"):
        if has(gradle):
            return "java"
    return None


_LANG_EXTENSIONS: list[tuple[str, tuple[str, ...]]] = [
    ("python", (".py",)),
    ("typescript", (".ts", ".tsx", ".mts")),
    ("javascript", (".js", ".jsx", ".mjs")),
    ("go", (".go",)),
    ("rust", (".rs",)),
    ("cpp", CppAnalyzer.extensions),
    ("java", JavaAnalyzer.extensions),
    ("csharp", (".cs",)),
    ("ruby", (".rb",)),
    ("php", (".php",)),
    ("swift", (".swift",)),
    ("dart", (".dart",)),
    ("zig", (".zig",)),
]


def _detect_from_trammel_config(project_root: str) -> str | None:
    """Check for explicit language override in ``.trammel.json`` (highest priority)."""
    from .analyzers import _ANALYZER_REGISTRY  # lazy; analyzers.py imports this module
    config_path = os.path.join(project_root, ".trammel.json")
    if not os.path.isfile(config_path):
        return None
    try:
        with open(config_path, encoding="utf-8") as fp:
            config = json.load(fp)
        lang = config.get("language")
        if isinstance(lang, str) and lang in _ANALYZER_REGISTRY:
            return lang
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return None


def detect_language(project_root: str):
    """Auto-detect project language from config files, falling back to extension counting."""
    from .analyzers import PythonAnalyzer, get_analyzer  # lazy
    explicit = _detect_from_trammel_config(project_root)
    if explicit:
        return get_analyzer(explicit)
    config_lang = _detect_from_config(project_root)
    if config_lang:
        return get_analyzer(config_lang)
    counts: dict[str, int] = {lang: 0 for lang, _ in _LANG_EXTENSIONS}
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if not _is_ignored_dir(d)]
        for fname in files:
            for lang, exts in _LANG_EXTENSIONS:
                if fname.endswith(exts):
                    counts[lang] += 1
                    break
    best = max(counts, key=lambda k: counts[k])
    if counts[best] == 0:
        return PythonAnalyzer()
    return get_analyzer(best)
