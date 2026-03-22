"""Language-specific analyzers: symbol collection, import analysis, test discovery."""

from __future__ import annotations

import ast
import json
import os
import re
import sys
from typing import Any, Protocol

from .utils import _is_ignored_dir


class LanguageAnalyzer(Protocol):
    """Interface for language-specific code analysis."""

    name: str
    extensions: tuple[str, ...]

    def collect_symbols(self, project_root: str) -> dict[str, list[str]]: ...
    def analyze_imports(self, project_root: str) -> dict[str, list[str]]: ...
    def pick_test_cmd(self, project_root: str) -> list[str]: ...
    def error_patterns(self) -> list[tuple[str, str, str]]: ...


# ── Python ───────────────────────────────────────────────────────────────────

class PythonAnalyzer:
    """Python code analysis via stdlib AST."""

    name = "python"
    extensions = (".py",)

    def collect_symbols(self, project_root: str) -> dict[str, list[str]]:
        """Collect function/class symbol names grouped by relative file path."""
        symbols: dict[str, list[str]] = {}
        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if not _is_ignored_dir(d)]
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                path = os.path.join(root, fname)
                rel = os.path.relpath(path, project_root)
                try:
                    with open(path, encoding="utf-8", errors="replace") as fp:
                        tree = ast.parse(fp.read(), filename=path)
                except (OSError, SyntaxError):
                    continue
                names = [
                    node.name
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                ]
                if names:
                    symbols[rel] = names
        return symbols

    def analyze_imports(self, project_root: str) -> dict[str, list[str]]:
        """Build file -> [imported files] graph via AST (project-internal only)."""
        modules = self._catalog_modules(project_root)
        module_set = set(modules)
        graph: dict[str, list[str]] = {}

        for mod, rel in modules.items():
            path = os.path.join(project_root, rel)
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    tree = ast.parse(f.read(), filename=path)
            except (OSError, SyntaxError):
                continue

            deps: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self._resolve_import(alias.name, module_set, modules, deps)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    self._resolve_import(node.module, module_set, modules, deps)

            deps.discard(rel)
            if deps:
                graph[rel] = sorted(deps)

        return graph

    def pick_test_cmd(self, project_root: str) -> list[str]:
        exe = sys.executable
        tests_dir = os.path.join(project_root, "tests")
        start = "tests" if os.path.isdir(tests_dir) else "."
        return [exe, "-m", "unittest", "discover", "-q", "-s", start, "-p", "test_*.py"]

    def error_patterns(self) -> list[tuple[str, str, str]]:
        return [
            ("ImportError", "import_error", "Check import paths and module dependencies"),
            ("ModuleNotFoundError", "import_error", "Check import paths and module dependencies"),
            ("AttributeError", "attribute_error", "Verify referenced attributes exist on the object"),
            ("SyntaxError", "syntax_error", "Fix Python syntax in the referenced file"),
            ("TypeError", "type_error", "Check argument types and function signatures"),
            ("NameError", "name_error", "Check that referenced names are defined in scope"),
            ("AssertionError", "assertion_error", "Test assertion failed — check expected vs actual"),
            ("FAIL", "test_failure", "One or more test assertions failed"),
        ]

    @staticmethod
    def _catalog_modules(project_root: str) -> dict[str, str]:
        modules: dict[str, str] = {}
        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if not _is_ignored_dir(d)]
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                path = os.path.join(root, fname)
                rel = os.path.relpath(path, project_root)
                mod = rel.replace(os.sep, ".").removesuffix(".py")
                if mod.endswith(".__init__"):
                    mod = mod.removesuffix(".__init__")
                modules[mod] = rel
        return modules

    @staticmethod
    def _resolve_import(
        name: str, module_set: set[str], modules: dict[str, str], deps: set[str],
    ) -> None:
        if name in module_set:
            deps.add(modules[name])
            return
        parts = name.split(".")
        for i in range(len(parts), 0, -1):
            prefix = ".".join(parts[:i])
            if prefix in module_set:
                deps.add(modules[prefix])
                return


# ── TypeScript / JavaScript ──────────────────────────────────────────────────

_TS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")

_TS_SYMBOL_RE = re.compile(
    r"(?:^|\n)\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?"
    r"(?:function\*?\s+(\w+)|class\s+(\w+))"
    r"|(?:^|\n)\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*="
    r"\s*(?:async\s*)?\(",
)

_TS_IMPORT_RE = re.compile(
    r"""(?:import\s+.*?\s+from|import)\s+['"](\.[^'"]+)['"]"""
    r"""|require\(\s*['"](\.[^'"]+)['"]\s*\)""",
)


class TypeScriptAnalyzer:
    """TypeScript/JavaScript analysis via regex (stdlib-only, no Node.js required)."""

    name = "typescript"
    extensions = _TS_EXTENSIONS

    def collect_symbols(self, project_root: str) -> dict[str, list[str]]:
        symbols: dict[str, list[str]] = {}
        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if not _is_ignored_dir(d)]
            for fname in files:
                if not any(fname.endswith(ext) for ext in _TS_EXTENSIONS):
                    continue
                path = os.path.join(root, fname)
                rel = os.path.relpath(path, project_root)
                try:
                    with open(path, encoding="utf-8", errors="replace") as fp:
                        src = fp.read()
                except OSError:
                    continue
                names: list[str] = []
                for m in _TS_SYMBOL_RE.finditer(src):
                    name = m.group(1) or m.group(2) or m.group(3)
                    if name and name not in names:
                        names.append(name)
                if names:
                    symbols[rel] = names
        return symbols

    def analyze_imports(self, project_root: str) -> dict[str, list[str]]:
        file_set = self._collect_files(project_root)
        graph: dict[str, list[str]] = {}

        for rel in file_set:
            path = os.path.join(project_root, rel)
            try:
                with open(path, encoding="utf-8", errors="replace") as fp:
                    src = fp.read()
            except OSError:
                continue

            deps: set[str] = set()
            for m in _TS_IMPORT_RE.finditer(src):
                import_path = m.group(1) or m.group(2)
                if not import_path:
                    continue
                resolved = self._resolve_ts_path(rel, import_path, file_set)
                if resolved and resolved != rel:
                    deps.add(resolved)

            if deps:
                graph[rel] = sorted(deps)

        return graph

    def pick_test_cmd(self, project_root: str) -> list[str]:
        pkg_json = os.path.join(project_root, "package.json")
        if os.path.isfile(pkg_json):
            try:
                with open(pkg_json, encoding="utf-8") as fp:
                    pkg = json.load(fp)
                if pkg.get("scripts", {}).get("test"):
                    return ["npm", "test"]
            except (OSError, json.JSONDecodeError):
                pass
        return ["npx", "jest", "--passWithNoTests"]

    def error_patterns(self) -> list[tuple[str, str, str]]:
        return [
            ("TypeError", "type_error", "Check argument types"),
            ("ReferenceError", "reference_error", "Check that referenced names exist"),
            ("SyntaxError", "syntax_error", "Fix syntax in the referenced file"),
            ("Cannot find module", "import_error", "Check import paths and module names"),
            ("FAIL", "test_failure", "One or more test assertions failed"),
            ("Error:", "runtime_error", "Check the error details"),
        ]

    @staticmethod
    def _collect_files(project_root: str) -> set[str]:
        files: set[str] = set()
        for root, dirs, fnames in os.walk(project_root):
            dirs[:] = [d for d in dirs if not _is_ignored_dir(d)]
            for fname in fnames:
                if any(fname.endswith(ext) for ext in _TS_EXTENSIONS):
                    files.add(os.path.relpath(os.path.join(root, fname), project_root))
        return files

    @staticmethod
    def _resolve_ts_path(importing_file: str, import_path: str, file_set: set[str]) -> str | None:
        base = os.path.normpath(os.path.join(os.path.dirname(importing_file), import_path))
        for ext in _TS_EXTENSIONS:
            candidate = base + ext
            if candidate in file_set:
                return candidate
        for ext in _TS_EXTENSIONS:
            candidate = os.path.join(base, f"index{ext}")
            if candidate in file_set:
                return candidate
        if base in file_set:
            return base
        return None


# ── Registry + detection ─────────────────────────────────────────────────────

_ANALYZER_REGISTRY: dict[str, type] = {
    "python": PythonAnalyzer,
    "typescript": TypeScriptAnalyzer,
    "javascript": TypeScriptAnalyzer,
}


def get_analyzer(name: str) -> LanguageAnalyzer:
    """Get an analyzer by language name. Raises KeyError if unknown."""
    cls = _ANALYZER_REGISTRY[name]
    return cls()


def detect_language(project_root: str) -> LanguageAnalyzer:
    """Auto-detect dominant language by counting file extensions."""
    py_count = 0
    ts_count = 0
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if not _is_ignored_dir(d)]
        for fname in files:
            if fname.endswith(".py"):
                py_count += 1
            elif any(fname.endswith(ext) for ext in _TS_EXTENSIONS):
                ts_count += 1
    if ts_count > py_count:
        return TypeScriptAnalyzer()
    return PythonAnalyzer()
