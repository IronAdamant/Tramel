"""Extended language analyzers: Go, Rust, C/C++, Java/Kotlin.

Separated from analyzers.py to keep each module under 500 LOC.
These are re-exported by analyzers.py and registered in its analyzer registry.
"""

from __future__ import annotations

import os
import re

from .utils import (
    _collect_project_files, _collect_symbols_regex,
    _collect_typed_symbols_regex, _is_ignored_dir, _strip_c_comments,
)


# ── Go ────────────────────────────────────────────────────────────────────────

_GO_EXTENSIONS = (".go",)

_GO_SYMBOL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:^|\n)\s*func\s+(?:\([^)]+\)\s+)?(\w+)"),
    re.compile(r"(?:^|\n)\s*type\s+(\w+)\s+"),
    re.compile(r"(?:^|\n)\s*(?:var|const)\s+(\w+)\s"),
]

_GO_TYPED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:^|\n)\s*func\s+(?:\([^)]+\)\s+)?(\w+)"), "function"),
    (re.compile(r"(?:^|\n)\s*type\s+(\w+)\s+struct"), "struct"),
    (re.compile(r"(?:^|\n)\s*type\s+(\w+)\s+interface"), "interface"),
    (re.compile(r"(?:^|\n)\s*type\s+(\w+)\s+(?!struct|interface)"), "type"),
    (re.compile(r"(?:^|\n)\s*const\s+(\w+)\s"), "constant"),
    (re.compile(r"(?:^|\n)\s*var\s+(\w+)\s"), "variable"),
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
        return _collect_symbols_regex(project_root, _GO_EXTENSIONS, _GO_SYMBOL_PATTERNS, _strip_c_comments)

    def collect_typed_symbols(self, project_root: str) -> dict[str, list[tuple[str, str]]]:
        return _collect_typed_symbols_regex(project_root, _GO_EXTENSIONS, _GO_TYPED_PATTERNS, _strip_c_comments)

    def analyze_imports(self, project_root: str) -> dict[str, list[str]]:
        module_path, go_mod_dir = self._read_go_mod(project_root)
        if not module_path:
            return {}
        # Account for scope: if go.mod is above project_root, include the offset
        scope_rel = os.path.relpath(project_root, go_mod_dir)
        if scope_rel == ".":
            prefix = module_path + "/"
        else:
            prefix = module_path + "/" + scope_rel.replace(os.sep, "/") + "/"
        # Single walk: collect package dir->files mapping and read sources together
        dir_files: dict[str, list[str]] = {}
        file_sources: dict[str, str] = {}
        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if not _is_ignored_dir(d)]
            rel_dir = os.path.relpath(root, project_root)
            if rel_dir == ".":
                rel_dir = ""
            go_files_in_dir: list[str] = []
            for fname in files:
                if not fname.endswith(".go"):
                    continue
                path = os.path.join(root, fname)
                rel = os.path.relpath(path, project_root)
                if not fname.endswith("_test.go"):
                    go_files_in_dir.append(rel)
                try:
                    with open(path, encoding="utf-8", errors="replace") as fp:
                        file_sources[rel] = fp.read()
                except OSError:
                    continue
            if go_files_in_dir:
                dir_files[rel_dir] = go_files_in_dir
        graph: dict[str, list[str]] = {}
        for rel, src in file_sources.items():
            deps: set[str] = set()
            for imp in self._extract_imports(_strip_c_comments(src)):
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
    def _read_go_mod(project_root: str) -> tuple[str | None, str]:
        """Find and read go.mod, walking up parent directories for scoped analysis.

        Returns (module_path, go_mod_directory).
        """
        candidate = os.path.abspath(project_root)
        for _ in range(20):  # safety limit
            go_mod = os.path.join(candidate, "go.mod")
            if os.path.isfile(go_mod):
                try:
                    with open(go_mod, encoding="utf-8") as fp:
                        m = _GO_MOD_RE.search(fp.read())
                        return (m.group(1), candidate) if m else (None, candidate)
                except OSError:
                    return None, candidate
            parent = os.path.dirname(candidate)
            if parent == candidate:
                break
            candidate = parent
        return None, project_root

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

_RUST_TYPED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:^|\n)\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+(\w+)"), "function"),
    (re.compile(r"(?:^|\n)\s*(?:pub(?:\([^)]*\))?\s+)?struct\s+(\w+)"), "struct"),
    (re.compile(r"(?:^|\n)\s*(?:pub(?:\([^)]*\))?\s+)?enum\s+(\w+)"), "enum"),
    (re.compile(r"(?:^|\n)\s*(?:pub(?:\([^)]*\))?\s+)?trait\s+(\w+)"), "trait"),
    (re.compile(r"(?:^|\n)\s*impl(?:<(?:[^<>]|<[^<>]*>)*>)?\s+(\w+)"), "impl"),
    (re.compile(r"(?:^|\n)\s*(?:pub(?:\([^)]*\))?\s+)?type\s+(\w+)"), "type_alias"),
]

_RUST_SYMBOL_PATTERNS: list[re.Pattern[str]] = [p for p, _ in _RUST_TYPED_PATTERNS]


class RustAnalyzer:
    """Rust code analysis via regex (stdlib-only)."""

    name = "rust"
    extensions = _RUST_EXTENSIONS

    def collect_symbols(self, project_root: str) -> dict[str, list[str]]:
        return _collect_symbols_regex(project_root, _RUST_EXTENSIONS, _RUST_SYMBOL_PATTERNS, _strip_c_comments)

    def collect_typed_symbols(self, project_root: str) -> dict[str, list[tuple[str, str]]]:
        return _collect_typed_symbols_regex(project_root, _RUST_EXTENSIONS, _RUST_TYPED_PATTERNS, _strip_c_comments)

    def analyze_imports(self, project_root: str) -> dict[str, list[str]]:
        file_set = _collect_project_files(project_root, _RUST_EXTENSIONS)
        workspace_crates = self._read_cargo_crates(project_root)
        graph: dict[str, list[str]] = {}
        for rel in file_set:
            path = os.path.join(project_root, rel)
            try:
                with open(path, encoding="utf-8", errors="replace") as fp:
                    src = _strip_c_comments(fp.read())
            except OSError:
                continue
            deps: set[str] = set()
            # use crate::module
            for m in re.finditer(r"use\s+crate::(\w+(?:::\w+)*)", src):
                self._resolve_rust_mod(m.group(1).split("::")[0], "", file_set, deps)
            # use super::module (parent module)
            file_dir = os.path.dirname(rel)
            for m in re.finditer(r"use\s+super::(\w+(?:::\w+)*)", src):
                parent = os.path.dirname(file_dir) if file_dir else ""
                self._resolve_rust_mod(m.group(1).split("::")[0], parent, file_set, deps)
            # use self::module (current module)
            for m in re.finditer(r"use\s+self::(\w+(?:::\w+)*)", src):
                self._resolve_rust_mod(m.group(1).split("::")[0], file_dir, file_set, deps)
            # use workspace_crate::module
            for crate_name, crate_dir in workspace_crates.items():
                for m in re.finditer(rf"use\s+{re.escape(crate_name)}::(\w+(?:::\w+)*)", src):
                    mod_path = m.group(1).split("::")[0]
                    self._resolve_rust_mod(mod_path, crate_dir, file_set, deps)
            # mod declarations
            for m in re.finditer(r"(?:^|\n)\s*mod\s+(\w+)\s*;", src):
                self._resolve_rust_mod(m.group(1), file_dir, file_set, deps)
            deps.discard(rel)
            if deps:
                graph[rel] = sorted(deps)
        return graph

    @staticmethod
    def _resolve_rust_mod(
        mod_name: str, base: str, file_set: set[str], deps: set[str],
    ) -> None:
        """Resolve a Rust module name to file paths and add to deps."""
        for candidate in (
            os.path.join(base, mod_name + ".rs") if base else mod_name + ".rs",
            os.path.join(base, mod_name, "mod.rs") if base else os.path.join(mod_name, "mod.rs"),
        ):
            if candidate in file_set:
                deps.add(candidate)

    @staticmethod
    def _read_cargo_crates(project_root: str) -> dict[str, str]:
        """Read Cargo.toml for workspace member crate names mapped to their src dirs."""
        cargo = os.path.join(project_root, "Cargo.toml")
        crates: dict[str, str] = {}
        if not os.path.isfile(cargo):
            return crates
        try:
            with open(cargo, encoding="utf-8") as fp:
                content = fp.read()
        except OSError:
            return crates
        # Extract workspace members: members = ["crate1", "crate2"]
        m = re.search(r'members\s*=\s*\[(.*?)\]', content, re.DOTALL)
        if not m:
            return crates
        for member_match in re.finditer(r'"([^"]+)"', m.group(1)):
            member_path = member_match.group(1)
            member_dir = os.path.join(project_root, member_path)
            if not os.path.isdir(member_dir):
                continue
            # Crate name defaults to directory name (hyphens → underscores in Rust)
            crate_name = os.path.basename(member_path).replace("-", "_")
            # Check member's Cargo.toml for explicit name
            member_cargo = os.path.join(member_dir, "Cargo.toml")
            if os.path.isfile(member_cargo):
                try:
                    with open(member_cargo, encoding="utf-8") as fp:
                        mc = fp.read()
                    nm = re.search(r'name\s*=\s*"([^"]+)"', mc)
                    if nm:
                        crate_name = nm.group(1).replace("-", "_")
                except OSError:
                    pass
            src_dir = os.path.join(member_path, "src")
            crates[crate_name] = os.path.relpath(src_dir, ".") if os.path.isdir(os.path.join(project_root, src_dir)) else member_path
        return crates

    def pick_test_cmd(self, project_root: str) -> list[str]:
        return ["cargo", "test"]

    def error_patterns(self) -> list[tuple[str, str, str]]:
        return [
            ("cannot find", "import_error", "Check use/mod paths"),
            ("expected", "syntax_error", "Fix Rust syntax"),
            ("test result: FAILED", "test_failure", "One or more tests failed"),
            ("error[E", "compile_error", "Check compiler error code"),
        ]


# ── C/C++ ─────────────────────────────────────────────────────────────────────

_CPP_EXTENSIONS = (".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx")

_CPP_TYPED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:^|\n)\s*(?:template\s*<(?:[^<>]|<[^<>]*>)*>\s*)?class\s+(\w+)"), "class"),
    (re.compile(r"(?:^|\n)\s*(?:typedef\s+)?struct\s+(\w+)"), "struct"),
    (re.compile(r"(?:^|\n)\s*namespace\s+(\w+)"), "namespace"),
    (re.compile(r"(?:^|\n)\s*enum\s+(?:class\s+)?(\w+)"), "enum"),
    (re.compile(r"(?:^|\n)\s*typedef\s+[\w\s*&:<>,]+\s+(\w+)\s*;"), "type_alias"),
    (re.compile(r"(?:^|\n)\s*(?:(?:static|inline|constexpr|virtual|explicit|extern)\s+)*(?:[\w:*&<>]+\s+)+(\w+)\s*\([^;)]*\)"), "function"),
]

_CPP_SYMBOL_PATTERNS: list[re.Pattern[str]] = [p for p, _ in _CPP_TYPED_PATTERNS] + [
    # Template function (handles nested angle brackets like vector<pair<int,int>>)
    re.compile(r"(?:^|\n)\s*template\s*<(?:[^<>]|<[^<>]*>)*>\s*(?:[\w:*&<>\s]+\s+)?(\w+)\s*\("),
    # Operator overloading
    re.compile(r"(?:^|\n)\s*(?:[\w:*&<>]+\s+)*(operator\s*(?:<<|>>|==|!=|<=|>=|[+\-*/%<>&|^~!]|\[\]|\(\)|->|new|delete))\s*\("),
    # Constructor/destructor (out-of-class: Class::~Class)
    re.compile(r"(?:^|\n)\s*(?:explicit\s+)?(\w+)\s*::\s*~?\w+\s*\("),
    # Macro-prefixed function (e.g. EXPORT_API void func())
    re.compile(r"(?:^|\n)\s*[A-Z_]{2,}\s+(?:[\w:*&<>]+\s+)*(\w+)\s*\("),
]

_CPP_INCLUDE_RE = re.compile(r'#include\s+"([^"]+)"')


class CppAnalyzer:
    """C/C++ code analysis via regex (stdlib-only)."""

    name = "cpp"
    extensions = _CPP_EXTENSIONS

    def collect_symbols(self, project_root: str) -> dict[str, list[str]]:
        return _collect_symbols_regex(
            project_root, _CPP_EXTENSIONS, _CPP_SYMBOL_PATTERNS, _strip_c_comments,
        )

    def collect_typed_symbols(self, project_root: str) -> dict[str, list[tuple[str, str]]]:
        return _collect_typed_symbols_regex(
            project_root, _CPP_EXTENSIONS, _CPP_TYPED_PATTERNS, _strip_c_comments,
        )

    def analyze_imports(self, project_root: str) -> dict[str, list[str]]:
        file_set = _collect_project_files(project_root, _CPP_EXTENSIONS)
        graph: dict[str, list[str]] = {}
        for rel in file_set:
            path = os.path.join(project_root, rel)
            try:
                with open(path, encoding="utf-8", errors="replace") as fp:
                    src = _strip_c_comments(fp.read())
            except OSError:
                continue
            deps: set[str] = set()
            for m in _CPP_INCLUDE_RE.finditer(src):
                include_path = m.group(1)
                # Resolve relative to including file's directory, then project root
                base_dir = os.path.dirname(rel)
                for base in (base_dir, ""):
                    candidate = os.path.normpath(os.path.join(base, include_path)) if base else include_path
                    if candidate in file_set and candidate != rel:
                        deps.add(candidate)
                        break
            if deps:
                graph[rel] = sorted(deps)
        return graph

    def pick_test_cmd(self, project_root: str) -> list[str]:
        if os.path.isfile(os.path.join(project_root, "CMakeLists.txt")):
            return ["ctest", "--test-dir", "build"]
        return ["make", "test"]

    def error_patterns(self) -> list[tuple[str, str, str]]:
        return [
            ("error:", "compile_error", "Check compiler error details"),
            ("undefined reference", "link_error", "Check that symbols are defined and linked"),
            ("fatal error:", "fatal_error", "Check include paths and dependencies"),
            ("FAILED", "test_failure", "One or more tests failed"),
        ]


# ── Java / Kotlin ─────────────────────────────────────────────────────────────

_JAVA_EXTENSIONS = (".java", ".kt", ".kts")

_JAVA_TYPED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:^|\n)\s*(?:(?:public|protected|private|abstract|final|static|open|internal|data|sealed)\s+)*class\s+(\w+)"), "class"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|protected|private|internal|sealed)\s+)*interface\s+(\w+)"), "interface"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|protected|private|internal)\s+)*enum\s+(?:class\s+)?(\w+)"), "enum"),
    # Java 16+ records
    (re.compile(r"(?:^|\n)\s*(?:(?:public|protected|private)\s+)*record\s+(\w+)"), "record"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|protected|private|internal|override|open|suspend|inline)\s+)*fun\s+(?:<(?:[^<>]|<[^<>]*>)*>\s*)?(\w+)"), "function"),
    (re.compile(r"(?:^|\n)\s*(?:(?:internal|private)\s+)?(?:companion\s+)?object\s+(\w+)"), "object"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|protected|private)\s+)*@interface\s+(\w+)"), "annotation"),
]

_JAVA_SYMBOL_PATTERNS: list[re.Pattern[str]] = [p for p, _ in _JAVA_TYPED_PATTERNS]

_JAVA_PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)", re.MULTILINE)
_JAVA_IMPORT_RE = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)", re.MULTILINE)


class JavaAnalyzer:
    """Java/Kotlin code analysis via regex (stdlib-only)."""

    name = "java"
    extensions = _JAVA_EXTENSIONS

    def collect_symbols(self, project_root: str) -> dict[str, list[str]]:
        return _collect_symbols_regex(project_root, _JAVA_EXTENSIONS, _JAVA_SYMBOL_PATTERNS, _strip_c_comments)

    def collect_typed_symbols(self, project_root: str) -> dict[str, list[tuple[str, str]]]:
        return _collect_typed_symbols_regex(project_root, _JAVA_EXTENSIONS, _JAVA_TYPED_PATTERNS, _strip_c_comments)

    def analyze_imports(self, project_root: str) -> dict[str, list[str]]:
        source_roots = self._detect_source_roots(project_root)
        # Build mapping: package -> list of project files declaring that package
        pkg_to_files: dict[str, list[str]] = {}
        file_sources: dict[str, str] = {}
        for src_root in source_roots:
            for root, dirs, files in os.walk(src_root):
                dirs[:] = [d for d in dirs if not _is_ignored_dir(d)]
                for fname in files:
                    if not fname.endswith(_JAVA_EXTENSIONS):
                        continue
                    path = os.path.join(root, fname)
                    rel = os.path.relpath(path, project_root)
                    try:
                        with open(path, encoding="utf-8", errors="replace") as fp:
                            src = fp.read()
                    except OSError:
                        continue
                    file_sources[rel] = src
                    m = _JAVA_PACKAGE_RE.search(src)
                    if m:
                        pkg_to_files.setdefault(m.group(1), []).append(rel)

        graph: dict[str, list[str]] = {}
        for rel, src in file_sources.items():
            deps: set[str] = set()
            for m in _JAVA_IMPORT_RE.finditer(src):
                import_path = m.group(1)
                parts = import_path.split(".")
                for i in range(len(parts), 0, -1):
                    pkg = ".".join(parts[:i])
                    if pkg in pkg_to_files:
                        for dep_file in pkg_to_files[pkg]:
                            if dep_file != rel:
                                deps.add(dep_file)
                        break
            # Fallback: files sharing the same package are co-dependent
            if not deps:
                m = _JAVA_PACKAGE_RE.search(src)
                if m:
                    for sibling in pkg_to_files.get(m.group(1), []):
                        if sibling != rel:
                            deps.add(sibling)
            if deps:
                graph[rel] = sorted(deps)
        return graph

    @staticmethod
    def _detect_source_roots(project_root: str) -> list[str]:
        """Detect Java/Kotlin source roots from build files or standard layouts."""
        roots: list[str] = []
        # Gradle
        for gradle_file in ("build.gradle", "build.gradle.kts"):
            if os.path.isfile(os.path.join(project_root, gradle_file)):
                for candidate in ("src/main/java", "src/main/kotlin",
                                  "src/test/java", "src/test/kotlin"):
                    full = os.path.join(project_root, candidate)
                    if os.path.isdir(full):
                        roots.append(full)
                break
        # Maven
        if not roots:
            pom = os.path.join(project_root, "pom.xml")
            if os.path.isfile(pom):
                try:
                    with open(pom, encoding="utf-8", errors="replace") as fp:
                        pom_text = fp.read()
                    m = re.search(r"<sourceDirectory>\s*(.*?)\s*</sourceDirectory>", pom_text)
                    if m:
                        full = os.path.join(project_root, m.group(1))
                        if os.path.isdir(full):
                            roots.append(full)
                except OSError:
                    pass
                if not roots:
                    for candidate in ("src/main/java", "src/test/java"):
                        full = os.path.join(project_root, candidate)
                        if os.path.isdir(full):
                            roots.append(full)
        # Fallback: project root itself
        if not roots:
            roots.append(project_root)
        return roots

    def pick_test_cmd(self, project_root: str) -> list[str]:
        if os.path.isfile(os.path.join(project_root, "gradlew")):
            return ["./gradlew", "test"]
        if os.path.isfile(os.path.join(project_root, "pom.xml")):
            return ["mvn", "test"]
        return ["gradle", "test"]

    def error_patterns(self) -> list[tuple[str, str, str]]:
        return [
            ("error:", "compile_error", "Check compiler error details"),
            ("FAILURE", "test_failure", "Build or test failure"),
            ("BUILD FAILED", "build_error", "Check build configuration"),
            ("Exception", "runtime_error", "Check exception details"),
        ]
