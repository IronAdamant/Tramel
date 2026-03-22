"""Language-specific analyzers: symbol collection, import analysis, test discovery."""

from __future__ import annotations

import ast
import json
import os
import re
import sys
from typing import Any, Callable, Protocol

from .utils import _ERROR_PATTERNS, _is_ignored_dir


def _collect_symbols_regex(
    project_root: str,
    extensions: tuple[str, ...],
    patterns: list[re.Pattern[str]],
    preprocess: Callable[[str], str] | None = None,
) -> dict[str, list[str]]:
    """Shared symbol collection for regex-based analyzers."""
    symbols: dict[str, list[str]] = {}
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if not _is_ignored_dir(d)]
        for fname in files:
            if not any(fname.endswith(ext) for ext in extensions):
                continue
            path = os.path.join(root, fname)
            rel = os.path.relpath(path, project_root)
            try:
                with open(path, encoding="utf-8", errors="replace") as fp:
                    src = fp.read()
            except OSError:
                continue
            if preprocess:
                src = preprocess(src)
            names: list[str] = []
            for pat in patterns:
                for m in pat.finditer(src):
                    name = m.group(1)
                    if name and name not in names:
                        names.append(name)
            if names:
                symbols[rel] = names
    return symbols


_JS_COMMENT_RE = re.compile(r"//[^\n]*|/\*[\s\S]*?\*/")


def _strip_js_comments(src: str) -> str:
    """Remove JS/TS line and block comments."""
    return _JS_COMMENT_RE.sub("", src)


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
        return _ERROR_PATTERNS

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

_TS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mts", ".mjs")

_TS_SYMBOL_PATTERNS: list[re.Pattern[str]] = [
    # function/generator (export/default/async optional)
    re.compile(r"(?:^|\n)\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?function\*?\s+(\w+)"),
    # class (abstract, decorated)
    re.compile(r"(?:^|\n)\s*(?:@\w+[^\n]*\n\s*)*(?:export\s+(?:default\s+)?)?(?:abstract\s+)?class\s+(\w+)"),
    # interface
    re.compile(r"(?:^|\n)\s*(?:export\s+(?:default\s+)?)?interface\s+(\w+)"),
    # enum (including const enum)
    re.compile(r"(?:^|\n)\s*(?:export\s+(?:default\s+)?)?(?:const\s+)?enum\s+(\w+)"),
    # type alias
    re.compile(r"(?:^|\n)\s*(?:export\s+)?type\s+(\w+)\s*[=<]"),
    # arrow function assignment
    re.compile(r"(?:^|\n)\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\("),
    # function expression assignment
    re.compile(r"(?:^|\n)\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?function"),
    # namespace
    re.compile(r"(?:^|\n)\s*(?:export\s+)?namespace\s+(\w+)"),
]

# Relative imports (start with .)
_TS_IMPORT_RE = re.compile(
    r"""import\s+.*?\s+from\s+['"](\.[^'"]+)['"]"""         # import X from './path'
    r"""|import\s+['"](\.[^'"]+)['"]"""                       # import './path'
    r"""|require\(\s*['"](\.[^'"]+)['"]\s*\)"""               # require('./path')
    r"""|export\s+\{[^}]*\}\s+from\s+['"](\.[^'"]+)['"]"""  # export { X } from './path'
    r"""|export\s+\*\s+from\s+['"](\.[^'"]+)['"]"""          # export * from './path'
    r"""|export\s+type\s+\{[^}]*\}\s+from\s+['"](\.[^'"]+)['"]"""  # export type { X } from
    r"""|import\(\s*['"](\.[^'"]+)['"]\s*\)""",               # import('./path') dynamic
)

# All imports (for alias resolution — matches any from/require path)
_TS_ALIAS_IMPORT_RE = re.compile(
    r"""(?:import|export)\s+.*?\s+from\s+['"]([^'"./][^'"]*?)['"]"""
    r"""|require\(\s*['"]([^'"./][^'"]*?)['"]\s*\)"""
    r"""|import\(\s*['"]([^'"./][^'"]*?)['"]\s*\)""",
)


class TypeScriptAnalyzer:
    """TypeScript/JavaScript analysis via regex (stdlib-only, no Node.js required)."""

    name = "typescript"
    extensions = _TS_EXTENSIONS

    def collect_symbols(self, project_root: str) -> dict[str, list[str]]:
        return _collect_symbols_regex(
            project_root, _TS_EXTENSIONS, _TS_SYMBOL_PATTERNS, _strip_js_comments,
        )

    def analyze_imports(self, project_root: str) -> dict[str, list[str]]:
        file_set = self._collect_files(project_root)
        base_url, aliases = self._read_ts_path_aliases(project_root)
        graph: dict[str, list[str]] = {}

        for rel in file_set:
            path = os.path.join(project_root, rel)
            try:
                with open(path, encoding="utf-8", errors="replace") as fp:
                    src = _strip_js_comments(fp.read())
            except OSError:
                continue

            deps: set[str] = set()

            # Relative imports
            for m in _TS_IMPORT_RE.finditer(src):
                import_path = next((g for g in m.groups() if g is not None), None)
                if not import_path:
                    continue
                resolved = self._resolve_ts_path(rel, import_path, file_set)
                if resolved and resolved != rel:
                    deps.add(resolved)

            # Alias imports (only if aliases configured)
            if aliases:
                for m in _TS_ALIAS_IMPORT_RE.finditer(src):
                    import_path = next((g for g in m.groups() if g is not None), None)
                    if not import_path:
                        continue
                    resolved = self._resolve_alias(
                        import_path, file_set, base_url, aliases,
                    )
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

    @staticmethod
    def _read_ts_path_aliases(project_root: str) -> tuple[str, dict[str, str]]:
        """Read baseUrl and paths from tsconfig.json."""
        tsconfig = os.path.join(project_root, "tsconfig.json")
        base_url = "."
        aliases: dict[str, str] = {}
        if not os.path.isfile(tsconfig):
            return base_url, aliases
        try:
            with open(tsconfig, encoding="utf-8") as fp:
                config = json.load(fp)
        except (OSError, json.JSONDecodeError):
            return base_url, aliases
        compiler = config.get("compilerOptions", {})
        base_url = compiler.get("baseUrl", ".")
        for alias, targets in compiler.get("paths", {}).items():
            if not targets or not isinstance(targets, list):
                continue
            clean_alias = alias.removesuffix("/*")
            clean_target = targets[0].removesuffix("/*")
            aliases[clean_alias] = clean_target
        return base_url, aliases

    @staticmethod
    def _resolve_alias(
        import_path: str, file_set: set[str],
        base_url: str, aliases: dict[str, str],
    ) -> str | None:
        """Resolve an alias import (e.g., @/utils) to a project file."""
        for alias_prefix, real_prefix in aliases.items():
            if import_path == alias_prefix or import_path.startswith(alias_prefix + "/"):
                remainder = import_path[len(alias_prefix):]
                resolved_base = os.path.normpath(
                    os.path.join(base_url, real_prefix + remainder),
                )
                for ext in _TS_EXTENSIONS:
                    candidate = resolved_base + ext
                    if candidate in file_set:
                        return candidate
                for ext in _TS_EXTENSIONS:
                    candidate = os.path.join(resolved_base, f"index{ext}")
                    if candidate in file_set:
                        return candidate
                if resolved_base in file_set:
                    return resolved_base
                break
        return None


# ── Go ────────────────────────────────────────────────────────────────────────

_GO_EXTENSIONS = (".go",)

_GO_SYMBOL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:^|\n)\s*func\s+(?:\([^)]+\)\s+)?(\w+)"),
    re.compile(r"(?:^|\n)\s*type\s+(\w+)\s+"),
    re.compile(r"(?:^|\n)\s*(?:var|const)\s+(\w+)\s"),
]

_GO_IMPORT_SINGLE_RE = re.compile(r'import\s+"([^"]+)"')
_GO_IMPORT_BLOCK_RE = re.compile(r"import\s*\((.*?)\)", re.DOTALL)
_GO_IMPORT_LINE_RE = re.compile(r'"([^"]+)"')
_GO_MOD_RE = re.compile(r"module\s+(\S+)")


class GoAnalyzer:
    """Go code analysis via regex (stdlib-only)."""

    name = "go"
    extensions = _GO_EXTENSIONS

    def collect_symbols(self, project_root: str) -> dict[str, list[str]]:
        return _collect_symbols_regex(project_root, _GO_EXTENSIONS, _GO_SYMBOL_PATTERNS)

    def analyze_imports(self, project_root: str) -> dict[str, list[str]]:
        module_path = self._read_go_mod(project_root)
        if not module_path:
            return {}
        prefix = module_path + "/"
        dir_files: dict[str, list[str]] = {}
        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if not _is_ignored_dir(d)]
            go_files = [f for f in files if f.endswith(".go") and not f.endswith("_test.go")]
            if go_files:
                rel_dir = os.path.relpath(root, project_root)
                if rel_dir == ".":
                    rel_dir = ""
                dir_files[rel_dir] = [
                    os.path.relpath(os.path.join(root, f), project_root) for f in go_files
                ]
        graph: dict[str, list[str]] = {}
        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if not _is_ignored_dir(d)]
            for fname in files:
                if not fname.endswith(".go"):
                    continue
                path = os.path.join(root, fname)
                rel = os.path.relpath(path, project_root)
                try:
                    with open(path, encoding="utf-8", errors="replace") as fp:
                        src = fp.read()
                except OSError:
                    continue
                deps: set[str] = set()
                for imp in self._extract_imports(src):
                    if not imp.startswith(prefix):
                        continue
                    rel_pkg = imp[len(prefix):]
                    for dep_file in dir_files.get(rel_pkg, []):
                        if dep_file != rel:
                            deps.add(dep_file)
                if deps:
                    graph[rel] = sorted(deps)
        return graph

    def pick_test_cmd(self, project_root: str) -> list[str]:
        return ["go", "test", "./..."]

    def error_patterns(self) -> list[tuple[str, str, str]]:
        return [
            ("cannot find package", "import_error", "Check import paths"),
            ("undefined:", "name_error", "Check that names are defined"),
            ("syntax error", "syntax_error", "Fix Go syntax"),
            ("FAIL", "test_failure", "One or more tests failed"),
        ]

    @staticmethod
    def _read_go_mod(project_root: str) -> str | None:
        go_mod = os.path.join(project_root, "go.mod")
        if not os.path.isfile(go_mod):
            return None
        try:
            with open(go_mod, encoding="utf-8") as fp:
                m = _GO_MOD_RE.search(fp.read())
                return m.group(1) if m else None
        except OSError:
            return None

    @staticmethod
    def _extract_imports(src: str) -> list[str]:
        imports: list[str] = []
        for m in _GO_IMPORT_SINGLE_RE.finditer(src):
            imports.append(m.group(1))
        for block in _GO_IMPORT_BLOCK_RE.finditer(src):
            for m in _GO_IMPORT_LINE_RE.finditer(block.group(1)):
                imports.append(m.group(1))
        return imports


# ── Rust ──────────────────────────────────────────────────────────────────────

_RUST_EXTENSIONS = (".rs",)

_RUST_SYMBOL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:^|\n)\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+(\w+)"),
    re.compile(r"(?:^|\n)\s*(?:pub(?:\([^)]*\))?\s+)?struct\s+(\w+)"),
    re.compile(r"(?:^|\n)\s*(?:pub(?:\([^)]*\))?\s+)?enum\s+(\w+)"),
    re.compile(r"(?:^|\n)\s*(?:pub(?:\([^)]*\))?\s+)?trait\s+(\w+)"),
    re.compile(r"(?:^|\n)\s*impl(?:<[^>]*>)?\s+(\w+)"),
    re.compile(r"(?:^|\n)\s*(?:pub(?:\([^)]*\))?\s+)?type\s+(\w+)"),
]


class RustAnalyzer:
    """Rust code analysis via regex (stdlib-only)."""

    name = "rust"
    extensions = _RUST_EXTENSIONS

    def collect_symbols(self, project_root: str) -> dict[str, list[str]]:
        return _collect_symbols_regex(project_root, _RUST_EXTENSIONS, _RUST_SYMBOL_PATTERNS)

    def analyze_imports(self, project_root: str) -> dict[str, list[str]]:
        file_set: set[str] = set()
        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if not _is_ignored_dir(d)]
            for fname in files:
                if fname.endswith(".rs"):
                    file_set.add(os.path.relpath(os.path.join(root, fname), project_root))
        graph: dict[str, list[str]] = {}
        for rel in file_set:
            path = os.path.join(project_root, rel)
            try:
                with open(path, encoding="utf-8", errors="replace") as fp:
                    src = fp.read()
            except OSError:
                continue
            deps: set[str] = set()
            for m in re.finditer(r"use\s+crate::(\w+(?:::\w+)*)", src):
                mod_path = m.group(1).split("::")[0]
                for candidate in (mod_path + ".rs", os.path.join(mod_path, "mod.rs")):
                    if candidate in file_set and candidate != rel:
                        deps.add(candidate)
            file_dir = os.path.dirname(rel)
            for m in re.finditer(r"(?:^|\n)\s*mod\s+(\w+)\s*;", src):
                mod_name = m.group(1)
                base = file_dir if file_dir else ""
                for candidate in (
                    os.path.join(base, mod_name + ".rs") if base else mod_name + ".rs",
                    os.path.join(base, mod_name, "mod.rs") if base else os.path.join(mod_name, "mod.rs"),
                ):
                    if candidate in file_set and candidate != rel:
                        deps.add(candidate)
            if deps:
                graph[rel] = sorted(deps)
        return graph

    def pick_test_cmd(self, project_root: str) -> list[str]:
        return ["cargo", "test"]

    def error_patterns(self) -> list[tuple[str, str, str]]:
        return [
            ("cannot find", "import_error", "Check use/mod paths"),
            ("expected", "syntax_error", "Fix Rust syntax"),
            ("test result: FAILED", "test_failure", "One or more tests failed"),
            ("error[E", "compile_error", "Check compiler error code"),
        ]


# ── Registry + detection ─────────────────────────────────────────────────────

_ANALYZER_REGISTRY: dict[str, type] = {
    "python": PythonAnalyzer,
    "typescript": TypeScriptAnalyzer,
    "javascript": TypeScriptAnalyzer,
    "go": GoAnalyzer,
    "rust": RustAnalyzer,
}


def get_analyzer(name: str) -> LanguageAnalyzer:
    """Get an analyzer by language name. Raises KeyError if unknown."""
    cls = _ANALYZER_REGISTRY[name]
    return cls()


def detect_language(project_root: str) -> LanguageAnalyzer:
    """Auto-detect dominant language by counting file extensions."""
    counts: dict[str, int] = {"python": 0, "typescript": 0, "go": 0, "rust": 0}
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if not _is_ignored_dir(d)]
        for fname in files:
            if fname.endswith(".py"):
                counts["python"] += 1
            elif any(fname.endswith(ext) for ext in _TS_EXTENSIONS):
                counts["typescript"] += 1
            elif fname.endswith(".go"):
                counts["go"] += 1
            elif fname.endswith(".rs"):
                counts["rust"] += 1
    best = max(counts, key=lambda k: counts[k])
    if counts[best] == 0:
        return PythonAnalyzer()
    return get_analyzer(best)
