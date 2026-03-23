"""Extended language analyzers batch 2: C#, Ruby, PHP, Swift, Dart, Zig.

Separated from analyzers_ext.py to keep each module under 500 LOC.
Re-exported by analyzers.py and registered in its analyzer registry.
"""

from __future__ import annotations

import os
import re

from .utils import (
    _collect_project_files, _collect_symbols_regex,
    _collect_typed_symbols_regex,
    _resolve_namespace_import, _strip_c_comments,
    _strip_hash_comments, _strip_php_comments,
    _walk_and_map_namespaces,
)


# ── C# ──────────────────────────────────────────────────────────────────────

_CSHARP_EXTENSIONS = (".cs",)

_CSHARP_TYPED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:^|\n)\s*(?:(?:public|private|protected|internal|static|abstract|sealed|partial|async)\s+)*class\s+(\w+)"), "class"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|private|protected|internal)\s+)*interface\s+(\w+)"), "interface"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|private|protected|internal)\s+)*struct\s+(\w+)"), "struct"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|private|protected|internal)\s+)*enum\s+(\w+)"), "enum"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|private|protected|internal)\s+)*record\s+(\w+)"), "record"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|private|protected|internal|static|virtual|override|abstract|async)\s+)*[\w<>\[\],\s]+\s+(\w+)\s*\("), "function"),
]

_CSHARP_SYMBOL_PATTERNS: list[re.Pattern[str]] = [p for p, _ in _CSHARP_TYPED_PATTERNS]

_CSHARP_USING_RE = re.compile(r"^\s*using\s+([\w.]+)\s*;", re.MULTILINE)
_CSHARP_NAMESPACE_RE = re.compile(r"^\s*namespace\s+([\w.]+)", re.MULTILINE)


class CSharpAnalyzer:
    """C# code analysis via regex (stdlib-only)."""

    name = "csharp"
    extensions = _CSHARP_EXTENSIONS

    def collect_symbols(self, project_root: str) -> dict[str, list[str]]:
        return _collect_symbols_regex(project_root, _CSHARP_EXTENSIONS, _CSHARP_SYMBOL_PATTERNS, _strip_c_comments)

    def collect_typed_symbols(self, project_root: str) -> dict[str, list[tuple[str, str]]]:
        return _collect_typed_symbols_regex(project_root, _CSHARP_EXTENSIONS, _CSHARP_TYPED_PATTERNS, _strip_c_comments)

    def analyze_imports(self, project_root: str) -> dict[str, list[str]]:
        ns_to_files, file_sources = _walk_and_map_namespaces(
            project_root, _CSHARP_EXTENSIONS, _CSHARP_NAMESPACE_RE, _strip_c_comments,
        )
        graph: dict[str, list[str]] = {}
        for rel, src in file_sources.items():
            deps: set[str] = set()
            for m in _CSHARP_USING_RE.finditer(src):
                _resolve_namespace_import(m.group(1), ns_to_files, rel, deps)
            if deps:
                graph[rel] = sorted(deps)
        return graph

    def pick_test_cmd(self, project_root: str) -> list[str]:
        return ["dotnet", "test"]

    def error_patterns(self) -> list[tuple[str, str, str]]:
        return [
            ("error CS", "compile_error", "Check C# compiler error"),
            ("Build FAILED", "build_error", "Check build configuration"),
            ("Failed!", "test_failure", "One or more tests failed"),
            ("Exception", "runtime_error", "Check exception details"),
        ]


# ── Ruby ─────────────────────────────────────────────────────────────────────

_RUBY_EXTENSIONS = (".rb",)

_RUBY_TYPED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:^|\n)\s*class\s+(\w+)"), "class"),
    (re.compile(r"(?:^|\n)\s*module\s+(\w+)"), "module"),
    (re.compile(r"(?:^|\n)\s*def\s+(?:self\.)?(\w+)"), "function"),
]

_RUBY_SYMBOL_PATTERNS: list[re.Pattern[str]] = [p for p, _ in _RUBY_TYPED_PATTERNS]

_RUBY_REQUIRE_RE = re.compile(r"""require(?:_relative)?\s+['"]([^'"]+)['"]""")


class RubyAnalyzer:
    """Ruby code analysis via regex (stdlib-only)."""

    name = "ruby"
    extensions = _RUBY_EXTENSIONS

    def collect_symbols(self, project_root: str) -> dict[str, list[str]]:
        return _collect_symbols_regex(project_root, _RUBY_EXTENSIONS, _RUBY_SYMBOL_PATTERNS, _strip_hash_comments)

    def collect_typed_symbols(self, project_root: str) -> dict[str, list[tuple[str, str]]]:
        return _collect_typed_symbols_regex(project_root, _RUBY_EXTENSIONS, _RUBY_TYPED_PATTERNS, _strip_hash_comments)

    def analyze_imports(self, project_root: str) -> dict[str, list[str]]:
        file_set = _collect_project_files(project_root, _RUBY_EXTENSIONS)
        # Full-path stems (highest priority) and basename stems (fallback)
        stem_to_file: dict[str, str] = {}
        basename_to_file: dict[str, str] = {}
        for rel in sorted(file_set):
            stem = rel.removesuffix(".rb")
            stem_to_file[stem] = rel
            basename_to_file.setdefault(os.path.basename(stem), rel)
        graph: dict[str, list[str]] = {}
        for rel in file_set:
            path = os.path.join(project_root, rel)
            try:
                with open(path, encoding="utf-8", errors="replace") as fp:
                    src = fp.read()
            except OSError:
                continue
            src = _strip_hash_comments(src)
            deps: set[str] = set()
            for m in _RUBY_REQUIRE_RE.finditer(src):
                req = m.group(1)
                resolved = stem_to_file.get(req) or basename_to_file.get(req)
                if resolved and resolved != rel:
                    deps.add(resolved)
            if deps:
                graph[rel] = sorted(deps)
        return graph

    def pick_test_cmd(self, project_root: str) -> list[str]:
        if os.path.isfile(os.path.join(project_root, "Gemfile")):
            return ["bundle", "exec", "rspec"]
        return ["ruby", "-Itest", "-e", "Dir.glob('test/**/test_*.rb').each{|f| require(f)}"]

    def error_patterns(self) -> list[tuple[str, str, str]]:
        return [
            ("Error", "runtime_error", "Check Ruby error details"),
            ("NameError", "name_error", "Check that referenced names exist"),
            ("LoadError", "import_error", "Check require paths"),
            ("FAILED", "test_failure", "One or more tests failed"),
        ]


# ── PHP ──────────────────────────────────────────────────────────────────────

_PHP_EXTENSIONS = (".php",)

_PHP_TYPED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:^|\n)\s*(?:(?:abstract|final)\s+)?class\s+(\w+)"), "class"),
    (re.compile(r"(?:^|\n)\s*interface\s+(\w+)"), "interface"),
    (re.compile(r"(?:^|\n)\s*trait\s+(\w+)"), "trait"),
    (re.compile(r"(?:^|\n)\s*enum\s+(\w+)"), "enum"),
    (re.compile(r"(?:^|\n)\s*function\s+(\w+)"), "function"),
    # Class methods (require at least one access modifier to avoid duplicating the function pattern)
    (re.compile(r"(?:^|\n)\s*(?:(?:public|protected|private|static|abstract|final)\s+)+function\s+(\w+)"), "method"),
]

_PHP_SYMBOL_PATTERNS: list[re.Pattern[str]] = [p for p, _ in _PHP_TYPED_PATTERNS]

_PHP_USE_RE = re.compile(r"^\s*use\s+([\w\\]+)\s*;", re.MULTILINE)
_PHP_USE_GROUP_RE = re.compile(r"^\s*use\s+([\w\\]+)\\\{([^}]+)\}", re.MULTILINE)
_PHP_NAMESPACE_RE = re.compile(r"^\s*namespace\s+([\w\\]+)", re.MULTILINE)


class PhpAnalyzer:
    """PHP code analysis via regex (stdlib-only)."""

    name = "php"
    extensions = _PHP_EXTENSIONS

    def collect_symbols(self, project_root: str) -> dict[str, list[str]]:
        return _collect_symbols_regex(project_root, _PHP_EXTENSIONS, _PHP_SYMBOL_PATTERNS, _strip_php_comments)

    def collect_typed_symbols(self, project_root: str) -> dict[str, list[tuple[str, str]]]:
        return _collect_typed_symbols_regex(project_root, _PHP_EXTENSIONS, _PHP_TYPED_PATTERNS, _strip_php_comments)

    def analyze_imports(self, project_root: str) -> dict[str, list[str]]:
        ns_to_files, file_sources = _walk_and_map_namespaces(
            project_root, _PHP_EXTENSIONS, _PHP_NAMESPACE_RE, _strip_php_comments,
        )
        # Normalize namespace keys to dot-separated for uniform resolution
        dot_ns_to_files: dict[str, list[str]] = {
            ns.replace("\\", "."): files for ns, files in ns_to_files.items()
        }
        graph: dict[str, list[str]] = {}
        for rel, src in file_sources.items():
            deps: set[str] = set()
            # Regular use statements: use Foo\Bar;
            use_paths: list[str] = [m.group(1) for m in _PHP_USE_RE.finditer(src)]
            # Grouped use statements: use Foo\{Bar, Baz};
            for m in _PHP_USE_GROUP_RE.finditer(src):
                prefix = m.group(1)
                for item in m.group(2).split(","):
                    item = item.split(" as ")[0].strip()
                    if item:
                        use_paths.append(prefix + "\\" + item)
            for use_path in use_paths:
                _resolve_namespace_import(
                    use_path.replace("\\", "."), dot_ns_to_files, rel, deps,
                )
            if deps:
                graph[rel] = sorted(deps)
        return graph

    def pick_test_cmd(self, project_root: str) -> list[str]:
        return ["vendor/bin/phpunit"]

    def error_patterns(self) -> list[tuple[str, str, str]]:
        return [
            ("Fatal error", "fatal_error", "Check PHP fatal error"),
            ("Parse error", "syntax_error", "Fix PHP syntax"),
            ("FAILURES!", "test_failure", "One or more tests failed"),
            ("Error:", "runtime_error", "Check error details"),
        ]


# ── Swift ────────────────────────────────────────────────────────────────────

_SWIFT_EXTENSIONS = (".swift",)

_SWIFT_TYPED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:^|\n)\s*(?:(?:public|private|internal|fileprivate|open)\s+)?class\s+(\w+)"), "class"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|private|internal|fileprivate|open)\s+)?struct\s+(\w+)"), "struct"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|private|internal|fileprivate|open)\s+)?enum\s+(\w+)"), "enum"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|private|internal|fileprivate|open)\s+)?protocol\s+(\w+)"), "protocol"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|private|internal|fileprivate|open|override|static|class)\s+)*func\s+(\w+)"), "function"),
    (re.compile(r"(?:^|\n)\s*extension\s+(\w+)"), "extension"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|private|internal)\s+)?typealias\s+(\w+)"), "type_alias"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|private|internal)\s+)?actor\s+(\w+)"), "actor"),
]

_SWIFT_SYMBOL_PATTERNS: list[re.Pattern[str]] = [p for p, _ in _SWIFT_TYPED_PATTERNS]

_SWIFT_IMPORT_RE = re.compile(r"^\s*import\s+(\w+)", re.MULTILINE)


class SwiftAnalyzer:
    """Swift code analysis via regex (stdlib-only)."""

    name = "swift"
    extensions = _SWIFT_EXTENSIONS

    def collect_symbols(self, project_root: str) -> dict[str, list[str]]:
        return _collect_symbols_regex(project_root, _SWIFT_EXTENSIONS, _SWIFT_SYMBOL_PATTERNS, _strip_c_comments)

    def collect_typed_symbols(self, project_root: str) -> dict[str, list[tuple[str, str]]]:
        return _collect_typed_symbols_regex(project_root, _SWIFT_EXTENSIONS, _SWIFT_TYPED_PATTERNS, _strip_c_comments)

    def analyze_imports(self, project_root: str) -> dict[str, list[str]]:
        file_set = _collect_project_files(project_root, _SWIFT_EXTENSIONS)
        module_to_files = self._build_module_map(project_root, file_set)
        graph: dict[str, list[str]] = {}
        for rel in file_set:
            path = os.path.join(project_root, rel)
            try:
                with open(path, encoding="utf-8", errors="replace") as fp:
                    src = _strip_c_comments(fp.read())
            except OSError:
                continue
            deps: set[str] = set()
            for m in _SWIFT_IMPORT_RE.finditer(src):
                mod = m.group(1)
                for dep in module_to_files.get(mod, []):
                    if dep != rel:
                        deps.add(dep)
            if deps:
                graph[rel] = sorted(deps)
        return graph

    @staticmethod
    def _scan_spm_dir(
        project_root: str, dirname: str, file_set: set[str],
        module_to_files: dict[str, list[str]],
    ) -> None:
        """Scan an SPM directory (Sources or Tests) for module subdirectories."""
        full_dir = os.path.join(project_root, dirname)
        if not os.path.isdir(full_dir):
            return
        try:
            for entry in os.listdir(full_dir):
                if os.path.isdir(os.path.join(full_dir, entry)):
                    norm_prefix = os.path.join(dirname, entry).replace(os.sep, "/") + "/"
                    mod_files = [f for f in file_set if f.replace(os.sep, "/").startswith(norm_prefix)]
                    if mod_files:
                        module_to_files[entry] = mod_files
        except OSError:
            pass

    @staticmethod
    def _build_module_map(project_root: str, file_set: set[str]) -> dict[str, list[str]]:
        """Map module names to files. SPM-aware: Sources/<Module>/ directories are modules."""
        module_to_files: dict[str, list[str]] = {}
        SwiftAnalyzer._scan_spm_dir(project_root, "Sources", file_set, module_to_files)
        SwiftAnalyzer._scan_spm_dir(project_root, "Tests", file_set, module_to_files)
        # Fallback: immediate parent directory name (for non-SPM projects)
        if not module_to_files:
            for rel in file_set:
                parts = rel.replace(os.sep, "/").split("/")
                if len(parts) >= 2:
                    module_to_files.setdefault(parts[-2], []).append(rel)
        return module_to_files

    def pick_test_cmd(self, project_root: str) -> list[str]:
        if os.path.isfile(os.path.join(project_root, "Package.swift")):
            return ["swift", "test"]
        return ["xcodebuild", "test"]

    def error_patterns(self) -> list[tuple[str, str, str]]:
        return [
            ("error:", "compile_error", "Check Swift compiler error"),
            ("fatal error", "fatal_error", "Check fatal error"),
            ("Test Case", "test_failure", "One or more tests failed"),
        ]


# ── Dart ─────────────────────────────────────────────────────────────────────

_DART_EXTENSIONS = (".dart",)

_DART_TYPED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:^|\n)\s*(?:abstract\s+)?class\s+(\w+)"), "class"),
    (re.compile(r"(?:^|\n)\s*mixin\s+(\w+)"), "mixin"),
    (re.compile(r"(?:^|\n)\s*extension\s+(\w+)"), "extension"),
    (re.compile(r"(?:^|\n)\s*enum\s+(\w+)"), "enum"),
    (re.compile(r"(?:^|\n)\s*typedef\s+(\w+)"), "type_alias"),
    (re.compile(r"(?:^|\n)\s*(?:[\w<>?]+\s+)?(?!if|else|for|while|do|switch|catch)(\w+)\s*\([^)]*\)\s*(?:async\s*)?[{=]"), "function"),
    # Factory and named constructors: factory ClassName.name(...) or ClassName.name(...)
    (re.compile(r"(?:^|\n)\s*(?:factory\s+)?(\w+\.\w+)\s*\("), "constructor"),
]

_DART_SYMBOL_PATTERNS: list[re.Pattern[str]] = [p for p, _ in _DART_TYPED_PATTERNS]

_DART_IMPORT_RE = re.compile(r"""import\s+['"](?:package:[\w/]+/)?([^'"]+)['"]""")


class DartAnalyzer:
    """Dart code analysis via regex (stdlib-only)."""

    name = "dart"
    extensions = _DART_EXTENSIONS

    def collect_symbols(self, project_root: str) -> dict[str, list[str]]:
        return _collect_symbols_regex(project_root, _DART_EXTENSIONS, _DART_SYMBOL_PATTERNS, _strip_c_comments)

    def collect_typed_symbols(self, project_root: str) -> dict[str, list[tuple[str, str]]]:
        return _collect_typed_symbols_regex(project_root, _DART_EXTENSIONS, _DART_TYPED_PATTERNS, _strip_c_comments)

    def analyze_imports(self, project_root: str) -> dict[str, list[str]]:
        file_set = _collect_project_files(project_root, _DART_EXTENSIONS)
        graph: dict[str, list[str]] = {}
        for rel in file_set:
            path = os.path.join(project_root, rel)
            try:
                with open(path, encoding="utf-8", errors="replace") as fp:
                    src = fp.read()
            except OSError:
                continue
            src = _strip_c_comments(src)
            deps: set[str] = set()
            for m in _DART_IMPORT_RE.finditer(src):
                import_path = m.group(1)
                if import_path in file_set and import_path != rel:
                    deps.add(import_path)
                else:
                    # Try relative resolution only if direct match failed
                    base = os.path.normpath(os.path.join(os.path.dirname(rel), import_path))
                    if base in file_set and base != rel:
                        deps.add(base)
            if deps:
                graph[rel] = sorted(deps)
        return graph

    def pick_test_cmd(self, project_root: str) -> list[str]:
        return ["dart", "test"]

    def error_patterns(self) -> list[tuple[str, str, str]]:
        return [
            ("Error:", "compile_error", "Check Dart compiler error"),
            ("Failed assertion", "assertion_error", "Check assertion"),
            ("Some tests failed", "test_failure", "One or more tests failed"),
        ]


# ── Zig ──────────────────────────────────────────────────────────────────────

_ZIG_EXTENSIONS = (".zig",)

_ZIG_TYPED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:^|\n)\s*(?:pub\s+)?fn\s+(\w+)"), "function"),
    (re.compile(r"(?:^|\n)\s*(?:pub\s+)?const\s+(\w+)\s*=\s*struct"), "struct"),
    (re.compile(r"(?:^|\n)\s*(?:pub\s+)?const\s+(\w+)\s*=\s*enum"), "enum"),
    (re.compile(r"(?:^|\n)\s*(?:pub\s+)?const\s+(\w+)\s*=\s*union"), "union"),
    (re.compile(r"(?:^|\n)\s*(?:pub\s+)?const\s+(\w+)\s*=\s*@import"), "import_const"),
    (re.compile(r"(?:^|\n)\s*(?:pub\s+)?const\s+(\w+)\s*:\s*type"), "type_alias"),
]

# Zig symbol patterns differ from typed: combine struct/enum/union into one pattern
_ZIG_SYMBOL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:^|\n)\s*(?:pub\s+)?fn\s+(\w+)"),
    re.compile(r"(?:^|\n)\s*(?:pub\s+)?const\s+(\w+)\s*=\s*(?:struct|enum|union)"),
    re.compile(r"(?:^|\n)\s*(?:pub\s+)?const\s+(\w+)\s*=\s*@import"),
    re.compile(r"(?:^|\n)\s*(?:pub\s+)?const\s+(\w+)\s*:\s*type"),
]

_ZIG_IMPORT_RE = re.compile(r'@import\(\s*"([^"]+)"\s*\)')


class ZigAnalyzer:
    """Zig code analysis via regex (stdlib-only)."""

    name = "zig"
    extensions = _ZIG_EXTENSIONS

    def collect_symbols(self, project_root: str) -> dict[str, list[str]]:
        return _collect_symbols_regex(project_root, _ZIG_EXTENSIONS, _ZIG_SYMBOL_PATTERNS, _strip_c_comments)

    def collect_typed_symbols(self, project_root: str) -> dict[str, list[tuple[str, str]]]:
        return _collect_typed_symbols_regex(project_root, _ZIG_EXTENSIONS, _ZIG_TYPED_PATTERNS, _strip_c_comments)

    def analyze_imports(self, project_root: str) -> dict[str, list[str]]:
        file_set = _collect_project_files(project_root, _ZIG_EXTENSIONS)
        graph: dict[str, list[str]] = {}
        for rel in file_set:
            path = os.path.join(project_root, rel)
            try:
                with open(path, encoding="utf-8", errors="replace") as fp:
                    src = fp.read()
            except OSError:
                continue
            src = _strip_c_comments(src)
            deps: set[str] = set()
            for m in _ZIG_IMPORT_RE.finditer(src):
                import_path = m.group(1)
                if import_path.endswith(".zig"):
                    base = os.path.normpath(os.path.join(os.path.dirname(rel), import_path))
                    if base in file_set and base != rel:
                        deps.add(base)
            if deps:
                graph[rel] = sorted(deps)
        return graph

    def pick_test_cmd(self, project_root: str) -> list[str]:
        return ["zig", "build", "test"]

    def error_patterns(self) -> list[tuple[str, str, str]]:
        return [
            ("error:", "compile_error", "Check Zig compiler error"),
            ("FAIL", "test_failure", "One or more tests failed"),
            ("panic", "runtime_error", "Check panic details"),
        ]
