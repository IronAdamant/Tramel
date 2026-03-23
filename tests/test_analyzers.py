"""Tests for language analyzers: PythonAnalyzer, TypeScriptAnalyzer, detection."""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trammel.analyzers import (  # noqa: E402
    CppAnalyzer,
    GoAnalyzer,
    JavaAnalyzer,
    PythonAnalyzer,
    RustAnalyzer,
    TypeScriptAnalyzer,
    detect_language,
)
from trammel.analyzers_ext2 import (  # noqa: E402
    CSharpAnalyzer, DartAnalyzer, PhpAnalyzer,
    RubyAnalyzer, SwiftAnalyzer, ZigAnalyzer,
)


# ── PythonAnalyzer ───────────────────────────────────────────────────────────

class TestPythonAnalyzer(unittest.TestCase):
    def test_collect_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "mod.py").write_text(
                "def foo():\n    pass\n\nclass Bar:\n    pass\n", encoding="utf-8",
            )
            analyzer = PythonAnalyzer()
            symbols = analyzer.collect_symbols(d)
            self.assertIn("mod.py", symbols)
            self.assertEqual(sorted(symbols["mod.py"]), ["Bar", "foo"])

    def test_analyze_imports(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pkg = pathlib.Path(d) / "pkg"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("", encoding="utf-8")
            (pkg / "a.py").write_text("X = 1\n", encoding="utf-8")
            (pkg / "b.py").write_text("from pkg.a import X\n", encoding="utf-8")
            analyzer = PythonAnalyzer()
            graph = analyzer.analyze_imports(d)
            b_deps = graph.get(os.path.join("pkg", "b.py"), [])
            self.assertIn(os.path.join("pkg", "a.py"), b_deps)

    def test_pick_test_cmd(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            analyzer = PythonAnalyzer()
            cmd = analyzer.pick_test_cmd(d)
            self.assertIn("unittest", cmd)

    def test_error_patterns(self) -> None:
        analyzer = PythonAnalyzer()
        patterns = analyzer.error_patterns()
        markers = [p[0] for p in patterns]
        self.assertIn("ImportError", markers)
        self.assertIn("SyntaxError", markers)


# ── TypeScriptAnalyzer ───────────────────────────────────────────────────────

class TestTypeScriptAnalyzer(unittest.TestCase):
    def test_collect_symbols_ts(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "utils.ts").write_text(
                "export function greet(name: string): string {\n"
                "  return `Hello ${name}`;\n"
                "}\n"
                "\n"
                "export class Logger {\n"
                "  log(msg: string) { console.log(msg); }\n"
                "}\n"
                "\n"
                "const helper = (x: number) => x * 2;\n",
                encoding="utf-8",
            )
            analyzer = TypeScriptAnalyzer()
            symbols = analyzer.collect_symbols(d)
            self.assertIn("utils.ts", symbols)
            names = symbols["utils.ts"]
            self.assertIn("greet", names)
            self.assertIn("Logger", names)
            self.assertIn("helper", names)

    def test_analyze_imports_ts(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "utils.ts").write_text(
                "export function greet() { return 'hi'; }\n", encoding="utf-8",
            )
            pathlib.Path(d, "main.ts").write_text(
                "import { greet } from './utils';\nconsole.log(greet());\n",
                encoding="utf-8",
            )
            analyzer = TypeScriptAnalyzer()
            graph = analyzer.analyze_imports(d)
            self.assertIn("main.ts", graph)
            self.assertIn("utils.ts", graph["main.ts"])

    def test_analyze_imports_js_extension(self) -> None:
        """TS files importing with .js extension (modern TS convention)."""
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "utils.ts").write_text(
                "export function greet() { return 'hi'; }\n", encoding="utf-8",
            )
            pathlib.Path(d, "main.ts").write_text(
                "import { greet } from './utils.js';\nconsole.log(greet());\n",
                encoding="utf-8",
            )
            analyzer = TypeScriptAnalyzer()
            graph = analyzer.analyze_imports(d)
            self.assertIn("main.ts", graph)
            self.assertIn("utils.ts", graph["main.ts"])

    def test_pick_test_cmd_with_package_json(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "package.json").write_text(
                json.dumps({"scripts": {"test": "jest"}}), encoding="utf-8",
            )
            analyzer = TypeScriptAnalyzer()
            cmd = analyzer.pick_test_cmd(d)
            self.assertEqual(cmd, ["npm", "test"])

    def test_error_patterns(self) -> None:
        analyzer = TypeScriptAnalyzer()
        patterns = analyzer.error_patterns()
        markers = [p[0] for p in patterns]
        self.assertIn("TypeError", markers)
        self.assertIn("Cannot find module", markers)

    def test_collect_symbols_interface(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "types.ts").write_text(
                "export interface UserProps {\n  name: string;\n}\n", encoding="utf-8",
            )
            symbols = TypeScriptAnalyzer().collect_symbols(d)
            self.assertIn("UserProps", symbols.get("types.ts", []))

    def test_collect_symbols_enum(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "colors.ts").write_text(
                "export enum Color {\n  Red,\n  Green,\n  Blue\n}\n", encoding="utf-8",
            )
            symbols = TypeScriptAnalyzer().collect_symbols(d)
            self.assertIn("Color", symbols.get("colors.ts", []))

    def test_collect_symbols_const_enum(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "dir.ts").write_text(
                "export const enum Direction {\n  Up,\n  Down\n}\n", encoding="utf-8",
            )
            symbols = TypeScriptAnalyzer().collect_symbols(d)
            self.assertIn("Direction", symbols.get("dir.ts", []))

    def test_collect_symbols_type_alias(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "types.ts").write_text(
                "export type ID = string | number;\n", encoding="utf-8",
            )
            symbols = TypeScriptAnalyzer().collect_symbols(d)
            self.assertIn("ID", symbols.get("types.ts", []))

    def test_collect_symbols_abstract_class(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "base.ts").write_text(
                "export abstract class Base {\n  abstract run(): void;\n}\n", encoding="utf-8",
            )
            symbols = TypeScriptAnalyzer().collect_symbols(d)
            self.assertIn("Base", symbols.get("base.ts", []))

    def test_collect_symbols_decorated_class(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "comp.ts").write_text(
                "@Component({selector: 'app'})\nexport class MyComponent {\n}\n", encoding="utf-8",
            )
            symbols = TypeScriptAnalyzer().collect_symbols(d)
            self.assertIn("MyComponent", symbols.get("comp.ts", []))

    def test_collect_symbols_function_expression(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "handler.ts").write_text(
                "export const handler = function(req: Request) {\n  return null;\n}\n", encoding="utf-8",
            )
            symbols = TypeScriptAnalyzer().collect_symbols(d)
            self.assertIn("handler", symbols.get("handler.ts", []))

    def test_import_reexport(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "utils.ts").write_text(
                "export function greet() { return 'hi'; }\n", encoding="utf-8",
            )
            pathlib.Path(d, "index.ts").write_text(
                "export { greet } from './utils';\n", encoding="utf-8",
            )
            graph = TypeScriptAnalyzer().analyze_imports(d)
            self.assertIn("index.ts", graph)
            self.assertIn("utils.ts", graph["index.ts"])

    def test_import_barrel_export(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "models.ts").write_text(
                "export class User {}\n", encoding="utf-8",
            )
            pathlib.Path(d, "index.ts").write_text(
                "export * from './models';\n", encoding="utf-8",
            )
            graph = TypeScriptAnalyzer().analyze_imports(d)
            self.assertIn("index.ts", graph)
            self.assertIn("models.ts", graph["index.ts"])

    def test_import_dynamic(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "lazy.ts").write_text(
                "export function load() { return 42; }\n", encoding="utf-8",
            )
            pathlib.Path(d, "main.ts").write_text(
                "const mod = import('./lazy');\n", encoding="utf-8",
            )
            graph = TypeScriptAnalyzer().analyze_imports(d)
            self.assertIn("main.ts", graph)
            self.assertIn("lazy.ts", graph["main.ts"])

    def test_import_type_reexport(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "types.ts").write_text(
                "export interface Foo { x: number; }\n", encoding="utf-8",
            )
            pathlib.Path(d, "index.ts").write_text(
                "export type { Foo } from './types';\n", encoding="utf-8",
            )
            graph = TypeScriptAnalyzer().analyze_imports(d)
            self.assertIn("index.ts", graph)
            self.assertIn("types.ts", graph["index.ts"])

    def test_mts_mjs_collected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "mod.mts").write_text(
                "export function mtsFunc() {}\n", encoding="utf-8",
            )
            pathlib.Path(d, "util.mjs").write_text(
                "export function mjsFunc() {}\n", encoding="utf-8",
            )
            symbols = TypeScriptAnalyzer().collect_symbols(d)
            self.assertIn("mtsFunc", symbols.get("mod.mts", []))
            self.assertIn("mjsFunc", symbols.get("util.mjs", []))


# ── Detection ────────────────────────────────────────────────────────────────

class TestDetectLanguage(unittest.TestCase):
    def test_python_project(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "a.py").write_text("", encoding="utf-8")
            pathlib.Path(d, "b.py").write_text("", encoding="utf-8")
            analyzer = detect_language(d)
            self.assertEqual(analyzer.name, "python")

    def test_typescript_project(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "a.ts").write_text("", encoding="utf-8")
            pathlib.Path(d, "b.ts").write_text("", encoding="utf-8")
            pathlib.Path(d, "c.tsx").write_text("", encoding="utf-8")
            analyzer = detect_language(d)
            self.assertEqual(analyzer.name, "typescript")

    def test_mixed_project(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "a.py").write_text("", encoding="utf-8")
            pathlib.Path(d, "b.ts").write_text("", encoding="utf-8")
            pathlib.Path(d, "c.ts").write_text("", encoding="utf-8")
            analyzer = detect_language(d)
            self.assertEqual(analyzer.name, "typescript")

    def test_empty_project_defaults_python(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            analyzer = detect_language(d)
            self.assertEqual(analyzer.name, "python")


# ── TsConfig ─────────────────────────────────────────────────────────────────

class TestTsConfig(unittest.TestCase):
    def test_tsconfig_path_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            src = pathlib.Path(d) / "src"
            src.mkdir()
            (src / "utils.ts").write_text(
                "export function helper() { return 1; }\n", encoding="utf-8",
            )
            pathlib.Path(d, "main.ts").write_text(
                "import { helper } from '@/utils';\nconsole.log(helper());\n",
                encoding="utf-8",
            )
            pathlib.Path(d, "tsconfig.json").write_text(
                json.dumps({
                    "compilerOptions": {
                        "baseUrl": ".",
                        "paths": {"@/*": ["src/*"]}
                    }
                }),
                encoding="utf-8",
            )
            graph = TypeScriptAnalyzer().analyze_imports(d)
            self.assertIn("main.ts", graph)
            self.assertIn(os.path.join("src", "utils.ts"), graph["main.ts"])

    def test_tsconfig_missing_graceful(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "utils.ts").write_text(
                "export function greet() { return 'hi'; }\n", encoding="utf-8",
            )
            pathlib.Path(d, "main.ts").write_text(
                "import { greet } from './utils';\n", encoding="utf-8",
            )
            # No tsconfig.json — should still work for relative imports
            graph = TypeScriptAnalyzer().analyze_imports(d)
            self.assertIn("main.ts", graph)
            self.assertIn("utils.ts", graph["main.ts"])

    def test_tsconfig_invalid_json_graceful(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "utils.ts").write_text(
                "export function greet() { return 'hi'; }\n", encoding="utf-8",
            )
            pathlib.Path(d, "main.ts").write_text(
                "import { greet } from './utils';\n", encoding="utf-8",
            )
            pathlib.Path(d, "tsconfig.json").write_text("not json!", encoding="utf-8")
            graph = TypeScriptAnalyzer().analyze_imports(d)
            self.assertIn("main.ts", graph)


# ── GoAnalyzer ────────────────────────────────────────────────────────────────

class TestGoAnalyzer(unittest.TestCase):
    def test_collect_symbols_go(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "main.go").write_text(
                "package main\n\n"
                "func Greet() {}\n\n"
                "type Server struct {}\n",
                encoding="utf-8",
            )
            analyzer = GoAnalyzer()
            symbols = analyzer.collect_symbols(d)
            self.assertIn("main.go", symbols)
            self.assertIn("Greet", symbols["main.go"])
            self.assertIn("Server", symbols["main.go"])

    def test_analyze_imports_go(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "go.mod").write_text(
                "module example.com/proj\n\ngo 1.21\n", encoding="utf-8",
            )
            pkg = pathlib.Path(d) / "pkg"
            pkg.mkdir()
            (pkg / "utils.go").write_text(
                "package pkg\n\nfunc Helper() {}\n", encoding="utf-8",
            )
            pathlib.Path(d, "main.go").write_text(
                'package main\n\nimport "example.com/proj/pkg"\n\n'
                "func main() { pkg.Helper() }\n",
                encoding="utf-8",
            )
            analyzer = GoAnalyzer()
            graph = analyzer.analyze_imports(d)
            main_deps = graph.get("main.go", [])
            self.assertTrue(
                any("pkg" in dep for dep in main_deps),
                f"Expected pkg dependency in main.go deps: {main_deps}",
            )

    def test_pick_test_cmd_go(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            analyzer = GoAnalyzer()
            cmd = analyzer.pick_test_cmd(d)
            self.assertEqual(cmd, ["go", "test", "./..."])

    def test_error_patterns_go(self) -> None:
        analyzer = GoAnalyzer()
        patterns = analyzer.error_patterns()
        markers = [p[0] for p in patterns]
        self.assertIn("FAIL", markers)


# ── RustAnalyzer ──────────────────────────────────────────────────────────────

class TestRustAnalyzer(unittest.TestCase):
    def test_collect_symbols_rust(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "lib.rs").write_text(
                "fn greet() {}\n\n"
                "pub struct Server {}\n\n"
                "enum Color { Red, Green, Blue }\n",
                encoding="utf-8",
            )
            analyzer = RustAnalyzer()
            symbols = analyzer.collect_symbols(d)
            self.assertIn("lib.rs", symbols)
            self.assertIn("greet", symbols["lib.rs"])
            self.assertIn("Server", symbols["lib.rs"])
            self.assertIn("Color", symbols["lib.rs"])

    def test_analyze_imports_rust(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "lib.rs").write_text(
                "mod utils;\n", encoding="utf-8",
            )
            pathlib.Path(d, "utils.rs").write_text(
                "pub fn helper() {}\n", encoding="utf-8",
            )
            analyzer = RustAnalyzer()
            graph = analyzer.analyze_imports(d)
            lib_deps = graph.get("lib.rs", [])
            self.assertTrue(
                any("utils" in dep for dep in lib_deps),
                f"Expected utils dependency in lib.rs deps: {lib_deps}",
            )

    def test_pick_test_cmd_rust(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            analyzer = RustAnalyzer()
            cmd = analyzer.pick_test_cmd(d)
            self.assertEqual(cmd, ["cargo", "test"])


# ── TS Enhancements ──────────────────────────────────────────────────────────

class TestTSEnhancements(unittest.TestCase):
    def test_namespace_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "api.ts").write_text(
                "export namespace API {\n"
                "  export function getUser() { return null; }\n"
                "}\n",
                encoding="utf-8",
            )
            symbols = TypeScriptAnalyzer().collect_symbols(d)
            self.assertIn("API", symbols.get("api.ts", []))

    def test_commented_import_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "utils.ts").write_text(
                "export function foo() { return 1; }\n", encoding="utf-8",
            )
            pathlib.Path(d, "main.ts").write_text(
                "// import { foo } from './utils'\n", encoding="utf-8",
            )
            graph = TypeScriptAnalyzer().analyze_imports(d)
            self.assertNotIn("main.ts", graph)


# ── Detection (expanded) ─────────────────────────────────────────────────────

class TestDetectLanguageExpanded(unittest.TestCase):
    def test_go_project(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "main.go").write_text("", encoding="utf-8")
            pathlib.Path(d, "server.go").write_text("", encoding="utf-8")
            pathlib.Path(d, "handler.go").write_text("", encoding="utf-8")
            analyzer = detect_language(d)
            self.assertEqual(analyzer.name, "go")

    def test_rust_project(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "main.rs").write_text("", encoding="utf-8")
            pathlib.Path(d, "lib.rs").write_text("", encoding="utf-8")
            pathlib.Path(d, "utils.rs").write_text("", encoding="utf-8")
            analyzer = detect_language(d)
            self.assertEqual(analyzer.name, "rust")


# ── CppAnalyzer ──────────────────────────────────────────────────────────────

class TestCppAnalyzer(unittest.TestCase):
    def test_collect_symbols_cpp(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "main.cpp").write_text(
                "class Server {};\n\n"
                "struct Config {};\n\n"
                "namespace Net {\n  int init() { return 0; }\n}\n\n"
                "enum class Color { Red, Green };\n",
                encoding="utf-8",
            )
            symbols = CppAnalyzer().collect_symbols(d)
            self.assertIn("main.cpp", symbols)
            names = symbols["main.cpp"]
            self.assertIn("Server", names)
            self.assertIn("Config", names)
            self.assertIn("Net", names)
            self.assertIn("Color", names)

    def test_header_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "types.h").write_text(
                "struct Point { int x; int y; };\n", encoding="utf-8",
            )
            symbols = CppAnalyzer().collect_symbols(d)
            self.assertIn("types.h", symbols)
            self.assertIn("Point", symbols["types.h"])

    def test_analyze_imports_cpp(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "utils.h").write_text(
                "int helper();\n", encoding="utf-8",
            )
            pathlib.Path(d, "main.cpp").write_text(
                '#include "utils.h"\n\nint main() { return helper(); }\n',
                encoding="utf-8",
            )
            graph = CppAnalyzer().analyze_imports(d)
            self.assertIn("main.cpp", graph)
            self.assertIn("utils.h", graph["main.cpp"])

    def test_pick_test_cmd_cmake(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "CMakeLists.txt").write_text("", encoding="utf-8")
            cmd = CppAnalyzer().pick_test_cmd(d)
            self.assertIn("ctest", cmd)

    def test_error_patterns_cpp(self) -> None:
        markers = [p[0] for p in CppAnalyzer().error_patterns()]
        self.assertIn("error:", markers)

    def test_commented_include_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "utils.h").write_text("int x;\n", encoding="utf-8")
            pathlib.Path(d, "main.cpp").write_text(
                '// #include "utils.h"\nint main() {}\n', encoding="utf-8",
            )
            graph = CppAnalyzer().analyze_imports(d)
            self.assertNotIn("main.cpp", graph)

    def test_template_function(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "tmpl.hpp").write_text(
                "template<typename T>\nT process(T val) { return val; }\n",
                encoding="utf-8",
            )
            symbols = CppAnalyzer().collect_symbols(d)
            self.assertIn("process", symbols.get("tmpl.hpp", []))

    def test_qualified_function(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "qual.cpp").write_text(
                "static inline constexpr int compute(int x) { return x; }\n",
                encoding="utf-8",
            )
            symbols = CppAnalyzer().collect_symbols(d)
            self.assertIn("compute", symbols.get("qual.cpp", []))

    def test_operator_overloading(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "ops.cpp").write_text(
                "struct Foo {};\n"
                "bool operator==(const Foo& a, const Foo& b) { return true; }\n",
                encoding="utf-8",
            )
            symbols = CppAnalyzer().collect_symbols(d)
            names = symbols.get("ops.cpp", [])
            self.assertTrue(any("operator" in n for n in names))

    def test_macro_prefixed_function(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "api.cpp").write_text(
                "EXPORT_API void exported_func() {}\n", encoding="utf-8",
            )
            symbols = CppAnalyzer().collect_symbols(d)
            self.assertIn("exported_func", symbols.get("api.cpp", []))


# ── JavaAnalyzer ─────────────────────────────────────────────────────────────

class TestJavaAnalyzer(unittest.TestCase):
    def test_collect_symbols_java(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "App.java").write_text(
                "package com.example;\n\n"
                "public class App {\n"
                "  public interface Service {}\n"
                "  public enum Status { OK, ERR }\n"
                "}\n",
                encoding="utf-8",
            )
            symbols = JavaAnalyzer().collect_symbols(d)
            self.assertIn("App.java", symbols)
            names = symbols["App.java"]
            self.assertIn("App", names)
            self.assertIn("Service", names)
            self.assertIn("Status", names)

    def test_collect_symbols_kotlin(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "Main.kt").write_text(
                "package com.example\n\n"
                "data class User(val name: String)\n\n"
                "fun greet(u: User): String = \"Hello ${u.name}\"\n\n"
                "object Config {}\n",
                encoding="utf-8",
            )
            symbols = JavaAnalyzer().collect_symbols(d)
            self.assertIn("Main.kt", symbols)
            names = symbols["Main.kt"]
            self.assertIn("User", names)
            self.assertIn("greet", names)
            self.assertIn("Config", names)

    def test_analyze_imports_java(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pkg = pathlib.Path(d) / "com" / "example"
            pkg.mkdir(parents=True)
            (pkg / "Utils.java").write_text(
                "package com.example;\n\npublic class Utils {}\n", encoding="utf-8",
            )
            (pkg / "App.java").write_text(
                "package com.example;\n\nimport com.example.Utils;\n\n"
                "public class App {}\n",
                encoding="utf-8",
            )
            graph = JavaAnalyzer().analyze_imports(d)
            app_key = os.path.join("com", "example", "App.java")
            utils_key = os.path.join("com", "example", "Utils.java")
            self.assertIn(app_key, graph)
            self.assertIn(utils_key, graph[app_key])

    def test_pick_test_cmd_gradle(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")
            cmd = JavaAnalyzer().pick_test_cmd(d)
            self.assertIn("gradlew", cmd[0])

    def test_pick_test_cmd_maven(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "pom.xml").write_text("<project/>", encoding="utf-8")
            cmd = JavaAnalyzer().pick_test_cmd(d)
            self.assertEqual(cmd, ["mvn", "test"])

    def test_error_patterns_java(self) -> None:
        markers = [p[0] for p in JavaAnalyzer().error_patterns()]
        self.assertIn("FAILURE", markers)

    def test_maven_source_root(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "pom.xml").write_text("<project/>", encoding="utf-8")
            src = pathlib.Path(d) / "src" / "main" / "java" / "com" / "ex"
            src.mkdir(parents=True)
            (src / "App.java").write_text(
                "package com.ex;\npublic class App {}\n", encoding="utf-8",
            )
            (src / "Util.java").write_text(
                "package com.ex;\nimport com.ex.App;\npublic class Util {}\n",
                encoding="utf-8",
            )
            graph = JavaAnalyzer().analyze_imports(d)
            util_key = os.path.join("src", "main", "java", "com", "ex", "Util.java")
            app_key = os.path.join("src", "main", "java", "com", "ex", "App.java")
            self.assertIn(util_key, graph)
            self.assertIn(app_key, graph[util_key])

    def test_gradle_source_root(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "build.gradle").write_text("apply plugin: 'java'\n", encoding="utf-8")
            src = pathlib.Path(d) / "src" / "main" / "java" / "com" / "ex"
            src.mkdir(parents=True)
            (src / "Main.java").write_text(
                "package com.ex;\npublic class Main {}\n", encoding="utf-8",
            )
            symbols = JavaAnalyzer().collect_symbols(d)
            self.assertTrue(any("Main" in v for v in symbols.values()))

    def test_kotlin_gradle_source_root(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "build.gradle.kts").write_text("plugins { kotlin(\"jvm\") }\n", encoding="utf-8")
            src = pathlib.Path(d) / "src" / "main" / "kotlin" / "com" / "ex"
            src.mkdir(parents=True)
            (src / "Main.kt").write_text(
                "package com.ex\nfun main() {}\n", encoding="utf-8",
            )
            graph = JavaAnalyzer().analyze_imports(d)
            # Single file, no internal imports — just verify detection works
            roots = JavaAnalyzer._detect_source_roots(d)
            self.assertTrue(any("kotlin" in r for r in roots))


# ── Detection (C++ / Java) ──────────────────────────────────────────────────

class TestDetectLanguageCppJava(unittest.TestCase):
    def test_cpp_project(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "main.cpp").write_text("", encoding="utf-8")
            pathlib.Path(d, "utils.h").write_text("", encoding="utf-8")
            pathlib.Path(d, "lib.cpp").write_text("", encoding="utf-8")
            analyzer = detect_language(d)
            self.assertEqual(analyzer.name, "cpp")

    def test_java_project(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "App.java").write_text("", encoding="utf-8")
            pathlib.Path(d, "Utils.java").write_text("", encoding="utf-8")
            pathlib.Path(d, "Model.java").write_text("", encoding="utf-8")
            analyzer = detect_language(d)
            self.assertEqual(analyzer.name, "java")


# ── New language analyzers (batch 2) ─────────────────────────────────────────


class TestCSharpAnalyzer(unittest.TestCase):
    def test_collect_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "Service.cs").write_text(
                "namespace App {\n"
                "    public class UserService {\n"
                "        public void GetUser(int id) { }\n"
                "    }\n"
                "    public interface IService { }\n"
                "    public enum Status { Active, Inactive }\n"
                "    public record UserDto(string Name);\n"
                "}\n",
                encoding="utf-8",
            )
            symbols = CSharpAnalyzer().collect_symbols(d)
            names = symbols.get("Service.cs", [])
            self.assertIn("UserService", names)
            self.assertIn("IService", names)
            self.assertIn("Status", names)
            self.assertIn("UserDto", names)

    def test_analyze_imports(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "Models.cs").write_text(
                "namespace App.Models {\n    public class User { }\n}\n",
                encoding="utf-8",
            )
            pathlib.Path(d, "Service.cs").write_text(
                "using App.Models;\nnamespace App.Services {\n    public class Svc { }\n}\n",
                encoding="utf-8",
            )
            graph = CSharpAnalyzer().analyze_imports(d)
            self.assertIn("Service.cs", graph)
            self.assertIn("Models.cs", graph["Service.cs"])


class TestRubyAnalyzer(unittest.TestCase):
    def test_collect_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "app.rb").write_text(
                "module MyApp\n  class User\n    def initialize(name)\n    end\n  end\nend\n",
                encoding="utf-8",
            )
            symbols = RubyAnalyzer().collect_symbols(d)
            names = symbols.get("app.rb", [])
            self.assertIn("MyApp", names)
            self.assertIn("User", names)
            self.assertIn("initialize", names)

    def test_analyze_imports(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "helper.rb").write_text("def help; end\n", encoding="utf-8")
            pathlib.Path(d, "main.rb").write_text("require_relative 'helper'\n", encoding="utf-8")
            graph = RubyAnalyzer().analyze_imports(d)
            self.assertIn("main.rb", graph)
            self.assertIn("helper.rb", graph["main.rb"])


class TestPhpAnalyzer(unittest.TestCase):
    def test_collect_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "User.php").write_text(
                "<?php\nnamespace App;\nclass User {}\ninterface Loggable {}\ntrait HasName {}\n",
                encoding="utf-8",
            )
            symbols = PhpAnalyzer().collect_symbols(d)
            names = symbols.get("User.php", [])
            self.assertIn("User", names)
            self.assertIn("Loggable", names)
            self.assertIn("HasName", names)


class TestSwiftAnalyzer(unittest.TestCase):
    def test_collect_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "Model.swift").write_text(
                "public class User {\n    func getName() -> String { return \"\" }\n}\n"
                "struct Config {}\nenum Status { case active }\nprotocol Fetchable {}\n"
                "actor DataStore {}\n",
                encoding="utf-8",
            )
            symbols = SwiftAnalyzer().collect_symbols(d)
            names = symbols.get("Model.swift", [])
            self.assertIn("User", names)
            self.assertIn("Config", names)
            self.assertIn("Status", names)
            self.assertIn("Fetchable", names)
            self.assertIn("DataStore", names)


class TestDartAnalyzer(unittest.TestCase):
    def test_collect_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "model.dart").write_text(
                "class User {}\nmixin Printable {}\nenum Color { red, green }\n",
                encoding="utf-8",
            )
            symbols = DartAnalyzer().collect_symbols(d)
            names = symbols.get("model.dart", [])
            self.assertIn("User", names)
            self.assertIn("Printable", names)
            self.assertIn("Color", names)


class TestZigAnalyzer(unittest.TestCase):
    def test_collect_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "main.zig").write_text(
                "pub fn main() void {}\nconst Config = struct {};\nfn helper() void {}\n",
                encoding="utf-8",
            )
            symbols = ZigAnalyzer().collect_symbols(d)
            names = symbols.get("main.zig", [])
            self.assertIn("main", names)
            self.assertIn("Config", names)
            self.assertIn("helper", names)

    def test_analyze_imports(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "util.zig").write_text("pub fn help() void {}\n", encoding="utf-8")
            pathlib.Path(d, "main.zig").write_text(
                'const util = @import("util.zig");\npub fn main() void {}\n',
                encoding="utf-8",
            )
            graph = ZigAnalyzer().analyze_imports(d)
            self.assertIn("main.zig", graph)
            self.assertIn("util.zig", graph["main.zig"])


class TestDetectNewLanguages(unittest.TestCase):
    def test_detect_csharp(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "App.csproj").write_text("<Project />\n", encoding="utf-8")
            self.assertEqual(detect_language(d).name, "csharp")

    def test_detect_ruby(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "Gemfile").write_text("source 'https://rubygems.org'\n", encoding="utf-8")
            self.assertEqual(detect_language(d).name, "ruby")

    def test_detect_php(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "composer.json").write_text("{}\n", encoding="utf-8")
            self.assertEqual(detect_language(d).name, "php")

    def test_detect_swift(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "Package.swift").write_text("// swift-tools-version:5.5\n", encoding="utf-8")
            self.assertEqual(detect_language(d).name, "swift")

    def test_detect_dart(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "pubspec.yaml").write_text("name: myapp\n", encoding="utf-8")
            self.assertEqual(detect_language(d).name, "dart")

    def test_detect_zig(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "build.zig").write_text("const std = @import(\"std\");\n", encoding="utf-8")
            self.assertEqual(detect_language(d).name, "zig")


# ── Typed symbols tests ──────────────────────────────────────────────────────

class TestPythonTypedSymbols(unittest.TestCase):
    def test_typed_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "mod.py").write_text(
                "class Foo:\n    pass\n\ndef bar():\n    pass\n\nasync def baz():\n    pass\n",
                encoding="utf-8",
            )
            typed = PythonAnalyzer().collect_typed_symbols(d)
            entries = typed.get("mod.py", [])
            names_types = set(entries)
            self.assertIn(("Foo", "class"), names_types)
            self.assertIn(("bar", "function"), names_types)
            self.assertIn(("baz", "function"), names_types)


class TestTypescriptTypedSymbols(unittest.TestCase):
    def test_typed_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "app.ts").write_text(
                "interface IUser {}\nclass UserService {}\nenum Role { Admin }\n"
                "type ID = string;\nfunction getUser() {}\n",
                encoding="utf-8",
            )
            typed = TypeScriptAnalyzer().collect_typed_symbols(d)
            entries = typed.get("app.ts", [])
            names_types = set(entries)
            self.assertIn(("IUser", "interface"), names_types)
            self.assertIn(("UserService", "class"), names_types)
            self.assertIn(("Role", "enum"), names_types)
            self.assertIn(("ID", "type_alias"), names_types)
            self.assertIn(("getUser", "function"), names_types)


class TestGoTypedSymbols(unittest.TestCase):
    def test_typed_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "main.go").write_text(
                "package main\nfunc main() {}\ntype Config struct {}\nconst MaxRetries = 3\n",
                encoding="utf-8",
            )
            typed = GoAnalyzer().collect_typed_symbols(d)
            entries = typed.get("main.go", [])
            names_types = set(entries)
            self.assertIn(("main", "function"), names_types)
            self.assertIn(("Config", "struct"), names_types)
            self.assertIn(("MaxRetries", "constant"), names_types)


class TestRustTypedSymbols(unittest.TestCase):
    def test_typed_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "lib.rs").write_text(
                "pub fn process() {}\nstruct Config {}\nenum Status { Ok, Err }\n"
                "trait Handler {}\nimpl Config {}\ntype Alias = i32;\n",
                encoding="utf-8",
            )
            typed = RustAnalyzer().collect_typed_symbols(d)
            entries = typed.get("lib.rs", [])
            names_types = set(entries)
            self.assertIn(("process", "function"), names_types)
            self.assertIn(("Config", "struct"), names_types)
            self.assertIn(("Status", "enum"), names_types)
            self.assertIn(("Handler", "trait"), names_types)
            self.assertIn(("Alias", "type_alias"), names_types)


class TestCppTypedSymbols(unittest.TestCase):
    def test_typed_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "main.cpp").write_text(
                "class Engine {};\nstruct Point {};\nnamespace gfx {}\n"
                "enum Color { Red };\nvoid render() {}\n",
                encoding="utf-8",
            )
            typed = CppAnalyzer().collect_typed_symbols(d)
            entries = typed.get("main.cpp", [])
            names_types = set(entries)
            self.assertIn(("Engine", "class"), names_types)
            self.assertIn(("Point", "struct"), names_types)
            self.assertIn(("gfx", "namespace"), names_types)
            self.assertIn(("Color", "enum"), names_types)
            self.assertIn(("render", "function"), names_types)


class TestJavaTypedSymbols(unittest.TestCase):
    def test_typed_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "App.java").write_text(
                "public class App {}\ninterface Repo {}\nenum State { ON, OFF }\n"
                "record Point(int x, int y) {}\n",
                encoding="utf-8",
            )
            typed = JavaAnalyzer().collect_typed_symbols(d)
            entries = typed.get("App.java", [])
            names_types = set(entries)
            self.assertIn(("App", "class"), names_types)
            self.assertIn(("Repo", "interface"), names_types)
            self.assertIn(("State", "enum"), names_types)
            self.assertIn(("Point", "record"), names_types)


class TestCSharpTypedSymbols(unittest.TestCase):
    def test_typed_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "Program.cs").write_text(
                "public class Service {}\ninterface IRepo {}\nstruct Vec2 {}\n"
                "enum Status { Active }\nrecord Config(string Name) {}\n",
                encoding="utf-8",
            )
            typed = CSharpAnalyzer().collect_typed_symbols(d)
            entries = typed.get("Program.cs", [])
            names_types = set(entries)
            self.assertIn(("Service", "class"), names_types)
            self.assertIn(("IRepo", "interface"), names_types)
            self.assertIn(("Vec2", "struct"), names_types)
            self.assertIn(("Status", "enum"), names_types)
            self.assertIn(("Config", "record"), names_types)


class TestRubyTypedSymbols(unittest.TestCase):
    def test_typed_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "app.rb").write_text(
                "class UserService\nend\nmodule Auth\nend\ndef process\nend\n",
                encoding="utf-8",
            )
            typed = RubyAnalyzer().collect_typed_symbols(d)
            entries = typed.get("app.rb", [])
            names_types = set(entries)
            self.assertIn(("UserService", "class"), names_types)
            self.assertIn(("Auth", "module"), names_types)
            self.assertIn(("process", "function"), names_types)


class TestPhpTypedSymbols(unittest.TestCase):
    def test_typed_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "app.php").write_text(
                "<?php\nclass Controller {}\ninterface Repo {}\ntrait Loggable {}\n"
                "enum Status {}\nfunction handle() {}\n",
                encoding="utf-8",
            )
            typed = PhpAnalyzer().collect_typed_symbols(d)
            entries = typed.get("app.php", [])
            names_types = set(entries)
            self.assertIn(("Controller", "class"), names_types)
            self.assertIn(("Repo", "interface"), names_types)
            self.assertIn(("Loggable", "trait"), names_types)
            self.assertIn(("Status", "enum"), names_types)
            self.assertIn(("handle", "function"), names_types)


class TestSwiftTypedSymbols(unittest.TestCase):
    def test_typed_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "app.swift").write_text(
                "class ViewModel {}\nstruct Point {}\nenum Direction { case up }\n"
                "protocol Drawable {}\nfunc render() {}\nextension ViewModel {}\n",
                encoding="utf-8",
            )
            typed = SwiftAnalyzer().collect_typed_symbols(d)
            entries = typed.get("app.swift", [])
            names_types = set(entries)
            self.assertIn(("ViewModel", "class"), names_types)
            self.assertIn(("Point", "struct"), names_types)
            self.assertIn(("Direction", "enum"), names_types)
            self.assertIn(("Drawable", "protocol"), names_types)
            self.assertIn(("render", "function"), names_types)


class TestDartTypedSymbols(unittest.TestCase):
    def test_typed_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "app.dart").write_text(
                "class Widget {}\nmixin Scrollable {}\nextension StringExt on String {}\n"
                "enum Theme { light, dark }\ntypedef Callback = void Function();\n",
                encoding="utf-8",
            )
            typed = DartAnalyzer().collect_typed_symbols(d)
            entries = typed.get("app.dart", [])
            names_types = set(entries)
            self.assertIn(("Widget", "class"), names_types)
            self.assertIn(("Scrollable", "mixin"), names_types)
            self.assertIn(("StringExt", "extension"), names_types)
            self.assertIn(("Theme", "enum"), names_types)
            self.assertIn(("Callback", "type_alias"), names_types)


class TestZigTypedSymbols(unittest.TestCase):
    def test_typed_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "main.zig").write_text(
                "pub fn init() void {}\nconst Config = struct {};\n"
                "const Status = enum { ok, err };\nconst std = @import(\"std\");\n",
                encoding="utf-8",
            )
            typed = ZigAnalyzer().collect_typed_symbols(d)
            entries = typed.get("main.zig", [])
            names_types = set(entries)
            self.assertIn(("init", "function"), names_types)
            self.assertIn(("Config", "struct"), names_types)
            self.assertIn(("Status", "enum"), names_types)
            self.assertIn(("std", "import_const"), names_types)


class TestRubyBasenameOverwrite(unittest.TestCase):
    def test_different_dirs_same_basename(self) -> None:
        """Ruby analyzer should not overwrite when two files share a basename."""
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "lib"))
            os.makedirs(os.path.join(d, "utils"))
            pathlib.Path(d, "lib", "helpers.rb").write_text("def lib_help; end\n", encoding="utf-8")
            pathlib.Path(d, "utils", "helpers.rb").write_text("def util_help; end\n", encoding="utf-8")
            pathlib.Path(d, "main.rb").write_text(
                "require_relative 'lib/helpers'\nrequire_relative 'utils/helpers'\n",
                encoding="utf-8",
            )
            graph = RubyAnalyzer().analyze_imports(d)
            self.assertIn("main.rb", graph)
            deps = graph["main.rb"]
            self.assertIn(os.path.join("lib", "helpers.rb"), deps)
            self.assertIn(os.path.join("utils", "helpers.rb"), deps)


class TestSwiftImmediateParent(unittest.TestCase):
    def test_only_immediate_parent_mapped(self) -> None:
        """Swift analyzer should only map files to their immediate parent directory."""
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "Sources", "MyModule"))
            pathlib.Path(d, "Sources", "MyModule", "Model.swift").write_text(
                "struct Model {}\n", encoding="utf-8",
            )
            pathlib.Path(d, "Sources", "MyModule", "View.swift").write_text(
                "import MyModule\nstruct View {}\n", encoding="utf-8",
            )
            graph = SwiftAnalyzer().analyze_imports(d)
            # View imports MyModule → should find Model.swift (immediate parent is MyModule)
            view_path = os.path.join("Sources", "MyModule", "View.swift")
            model_path = os.path.join("Sources", "MyModule", "Model.swift")
            self.assertIn(view_path, graph)
            self.assertIn(model_path, graph[view_path])


class TestJavaPackagelessFallback(unittest.TestCase):
    def test_unpackaged_files_not_spuriously_linked(self) -> None:
        """Java files without package or imports should not be linked."""
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "App.java").write_text(
                "public class App { }\n", encoding="utf-8",
            )
            pathlib.Path(d, "Helper.java").write_text(
                "public class Helper { }\n", encoding="utf-8",
            )
            graph = JavaAnalyzer().analyze_imports(d)
            # No package, no imports → no spurious dependency edges
            self.assertEqual(graph, {})


if __name__ == "__main__":
    unittest.main()
