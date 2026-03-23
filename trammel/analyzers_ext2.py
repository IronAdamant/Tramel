"""Extended language analyzers batch 2: C#, Ruby, PHP, Swift, Dart, Zig.

Separated from analyzers_ext.py to keep each module under 500 LOC.
Re-exported by analyzers.py and registered in its analyzer registry.
"""

from __future__ import annotations

import os
import re

from .utils import (
    _collect_project_files, _collect_symbols_regex,
    _collect_typed_symbols_regex, _is_ignored_dir,
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
        return _collect_symbols_regex(project_root, _CSHARP_EXTENSIONS, _CSHARP_SYMBOL_PATTERNS)

    def collect_typed_symbols(self, project_root: str) -> dict[str, list[tuple[str, str]]]:
        return _collect_typed_symbols_regex(project_root, _CSHARP_EXTENSIONS, _CSHARP_TYPED_PATTERNS)

    def analyze_imports(self, project_root: str) -> dict[str, list[str]]:
        ns_to_files: dict[str, list[str]] = {}
        file_sources: dict[str, str] = {}
        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if not _is_ignored_dir(d)]
            for fname in files:
                if not fname.endswith(".cs"):
                    continue
                path = os.path.join(root, fname)
                rel = os.path.relpath(path, project_root)
                try:
                    with open(path, encoding="utf-8", errors="replace") as fp:
                        src = fp.read()
                except OSError:
                    continue
                file_sources[rel] = src
                m = _CSHARP_NAMESPACE_RE.search(src)
                if m:
                    ns_to_files.setdefault(m.group(1), []).append(rel)
        graph: dict[str, list[str]] = {}
        for rel, src in file_sources.items():
            deps: set[str] = set()
            for m in _CSHARP_USING_RE.finditer(src):
                ns = m.group(1)
                parts = ns.split(".")
                for i in range(len(parts), 0, -1):
                    prefix = ".".join(parts[:i])
                    if prefix in ns_to_files:
                        for dep in ns_to_files[prefix]:
                            if dep != rel:
                                deps.add(dep)
                        break
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
        return _collect_symbols_regex(project_root, _RUBY_EXTENSIONS, _RUBY_SYMBOL_PATTERNS)

    def collect_typed_symbols(self, project_root: str) -> dict[str, list[tuple[str, str]]]:
        return _collect_typed_symbols_regex(project_root, _RUBY_EXTENSIONS, _RUBY_TYPED_PATTERNS)

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
]

_PHP_SYMBOL_PATTERNS: list[re.Pattern[str]] = [p for p, _ in _PHP_TYPED_PATTERNS]

_PHP_USE_RE = re.compile(r"^\s*use\s+([\w\\]+)", re.MULTILINE)
_PHP_NAMESPACE_RE = re.compile(r"^\s*namespace\s+([\w\\]+)", re.MULTILINE)


class PhpAnalyzer:
    """PHP code analysis via regex (stdlib-only)."""

    name = "php"
    extensions = _PHP_EXTENSIONS

    def collect_symbols(self, project_root: str) -> dict[str, list[str]]:
        return _collect_symbols_regex(project_root, _PHP_EXTENSIONS, _PHP_SYMBOL_PATTERNS)

    def collect_typed_symbols(self, project_root: str) -> dict[str, list[tuple[str, str]]]:
        return _collect_typed_symbols_regex(project_root, _PHP_EXTENSIONS, _PHP_TYPED_PATTERNS)

    def analyze_imports(self, project_root: str) -> dict[str, list[str]]:
        ns_to_files: dict[str, list[str]] = {}
        file_sources: dict[str, str] = {}
        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if not _is_ignored_dir(d)]
            for fname in files:
                if not fname.endswith(".php"):
                    continue
                path = os.path.join(root, fname)
                rel = os.path.relpath(path, project_root)
                try:
                    with open(path, encoding="utf-8", errors="replace") as fp:
                        src = fp.read()
                except OSError:
                    continue
                file_sources[rel] = src
                m = _PHP_NAMESPACE_RE.search(src)
                if m:
                    ns_to_files.setdefault(m.group(1), []).append(rel)
        # Build reverse index for fast namespace lookup
        ns_dot_map: dict[str, str] = {ns.replace("\\", "."): ns for ns in ns_to_files}
        graph: dict[str, list[str]] = {}
        for rel, src in file_sources.items():
            deps: set[str] = set()
            for m in _PHP_USE_RE.finditer(src):
                use_path = m.group(1).replace("\\", ".")
                parts = use_path.split(".")
                for i in range(len(parts), 0, -1):
                    prefix = ".".join(parts[:i])
                    if prefix in ns_dot_map:
                        for dep in ns_to_files[ns_dot_map[prefix]]:
                            if dep != rel:
                                deps.add(dep)
                        break
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
        return _collect_symbols_regex(project_root, _SWIFT_EXTENSIONS, _SWIFT_SYMBOL_PATTERNS)

    def collect_typed_symbols(self, project_root: str) -> dict[str, list[tuple[str, str]]]:
        return _collect_typed_symbols_regex(project_root, _SWIFT_EXTENSIONS, _SWIFT_TYPED_PATTERNS)

    def analyze_imports(self, project_root: str) -> dict[str, list[str]]:
        file_set = _collect_project_files(project_root, _SWIFT_EXTENSIONS)
        # Map immediate parent directory name to files (Swift modules map to directories)
        dir_to_files: dict[str, list[str]] = {}
        for rel in file_set:
            parts = rel.replace(os.sep, "/").split("/")
            if len(parts) >= 2:
                dir_to_files.setdefault(parts[-2], []).append(rel)
        graph: dict[str, list[str]] = {}
        for rel in file_set:
            path = os.path.join(project_root, rel)
            try:
                with open(path, encoding="utf-8", errors="replace") as fp:
                    src = fp.read()
            except OSError:
                continue
            deps: set[str] = set()
            for m in _SWIFT_IMPORT_RE.finditer(src):
                mod = m.group(1)
                for dep in dir_to_files.get(mod, []):
                    if dep != rel:
                        deps.add(dep)
            if deps:
                graph[rel] = sorted(deps)
        return graph

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
    (re.compile(r"(?:^|\n)\s*(?:[\w<>?]+\s+)?(\w+)\s*\([^)]*\)\s*(?:async\s*)?[{=]"), "function"),
]

_DART_SYMBOL_PATTERNS: list[re.Pattern[str]] = [p for p, _ in _DART_TYPED_PATTERNS]

_DART_IMPORT_RE = re.compile(r"""import\s+['"](?:package:[\w/]+/)?([^'"]+)['"]""")


class DartAnalyzer:
    """Dart code analysis via regex (stdlib-only)."""

    name = "dart"
    extensions = _DART_EXTENSIONS

    def collect_symbols(self, project_root: str) -> dict[str, list[str]]:
        return _collect_symbols_regex(project_root, _DART_EXTENSIONS, _DART_SYMBOL_PATTERNS)

    def collect_typed_symbols(self, project_root: str) -> dict[str, list[tuple[str, str]]]:
        return _collect_typed_symbols_regex(project_root, _DART_EXTENSIONS, _DART_TYPED_PATTERNS)

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
            deps: set[str] = set()
            for m in _DART_IMPORT_RE.finditer(src):
                import_path = m.group(1)
                if import_path in file_set and import_path != rel:
                    deps.add(import_path)
                # Try relative resolution
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

# Zig symbol patterns differ from typed: combine struct/enum/union and omit type_alias
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
        return _collect_symbols_regex(project_root, _ZIG_EXTENSIONS, _ZIG_SYMBOL_PATTERNS)

    def collect_typed_symbols(self, project_root: str) -> dict[str, list[tuple[str, str]]]:
        return _collect_typed_symbols_regex(project_root, _ZIG_EXTENSIONS, _ZIG_TYPED_PATTERNS)

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
