"""Declarative analyzer specs — one table to rule the regex analyzers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .utils import _strip_c_comments, _strip_hash_comments, _strip_php_comments


_COMMENT_STRIPPERS: dict[str, Callable[[str], str]] = {
    "c": _strip_c_comments,
    "hash": _strip_hash_comments,
    "php": _strip_php_comments,
}


@dataclass(frozen=True)
class ImportSpec:
    strategy: str
    patterns: list[tuple[re.Pattern[str], str | None]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnalyzerSpec:
    name: str
    extensions: tuple[str, ...]
    symbol_patterns: list[re.Pattern[str]]
    typed_patterns: list[tuple[re.Pattern[str], str]]
    strip_comments: str  # key into _COMMENT_STRIPPERS
    test_cmd: list[str] | Callable[[str], list[str]]
    error_patterns: list[tuple[str, str, str]]
    imports: ImportSpec | None = None


# ═══════════════════════════════════════════════════════════════════════════════
# Go
# ═══════════════════════════════════════════════════════════════════════════════

GO_SPEC = AnalyzerSpec(
    name="go",
    extensions=(".go",),
    symbol_patterns=[
        re.compile(r"(?:^|\n)\s*func\s+(?:\([^)]+\)\s+)?(\w+)"),
        re.compile(r"(?:^|\n)\s*type\s+(\w+)\s+"),
        re.compile(r"(?:^|\n)\s*(?:var|const)\s+(\w+)\s"),
    ],
    typed_patterns=[
        (re.compile(r"(?:^|\n)\s*func\s+(?:\([^)]+\)\s+)?(\w+)"), "function"),
        (re.compile(r"(?:^|\n)\s*type\s+(\w+)\s+struct"), "struct"),
        (re.compile(r"(?:^|\n)\s*type\s+(\w+)\s+interface"), "interface"),
        (re.compile(r"(?:^|\n)\s*type\s+(\w+)\s+(?!struct|interface)"), "type"),
        (re.compile(r"(?:^|\n)\s*const\s+(\w+)\s"), "constant"),
        (re.compile(r"(?:^|\n)\s*var\s+(\w+)\s"), "variable"),
    ],
    strip_comments="c",
    test_cmd=["go", "test", "./..."],
    error_patterns=[
        ("cannot find package", "import_error", "Check import paths"),
        ("undefined:", "name_error", "Check that names are defined"),
        ("syntax error", "syntax_error", "Fix Go syntax"),
        ("FAIL", "test_failure", "One or more tests failed"),
    ],
    imports=ImportSpec(
        strategy="go_mod",
        patterns=[
            (re.compile(r'import\s+"([^"]+)"'), None),
            (re.compile(r'import\s*\((.*?)\)', re.DOTALL), "block"),
        ],
    ),
)

# ═══════════════════════════════════════════════════════════════════════════════
# Rust
# ═══════════════════════════════════════════════════════════════════════════════

_RUST_TYPED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:^|\n)\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+(\w+)"), "function"),
    (re.compile(r"(?:^|\n)\s*(?:pub(?:\([^)]*\))?\s+)?struct\s+(\w+)"), "struct"),
    (re.compile(r"(?:^|\n)\s*(?:pub(?:\([^)]*\))?\s+)?enum\s+(\w+)"), "enum"),
    (re.compile(r"(?:^|\n)\s*(?:pub(?:\([^)]*\))?\s+)?trait\s+(\w+)"), "trait"),
    (re.compile(r"(?:^|\n)\s*impl(?:<(?:[^<>]|<[^<>]*>)*>)?\s+(\w+)"), "impl"),
    (re.compile(r"(?:^|\n)\s*(?:pub(?:\([^)]*\))?\s+)?type\s+(\w+)"), "type_alias"),
]

RUST_SPEC = AnalyzerSpec(
    name="rust",
    extensions=(".rs",),
    symbol_patterns=[p for p, _ in _RUST_TYPED_PATTERNS],
    typed_patterns=_RUST_TYPED_PATTERNS,
    strip_comments="c",
    test_cmd=["cargo", "test"],
    error_patterns=[
        ("cannot find", "import_error", "Check use/mod paths"),
        ("expected", "syntax_error", "Fix Rust syntax"),
        ("test result: FAILED", "test_failure", "One or more tests failed"),
        ("error[E", "compile_error", "Check compiler error code"),
    ],
    imports=ImportSpec(
        strategy="rust_crate",
        patterns=[
            (re.compile(r"use\s+crate::(\w+(?:::\w+)*)"), "crate"),
            (re.compile(r"use\s+super::(\w+(?:::\w+)*)"), "super"),
            (re.compile(r"use\s+self::(\w+(?:::\w+)*)"), "self"),
            (re.compile(r"(?:^|\n)\s*mod\s+(\w+)\s*;"), "mod"),
        ],
    ),
)

# ═══════════════════════════════════════════════════════════════════════════════
# C / C++
# ═══════════════════════════════════════════════════════════════════════════════

_CPP_TYPED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:^|\n)\s*(?:template\s*<(?:[^<>]|<[^<>]*>)*>\s*)?class\s+(\w+)"), "class"),
    (re.compile(r"(?:^|\n)\s*(?:typedef\s+)?struct\s+(\w+)"), "struct"),
    (re.compile(r"(?:^|\n)\s*namespace\s+(\w+)"), "namespace"),
    (re.compile(r"(?:^|\n)\s*enum\s+(?:class\s+)?(\w+)"), "enum"),
    (re.compile(r"(?:^|\n)\s*typedef\s+[\w\s*&:<>,]+\s+(\w+)\s*;"), "type_alias"),
    (re.compile(r"(?:^|\n)\s*(?:(?:static|inline|constexpr|virtual|explicit|extern)\s+)*(?:[\w:*&<>]+\s+)+(\w+)\s*\([^;)]*\)"), "function"),
]

_CPP_SYMBOL_PATTERNS: list[re.Pattern[str]] = [p for p, _ in _CPP_TYPED_PATTERNS] + [
    re.compile(r"(?:^|\n)\s*template\s*<(?:[^<>]|<[^<>]*>)*>\s*(?:[\w:*&<>\s]+\s+)?(\w+)\s*\("),
    re.compile(r"(?:^|\n)\s*(?:[\w:*&<>]+\s+)*(operator\s*(?:<<|>>|==|!=|<=|>=|[+\-*/%<>&|^~!]|\[\]|\(\)|->|new|delete))\s*\("),
    re.compile(r"(?:^|\n)\s*(?:explicit\s+)?(\w+)\s*::\s*~?\w+\s*\("),
    re.compile(r"(?:^|\n)\s*[A-Z_]{2,}\s+(?:[\w:*&<>]+\s+)*(\w+)\s*\("),
]

CPP_SPEC = AnalyzerSpec(
    name="cpp",
    extensions=(".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx"),
    symbol_patterns=_CPP_SYMBOL_PATTERNS,
    typed_patterns=_CPP_TYPED_PATTERNS,
    strip_comments="c",
    test_cmd=lambda root: (
        ["ctest", "--test-dir", "build"]
        if __import__("os").path.isfile(__import__("os").path.join(root, "CMakeLists.txt"))
        else ["make", "test"]
    ),
    error_patterns=[
        ("error:", "compile_error", "Check compiler error details"),
        ("undefined reference", "link_error", "Check that symbols are defined and linked"),
        ("fatal error:", "fatal_error", "Check include paths and dependencies"),
        ("FAILED", "test_failure", "One or more tests failed"),
    ],
    imports=ImportSpec(
        strategy="cpp_include",
        patterns=[(re.compile(r'#include\s+"([^"]+)"'), None)],
    ),
)

# ═══════════════════════════════════════════════════════════════════════════════
# Java / Kotlin
# ═══════════════════════════════════════════════════════════════════════════════

_JAVA_TYPED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:^|\n)\s*(?:(?:public|protected|private|abstract|final|static|open|internal|data|sealed)\s+)*class\s+(\w+)"), "class"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|protected|private|internal|sealed)\s+)*interface\s+(\w+)"), "interface"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|protected|private|internal)\s+)*enum\s+(?:class\s+)?(\w+)"), "enum"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|protected|private)\s+)*record\s+(\w+)"), "record"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|protected|private|internal|override|open|suspend|inline)\s+)*fun\s+(?:<(?:[^<>]|<[^<>]*>)*>\s*)?(\w+)"), "function"),
    (re.compile(r"(?:^|\n)\s*(?:(?:internal|private)\s+)?(?:companion\s+)?object\s+(\w+)"), "object"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|protected|private)\s+)*@interface\s+(\w+)"), "annotation"),
]

JAVA_SPEC = AnalyzerSpec(
    name="java",
    extensions=(".java", ".kt", ".kts"),
    symbol_patterns=[p for p, _ in _JAVA_TYPED_PATTERNS],
    typed_patterns=_JAVA_TYPED_PATTERNS,
    strip_comments="c",
    test_cmd=lambda root: (
        ["./gradlew", "test"]
        if __import__("os").path.isfile(__import__("os").path.join(root, "gradlew"))
        else (
            ["mvn", "test"]
            if __import__("os").path.isfile(__import__("os").path.join(root, "pom.xml"))
            else ["gradle", "test"]
        )
    ),
    error_patterns=[
        ("error:", "compile_error", "Check compiler error details"),
        ("FAILURE", "test_failure", "Build or test failure"),
        ("BUILD FAILED", "build_error", "Check build configuration"),
        ("Exception", "runtime_error", "Check exception details"),
    ],
    imports=ImportSpec(
        strategy="java_namespace",
        patterns=[(re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)", re.MULTILINE), None)],
        extra={"namespace_re": re.compile(r"^\s*package\s+([\w.]+)", re.MULTILINE)},
    ),
)

# ═══════════════════════════════════════════════════════════════════════════════
# C#
# ═══════════════════════════════════════════════════════════════════════════════

_CSHARP_TYPED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:^|\n)\s*(?:(?:public|private|protected|internal|static|abstract|sealed|partial|async)\s+)*class\s+(\w+)"), "class"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|private|protected|internal)\s+)*interface\s+(\w+)"), "interface"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|private|protected|internal)\s+)*struct\s+(\w+)"), "struct"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|private|protected|internal)\s+)*enum\s+(\w+)"), "enum"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|private|protected|internal)\s+)*record\s+(\w+)"), "record"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|private|protected|internal|static|virtual|override|abstract|async)\s+)*[\w<>\[\],\s]+\s+(\w+)\s*\("), "function"),
]

CSHARP_SPEC = AnalyzerSpec(
    name="csharp",
    extensions=(".cs",),
    symbol_patterns=[p for p, _ in _CSHARP_TYPED_PATTERNS],
    typed_patterns=_CSHARP_TYPED_PATTERNS,
    strip_comments="c",
    test_cmd=["dotnet", "test"],
    error_patterns=[
        ("error CS", "compile_error", "Check C# compiler error"),
        ("Build FAILED", "build_error", "Check build configuration"),
        ("Failed!", "test_failure", "One or more tests failed"),
        ("Exception", "runtime_error", "Check exception details"),
    ],
    imports=ImportSpec(
        strategy="csharp_namespace",
        patterns=[(re.compile(r"^\s*using\s+([\w.]+)\s*;", re.MULTILINE), None)],
        extra={"namespace_re": re.compile(r"^\s*namespace\s+([\w.]+)", re.MULTILINE)},
    ),
)

# ═══════════════════════════════════════════════════════════════════════════════
# Ruby
# ═══════════════════════════════════════════════════════════════════════════════

RUBY_SPEC = AnalyzerSpec(
    name="ruby",
    extensions=(".rb",),
    symbol_patterns=[
        re.compile(r"(?:^|\n)\s*class\s+(\w+)"),
        re.compile(r"(?:^|\n)\s*module\s+(\w+)"),
        re.compile(r"(?:^|\n)\s*def\s+(?:self\.)?(\w+)"),
    ],
    typed_patterns=[
        (re.compile(r"(?:^|\n)\s*class\s+(\w+)"), "class"),
        (re.compile(r"(?:^|\n)\s*module\s+(\w+)"), "module"),
        (re.compile(r"(?:^|\n)\s*def\s+(?:self\.)?(\w+)"), "function"),
    ],
    strip_comments="hash",
    test_cmd=lambda root: (
        ["bundle", "exec", "rspec"]
        if __import__("os").path.isfile(__import__("os").path.join(root, "Gemfile"))
        else ["ruby", "-Itest", "-e", "Dir.glob('test/**/test_*.rb').each{|f| require(f)}"]
    ),
    error_patterns=[
        ("Error", "runtime_error", "Check Ruby error details"),
        ("NameError", "name_error", "Check that referenced names exist"),
        ("LoadError", "import_error", "Check require paths"),
        ("FAILED", "test_failure", "One or more tests failed"),
    ],
    imports=ImportSpec(
        strategy="ruby_require",
        patterns=[(re.compile(r"""require(?:_relative)?\s+['\"]([^'\"]+)['\"]"""), None)],
    ),
)

# ═══════════════════════════════════════════════════════════════════════════════
# PHP
# ═══════════════════════════════════════════════════════════════════════════════

_PHP_TYPED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:^|\n)\s*(?:(?:abstract|final)\s+)?class\s+(\w+)"), "class"),
    (re.compile(r"(?:^|\n)\s*interface\s+(\w+)"), "interface"),
    (re.compile(r"(?:^|\n)\s*trait\s+(\w+)"), "trait"),
    (re.compile(r"(?:^|\n)\s*enum\s+(\w+)"), "enum"),
    (re.compile(r"(?:^|\n)\s*function\s+(\w+)"), "function"),
    (re.compile(r"(?:^|\n)\s*(?:(?:public|protected|private|static|abstract|final)\s+)+function\s+(\w+)"), "method"),
]

PHP_SPEC = AnalyzerSpec(
    name="php",
    extensions=(".php",),
    symbol_patterns=[p for p, _ in _PHP_TYPED_PATTERNS],
    typed_patterns=_PHP_TYPED_PATTERNS,
    strip_comments="php",
    test_cmd=["vendor/bin/phpunit"],
    error_patterns=[
        ("Fatal error", "fatal_error", "Check PHP fatal error"),
        ("Parse error", "syntax_error", "Fix PHP syntax"),
        ("FAILURES!", "test_failure", "One or more tests failed"),
        ("Error:", "runtime_error", "Check error details"),
    ],
    imports=ImportSpec(
        strategy="php_namespace",
        patterns=[
            (re.compile(r"^\s*use\s+([\w\\\\]+)\s*;", re.MULTILINE), "simple"),
            (re.compile(r"^\s*use\s+([\w\\\\]+)\\\{([^}]+)\}", re.MULTILINE), "group"),
        ],
        extra={"namespace_re": re.compile(r"^\s*namespace\s+([\w\\\\]+)", re.MULTILINE)},
    ),
)

# ═══════════════════════════════════════════════════════════════════════════════
# Swift
# ═══════════════════════════════════════════════════════════════════════════════

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

SWIFT_SPEC = AnalyzerSpec(
    name="swift",
    extensions=(".swift",),
    symbol_patterns=[p for p, _ in _SWIFT_TYPED_PATTERNS],
    typed_patterns=_SWIFT_TYPED_PATTERNS,
    strip_comments="c",
    test_cmd=lambda root: (
        ["swift", "test"]
        if __import__("os").path.isfile(__import__("os").path.join(root, "Package.swift"))
        else ["xcodebuild", "test"]
    ),
    error_patterns=[
        ("error:", "compile_error", "Check Swift compiler error"),
        ("fatal error", "fatal_error", "Check fatal error"),
        ("Test Case", "test_failure", "One or more tests failed"),
    ],
    imports=ImportSpec(
        strategy="swift_module",
        patterns=[(re.compile(r"^\s*import\s+(\w+)", re.MULTILINE), None)],
    ),
)

# ═══════════════════════════════════════════════════════════════════════════════
# Dart
# ═══════════════════════════════════════════════════════════════════════════════

_DART_TYPED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:^|\n)\s*(?:abstract\s+)?class\s+(\w+)"), "class"),
    (re.compile(r"(?:^|\n)\s*mixin\s+(\w+)"), "mixin"),
    (re.compile(r"(?:^|\n)\s*extension\s+(\w+)"), "extension"),
    (re.compile(r"(?:^|\n)\s*enum\s+(\w+)"), "enum"),
    (re.compile(r"(?:^|\n)\s*typedef\s+(\w+)"), "type_alias"),
    (re.compile(r"(?:^|\n)\s*(?:[\w<>?]+\s+)?(?!if|else|for|while|do|switch|catch)(\w+)\s*\([^)]*\)\s*(?:async\s*)?[{=]"), "function"),
    (re.compile(r"(?:^|\n)\s*(?:factory\s+)?(\w+\.\w+)\s*\("), "constructor"),
]

DART_SPEC = AnalyzerSpec(
    name="dart",
    extensions=(".dart",),
    symbol_patterns=[p for p, _ in _DART_TYPED_PATTERNS],
    typed_patterns=_DART_TYPED_PATTERNS,
    strip_comments="c",
    test_cmd=["dart", "test"],
    error_patterns=[
        ("Error:", "compile_error", "Check Dart compiler error"),
        ("Failed assertion", "assertion_error", "Check assertion"),
        ("Some tests failed", "test_failure", "One or more tests failed"),
    ],
    imports=ImportSpec(
        strategy="dart_package",
        patterns=[(re.compile(r"""import\s+['\"](?:package:[\w/]+/)?([^'\"]+)['\"]"""), None)],
    ),
)

# ═══════════════════════════════════════════════════════════════════════════════
# Zig
# ═══════════════════════════════════════════════════════════════════════════════

_ZIG_TYPED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:^|\n)\s*(?:pub\s+)?fn\s+(\w+)"), "function"),
    (re.compile(r"(?:^|\n)\s*(?:pub\s+)?const\s+(\w+)\s*=\s*struct"), "struct"),
    (re.compile(r"(?:^|\n)\s*(?:pub\s+)?const\s+(\w+)\s*=\s*enum"), "enum"),
    (re.compile(r"(?:^|\n)\s*(?:pub\s+)?const\s+(\w+)\s*=\s*union"), "union"),
    (re.compile(r"(?:^|\n)\s*(?:pub\s+)?const\s+(\w+)\s*=\s*@import"), "import_const"),
    (re.compile(r"(?:^|\n)\s*(?:pub\s+)?const\s+(\w+)\s*:\s*type"), "type_alias"),
]

ZIG_SPEC = AnalyzerSpec(
    name="zig",
    extensions=(".zig",),
    symbol_patterns=[
        re.compile(r"(?:^|\n)\s*(?:pub\s+)?fn\s+(\w+)"),
        re.compile(r"(?:^|\n)\s*(?:pub\s+)?const\s+(\w+)\s*=\s*(?:struct|enum|union)"),
        re.compile(r"(?:^|\n)\s*(?:pub\s+)?const\s+(\w+)\s*=\s*@import"),
        re.compile(r"(?:^|\n)\s*(?:pub\s+)?const\s+(\w+)\s*:\s*type"),
    ],
    typed_patterns=_ZIG_TYPED_PATTERNS,
    strip_comments="c",
    test_cmd=["zig", "build", "test"],
    error_patterns=[
        ("error:", "compile_error", "Check Zig compiler error"),
        ("FAIL", "test_failure", "One or more tests failed"),
        ("panic", "runtime_error", "Check panic details"),
    ],
    imports=ImportSpec(
        strategy="zig_import",
        patterns=[(re.compile(r'@import\(\s*"([^"]+)"\s*\)'), None)],
    ),
)

# ═══════════════════════════════════════════════════════════════════════════════
# Registry
# ═══════════════════════════════════════════════════════════════════════════════

SPEC_REGISTRY: dict[str, AnalyzerSpec] = {
    "go": GO_SPEC,
    "rust": RUST_SPEC,
    "cpp": CPP_SPEC,
    "c": CPP_SPEC,
    "java": JAVA_SPEC,
    "kotlin": JAVA_SPEC,
    "csharp": CSHARP_SPEC,
    "ruby": RUBY_SPEC,
    "php": PHP_SPEC,
    "swift": SWIFT_SPEC,
    "dart": DART_SPEC,
    "zig": ZIG_SPEC,
}
