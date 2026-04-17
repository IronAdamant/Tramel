"""RegexAnalyzerEngine — one engine, many specs, zero third-party deps."""

from __future__ import annotations

import os
import re
from typing import Any

from .analyzer_resolvers import (
    _detect_java_source_roots,
    _resolve_cpp_imports,
    _resolve_csharp_imports,
    _resolve_dart_imports,
    _resolve_go_imports,
    _resolve_java_imports,
    _resolve_php_imports,
    _resolve_ruby_imports,
    _resolve_rust_imports,
    _resolve_swift_imports,
    _resolve_zig_imports,
)
from .analyzer_specs import AnalyzerSpec, SPEC_REGISTRY, _COMMENT_STRIPPERS
from .utils import (
    _collect_project_files,
    _collect_symbols_regex,
    _collect_typed_symbols_regex,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Engine
# ═══════════════════════════════════════════════════════════════════════════════

class RegexAnalyzerEngine:
    """Generic regex-driven analyzer backed by a declarative spec."""

    _default_spec: AnalyzerSpec | None = None

    def __init__(self, spec: AnalyzerSpec | None = None) -> None:
        self.spec = spec or self._default_spec
        if self.spec is None:
            raise ValueError("RegexAnalyzerEngine requires a spec")

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def extensions(self) -> tuple[str, ...]:
        return self.spec.extensions

    def _stripper(self) -> Any:
        return _COMMENT_STRIPPERS[self.spec.strip_comments]

    def collect_symbols(self, project_root: str) -> dict[str, list[str]]:
        return _collect_symbols_regex(
            project_root,
            self.spec.extensions,
            self.spec.symbol_patterns,
            self._stripper(),
        )

    def collect_typed_symbols(self, project_root: str) -> dict[str, list[tuple[str, str]]]:
        return _collect_typed_symbols_regex(
            project_root,
            self.spec.extensions,
            self.spec.typed_patterns,
            self._stripper(),
        )

    def analyze_imports(self, project_root: str) -> dict[str, list[str]]:
        if self.spec.imports is None:
            return {}
        strategy = self.spec.imports.strategy
        fn = _IMPORT_RESOLVERS.get(strategy)
        if fn is None:
            return {}
        return fn(self.spec, project_root)

    def pick_test_cmd(self, project_root: str) -> list[str]:
        tc = self.spec.test_cmd
        if callable(tc):
            return tc(project_root)
        return list(tc)

    def error_patterns(self) -> list[tuple[str, str, str]]:
        return list(self.spec.error_patterns)


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: compile block-line regex lazily
# ═══════════════════════════════════════════════════════════════════════════════




_IMPORT_RESOLVERS: dict[str, Any] = {
    "go_mod": _resolve_go_imports,
    "rust_crate": _resolve_rust_imports,
    "cpp_include": _resolve_cpp_imports,
    "java_namespace": _resolve_java_imports,
    "csharp_namespace": _resolve_csharp_imports,
    "ruby_require": _resolve_ruby_imports,
    "php_namespace": _resolve_php_imports,
    "swift_module": _resolve_swift_imports,
    "dart_package": _resolve_dart_imports,
    "zig_import": _resolve_zig_imports,
}


# ═══════════════════════════════════════════════════════════════════════════════
# Backward-compatible class shims
# ═══════════════════════════════════════════════════════════════════════════════

class GoAnalyzer(RegexAnalyzerEngine):
    """Go analyzer: regex-driven symbol/import extraction from the 'go' spec."""
    _default_spec = SPEC_REGISTRY["go"]
    name = _default_spec.name
    extensions = _default_spec.extensions


class RustAnalyzer(RegexAnalyzerEngine):
    """Rust analyzer: regex-driven symbol/import extraction from the 'rust' spec."""
    _default_spec = SPEC_REGISTRY["rust"]
    name = _default_spec.name
    extensions = _default_spec.extensions


class CppAnalyzer(RegexAnalyzerEngine):
    """C/C++ analyzer: regex-driven symbol/include extraction from the 'cpp' spec."""
    _default_spec = SPEC_REGISTRY["cpp"]
    name = _default_spec.name
    extensions = _default_spec.extensions


class JavaAnalyzer(RegexAnalyzerEngine):
    """Java analyzer: regex-driven symbol/import extraction plus source-root detection."""
    _default_spec = SPEC_REGISTRY["java"]
    name = _default_spec.name
    extensions = _default_spec.extensions
    _detect_source_roots = staticmethod(_detect_java_source_roots)


class CSharpAnalyzer(RegexAnalyzerEngine):
    """C# analyzer: regex-driven symbol/using extraction from the 'csharp' spec."""
    _default_spec = SPEC_REGISTRY["csharp"]
    name = _default_spec.name
    extensions = _default_spec.extensions


class RubyAnalyzer(RegexAnalyzerEngine):
    """Ruby analyzer: regex-driven symbol/require extraction from the 'ruby' spec."""
    _default_spec = SPEC_REGISTRY["ruby"]
    name = _default_spec.name
    extensions = _default_spec.extensions


class PhpAnalyzer(RegexAnalyzerEngine):
    """PHP analyzer: regex-driven symbol/use extraction from the 'php' spec."""
    _default_spec = SPEC_REGISTRY["php"]
    name = _default_spec.name
    extensions = _default_spec.extensions


class SwiftAnalyzer(RegexAnalyzerEngine):
    """Swift analyzer: regex-driven symbol/import extraction from the 'swift' spec."""
    _default_spec = SPEC_REGISTRY["swift"]
    name = _default_spec.name
    extensions = _default_spec.extensions


class DartAnalyzer(RegexAnalyzerEngine):
    """Dart analyzer: regex-driven symbol/import extraction from the 'dart' spec."""
    _default_spec = SPEC_REGISTRY["dart"]
    name = _default_spec.name
    extensions = _default_spec.extensions


class ZigAnalyzer(RegexAnalyzerEngine):
    """Zig analyzer: regex-driven symbol/@import extraction from the 'zig' spec."""
    _default_spec = SPEC_REGISTRY["zig"]
    name = _default_spec.name
    extensions = _default_spec.extensions
