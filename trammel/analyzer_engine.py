"""RegexAnalyzerEngine — one engine, many specs, zero third-party deps."""

from __future__ import annotations

import os
import re
from typing import Any

from .analyzer_specs import AnalyzerSpec, SPEC_REGISTRY, _COMMENT_STRIPPERS
from .utils import (
    _collect_project_files,
    _collect_symbols_regex,
    _collect_typed_symbols_regex,
    _is_ignored_dir,
    _resolve_namespace_import,
    _strip_c_comments,
    _strip_hash_comments,
    _strip_php_comments,
    _walk_and_map_namespaces,
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

_GO_IMPORT_LINE_RE = re.compile(r'"([^"]+)"')
_CARGO_MEMBERS_RE = re.compile(r'members\s*=\s*\[(.*?)\]', re.DOTALL)
_CARGO_QUOTED_RE = re.compile(r'"([^"]+)"')
_CARGO_NAME_RE = re.compile(r'name\s*=\s*"([^"]+)"')
_MAVEN_SRC_DIR_RE = re.compile(r'<sourceDirectory>\s*(.*?)\s*</sourceDirectory>')


# ═══════════════════════════════════════════════════════════════════════════════
# Resolvers
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_go_imports(spec: AnalyzerSpec, project_root: str) -> dict[str, list[str]]:
    """Go import resolution via go.mod module path."""
    module_path, go_mod_dir = _read_go_mod(project_root)
    if not module_path:
        return {}
    scope_rel = os.path.relpath(project_root, go_mod_dir)
    prefix = module_path + "/"
    if scope_rel != ".":
        prefix = module_path + "/" + scope_rel.replace(os.sep, "/") + "/"

    dir_files: dict[str, list[str]] = {}
    file_sources: dict[str, str] = {}
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if not _is_ignored_dir(d)]
        rel_dir = os.path.relpath(root, project_root)
        if rel_dir == ".":
            rel_dir = ""
        go_files: list[str] = []
        for fname in files:
            if not fname.endswith(".go"):
                continue
            path = os.path.join(root, fname)
            rel = os.path.relpath(path, project_root)
            if not fname.endswith("_test.go"):
                go_files.append(rel)
            try:
                with open(path, encoding="utf-8", errors="replace") as fp:
                    file_sources[rel] = _strip_c_comments(fp.read())
            except OSError:
                continue
        if go_files:
            dir_files[rel_dir] = go_files

    graph: dict[str, list[str]] = {}
    single_re = re.compile(r'import\s+"([^"]+)"')
    block_re = re.compile(r"import\s*\((.*?)\)", re.DOTALL)
    for rel, src in file_sources.items():
        deps: set[str] = set()
        for m in single_re.finditer(src):
            deps.add(m.group(1))
        for block in block_re.finditer(src):
            for m in _GO_IMPORT_LINE_RE.finditer(block.group(1)):
                deps.add(m.group(1))
        resolved_deps: set[str] = set()
        for imp in deps:
            if not imp.startswith(prefix):
                continue
            rel_pkg = imp[len(prefix):]
            for dep_file in dir_files.get(rel_pkg, []):
                if dep_file != rel:
                    resolved_deps.add(dep_file)
        if resolved_deps:
            graph[rel] = sorted(resolved_deps)
    return graph


def _read_go_mod(project_root: str) -> tuple[str | None, str]:
    candidate = os.path.abspath(project_root)
    mod_re = re.compile(r"module\s+(\S+)")
    for _ in range(20):
        go_mod = os.path.join(candidate, "go.mod")
        if os.path.isfile(go_mod):
            try:
                with open(go_mod, encoding="utf-8") as fp:
                    m = mod_re.search(fp.read())
                    return (m.group(1), candidate) if m else (None, candidate)
            except OSError:
                return None, candidate
        parent = os.path.dirname(candidate)
        if parent == candidate:
            break
        candidate = parent
    return None, project_root


def _resolve_rust_imports(spec: AnalyzerSpec, project_root: str) -> dict[str, list[str]]:
    file_set = _collect_project_files(project_root, spec.extensions)
    workspace_crates = _read_cargo_crates(project_root)
    crate_regexes = [
        (re.compile(rf"use\s+{re.escape(name)}::(\w+(?:::\w+)*)"), cdir)
        for name, cdir in workspace_crates.items()
    ]
    graph: dict[str, list[str]] = {}
    use_crate_re = re.compile(r"use\s+crate::(\w+(?:::\w+)*)")
    use_super_re = re.compile(r"use\s+super::(\w+(?:::\w+)*)")
    use_self_re = re.compile(r"use\s+self::(\w+(?:::\w+)*)")
    mod_decl_re = re.compile(r"(?:^|\n)\s*mod\s+(\w+)\s*;")
    for rel in file_set:
        path = os.path.join(project_root, rel)
        try:
            with open(path, encoding="utf-8", errors="replace") as fp:
                src = _strip_c_comments(fp.read())
        except OSError:
            continue
        deps: set[str] = set()
        file_dir = os.path.dirname(rel)
        for m in use_crate_re.finditer(src):
            _resolve_rust_mod(m.group(1).split("::")[0], "", file_set, deps)
        for m in use_super_re.finditer(src):
            parent = os.path.dirname(file_dir) if file_dir else ""
            _resolve_rust_mod(m.group(1).split("::")[0], parent, file_set, deps)
        for m in use_self_re.finditer(src):
            _resolve_rust_mod(m.group(1).split("::")[0], file_dir, file_set, deps)
        for crate_re, crate_dir in crate_regexes:
            for m in crate_re.finditer(src):
                mod_path = m.group(1).split("::")[0]
                _resolve_rust_mod(mod_path, crate_dir, file_set, deps)
        for m in mod_decl_re.finditer(src):
            _resolve_rust_mod(m.group(1), file_dir, file_set, deps)
        deps.discard(rel)
        if deps:
            graph[rel] = sorted(deps)
    return graph


def _resolve_rust_mod(mod_name: str, base: str, file_set: set[str], deps: set[str]) -> None:
    candidates = [
        os.path.join(base, mod_name + ".rs") if base else mod_name + ".rs",
        os.path.join(base, mod_name, "mod.rs") if base else os.path.join(mod_name, "mod.rs"),
    ]
    for candidate in candidates:
        if candidate in file_set:
            deps.add(candidate)


def _read_cargo_crates(project_root: str) -> dict[str, str]:
    cargo = os.path.join(project_root, "Cargo.toml")
    crates: dict[str, str] = {}
    if not os.path.isfile(cargo):
        return crates
    try:
        with open(cargo, encoding="utf-8") as fp:
            content = fp.read()
    except OSError:
        return crates
    m = _CARGO_MEMBERS_RE.search(content)
    if not m:
        return crates
    for member_match in _CARGO_QUOTED_RE.finditer(m.group(1)):
        member_path = member_match.group(1)
        member_dir = os.path.join(project_root, member_path)
        if not os.path.isdir(member_dir):
            continue
        crate_name = os.path.basename(member_path).replace("-", "_")
        member_cargo = os.path.join(member_dir, "Cargo.toml")
        if os.path.isfile(member_cargo):
            try:
                with open(member_cargo, encoding="utf-8") as fp:
                    mc = fp.read()
                nm = _CARGO_NAME_RE.search(mc)
                if nm:
                    crate_name = nm.group(1).replace("-", "_")
            except OSError:
                pass
        src_dir = os.path.join(member_path, "src")
        crates[crate_name] = (
            src_dir
            if os.path.isdir(os.path.join(project_root, src_dir))
            else member_path
        )
    return crates


def _resolve_cpp_imports(spec: AnalyzerSpec, project_root: str) -> dict[str, list[str]]:
    file_set = _collect_project_files(project_root, spec.extensions)
    include_re = re.compile(r'#include\s+"([^"]+)"')
    graph: dict[str, list[str]] = {}
    for rel in file_set:
        path = os.path.join(project_root, rel)
        try:
            with open(path, encoding="utf-8", errors="replace") as fp:
                src = _strip_c_comments(fp.read())
        except OSError:
            continue
        deps: set[str] = set()
        for m in include_re.finditer(src):
            include_path = m.group(1)
            base_dir = os.path.dirname(rel)
            for base in (base_dir, ""):
                candidate = os.path.normpath(os.path.join(base, include_path)) if base else include_path
                if candidate in file_set and candidate != rel:
                    deps.add(candidate)
                    break
        if deps:
            graph[rel] = sorted(deps)
    return graph


def _resolve_java_imports(spec: AnalyzerSpec, project_root: str) -> dict[str, list[str]]:
    extra = spec.imports.extra if spec.imports else {}
    namespace_re = extra.get("namespace_re")
    source_roots = _detect_java_source_roots(project_root)
    pkg_to_files, file_sources = _walk_and_map_namespaces(
        project_root, spec.extensions, namespace_re, _strip_c_comments, source_roots=source_roots,
    )
    import_re = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)", re.MULTILINE)
    graph: dict[str, list[str]] = {}
    for rel, src in file_sources.items():
        deps: set[str] = set()
        for m in import_re.finditer(src):
            _resolve_namespace_import(m.group(1), pkg_to_files, rel, deps)
        if not deps:
            m = namespace_re.search(src)
            if m:
                for sibling in pkg_to_files.get(m.group(1), []):
                    if sibling != rel:
                        deps.add(sibling)
        if deps:
            graph[rel] = sorted(deps)
    return graph


def _detect_java_source_roots(project_root: str) -> list[str]:
    roots: list[str] = []
    for gradle_file in ("build.gradle", "build.gradle.kts"):
        if os.path.isfile(os.path.join(project_root, gradle_file)):
            for candidate in (
                "src/main/java", "src/main/kotlin",
                "src/test/java", "src/test/kotlin",
            ):
                full = os.path.join(project_root, candidate)
                if os.path.isdir(full):
                    roots.append(full)
            break
    if not roots:
        pom = os.path.join(project_root, "pom.xml")
        if os.path.isfile(pom):
            try:
                with open(pom, encoding="utf-8", errors="replace") as fp:
                    pom_text = fp.read()
                m = _MAVEN_SRC_DIR_RE.search(pom_text)
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
    if not roots:
        roots.append(project_root)
    return roots


def _resolve_csharp_imports(spec: AnalyzerSpec, project_root: str) -> dict[str, list[str]]:
    extra = spec.imports.extra if spec.imports else {}
    namespace_re = extra.get("namespace_re")
    using_re = re.compile(r"^\s*using\s+([\w.]+)\s*;", re.MULTILINE)
    ns_to_files, file_sources = _walk_and_map_namespaces(
        project_root, spec.extensions, namespace_re, _strip_c_comments,
    )
    graph: dict[str, list[str]] = {}
    for rel, src in file_sources.items():
        deps: set[str] = set()
        for m in using_re.finditer(src):
            _resolve_namespace_import(m.group(1), ns_to_files, rel, deps)
        if deps:
            graph[rel] = sorted(deps)
    return graph


def _resolve_ruby_imports(spec: AnalyzerSpec, project_root: str) -> dict[str, list[str]]:
    file_set = _collect_project_files(project_root, spec.extensions)
    stem_to_file: dict[str, str] = {}
    basename_to_file: dict[str, str] = {}
    for rel in sorted(file_set):
        stem = rel.removesuffix(".rb")
        stem_to_file[stem] = rel
        basename_to_file.setdefault(os.path.basename(stem), rel)
    require_re = re.compile(r"""require(?:_relative)?\s+['"]([^'"]+)['"]""")
    graph: dict[str, list[str]] = {}
    for rel in file_set:
        path = os.path.join(project_root, rel)
        try:
            with open(path, encoding="utf-8", errors="replace") as fp:
                src = _strip_hash_comments(fp.read())
        except OSError:
            continue
        deps: set[str] = set()
        for m in require_re.finditer(src):
            req = m.group(1)
            resolved = stem_to_file.get(req) or basename_to_file.get(req)
            if resolved and resolved != rel:
                deps.add(resolved)
        if deps:
            graph[rel] = sorted(deps)
    return graph


def _resolve_php_imports(spec: AnalyzerSpec, project_root: str) -> dict[str, list[str]]:
    extra = spec.imports.extra if spec.imports else {}
    namespace_re = extra.get("namespace_re")
    ns_to_files, file_sources = _walk_and_map_namespaces(
        project_root, spec.extensions, namespace_re, _strip_php_comments,
    )
    dot_ns_to_files = {ns.replace("\\", "."): files for ns, files in ns_to_files.items()}
    use_re = re.compile(r"^\s*use\s+([\w\\\\]+)\s*;", re.MULTILINE)
    use_group_re = re.compile(r"^\s*use\s+([\w\\\\]+)\\\{([^}]+)\}", re.MULTILINE)
    graph: dict[str, list[str]] = {}
    for rel, src in file_sources.items():
        deps: set[str] = set()
        use_paths = [m.group(1) for m in use_re.finditer(src)]
        for m in use_group_re.finditer(src):
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


def _resolve_swift_imports(spec: AnalyzerSpec, project_root: str) -> dict[str, list[str]]:
    file_set = _collect_project_files(project_root, spec.extensions)
    module_to_files = _build_swift_module_map(project_root, file_set)
    import_re = re.compile(r"^\s*import\s+(\w+)", re.MULTILINE)
    graph: dict[str, list[str]] = {}
    for rel in file_set:
        path = os.path.join(project_root, rel)
        try:
            with open(path, encoding="utf-8", errors="replace") as fp:
                src = _strip_c_comments(fp.read())
        except OSError:
            continue
        deps: set[str] = set()
        for m in import_re.finditer(src):
            mod = m.group(1)
            for dep in module_to_files.get(mod, []):
                if dep != rel:
                    deps.add(dep)
        if deps:
            graph[rel] = sorted(deps)
    return graph


def _build_swift_module_map(project_root: str, file_set: set[str]) -> dict[str, list[str]]:
    module_to_files: dict[str, list[str]] = {}
    for dirname in ("Sources", "Tests"):
        full_dir = os.path.join(project_root, dirname)
        if not os.path.isdir(full_dir):
            continue
        try:
            for entry in os.listdir(full_dir):
                if os.path.isdir(os.path.join(full_dir, entry)):
                    norm_prefix = os.path.join(dirname, entry).replace(os.sep, "/") + "/"
                    mod_files = [f for f in file_set if f.replace(os.sep, "/").startswith(norm_prefix)]
                    if mod_files:
                        module_to_files[entry] = mod_files
        except OSError:
            pass
    if not module_to_files:
        for rel in file_set:
            parts = rel.replace(os.sep, "/").split("/")
            if len(parts) >= 2:
                module_to_files.setdefault(parts[-2], []).append(rel)
    return module_to_files


def _resolve_dart_imports(spec: AnalyzerSpec, project_root: str) -> dict[str, list[str]]:
    file_set = _collect_project_files(project_root, spec.extensions)
    import_re = re.compile(r"""import\s+['\"](?:package:[\w/]+/)?([^'\"]+)['\"]""")
    graph: dict[str, list[str]] = {}
    for rel in file_set:
        path = os.path.join(project_root, rel)
        try:
            with open(path, encoding="utf-8", errors="replace") as fp:
                src = _strip_c_comments(fp.read())
        except OSError:
            continue
        deps: set[str] = set()
        for m in import_re.finditer(src):
            import_path = m.group(1)
            if import_path in file_set and import_path != rel:
                deps.add(import_path)
            else:
                base = os.path.normpath(os.path.join(os.path.dirname(rel), import_path))
                if base in file_set and base != rel:
                    deps.add(base)
        if deps:
            graph[rel] = sorted(deps)
    return graph


def _resolve_zig_imports(spec: AnalyzerSpec, project_root: str) -> dict[str, list[str]]:
    file_set = _collect_project_files(project_root, spec.extensions)
    import_re = re.compile(r'@import\(\s*"([^"]+)"\s*\)')
    graph: dict[str, list[str]] = {}
    for rel in file_set:
        path = os.path.join(project_root, rel)
        try:
            with open(path, encoding="utf-8", errors="replace") as fp:
                src = _strip_c_comments(fp.read())
        except OSError:
            continue
        deps: set[str] = set()
        for m in import_re.finditer(src):
            import_path = m.group(1)
            if import_path.endswith(".zig"):
                base = os.path.normpath(os.path.join(os.path.dirname(rel), import_path))
                if base in file_set and base != rel:
                    deps.add(base)
        if deps:
            graph[rel] = sorted(deps)
    return graph


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
    _default_spec = SPEC_REGISTRY["go"]
    name = _default_spec.name
    extensions = _default_spec.extensions


class RustAnalyzer(RegexAnalyzerEngine):
    _default_spec = SPEC_REGISTRY["rust"]
    name = _default_spec.name
    extensions = _default_spec.extensions


class CppAnalyzer(RegexAnalyzerEngine):
    _default_spec = SPEC_REGISTRY["cpp"]
    name = _default_spec.name
    extensions = _default_spec.extensions


class JavaAnalyzer(RegexAnalyzerEngine):
    _default_spec = SPEC_REGISTRY["java"]
    name = _default_spec.name
    extensions = _default_spec.extensions
    _detect_source_roots = staticmethod(_detect_java_source_roots)


class CSharpAnalyzer(RegexAnalyzerEngine):
    _default_spec = SPEC_REGISTRY["csharp"]
    name = _default_spec.name
    extensions = _default_spec.extensions


class RubyAnalyzer(RegexAnalyzerEngine):
    _default_spec = SPEC_REGISTRY["ruby"]
    name = _default_spec.name
    extensions = _default_spec.extensions


class PhpAnalyzer(RegexAnalyzerEngine):
    _default_spec = SPEC_REGISTRY["php"]
    name = _default_spec.name
    extensions = _default_spec.extensions


class SwiftAnalyzer(RegexAnalyzerEngine):
    _default_spec = SPEC_REGISTRY["swift"]
    name = _default_spec.name
    extensions = _default_spec.extensions


class DartAnalyzer(RegexAnalyzerEngine):
    _default_spec = SPEC_REGISTRY["dart"]
    name = _default_spec.name
    extensions = _default_spec.extensions


class ZigAnalyzer(RegexAnalyzerEngine):
    _default_spec = SPEC_REGISTRY["zig"]
    name = _default_spec.name
    extensions = _default_spec.extensions
