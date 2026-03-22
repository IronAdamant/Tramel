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

    def test_collect_symbols_interface(self):
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "types.ts").write_text(
                "export interface UserProps {\n  name: string;\n}\n", encoding="utf-8",
            )
            symbols = TypeScriptAnalyzer().collect_symbols(d)
            self.assertIn("UserProps", symbols.get("types.ts", []))

    def test_collect_symbols_enum(self):
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "colors.ts").write_text(
                "export enum Color {\n  Red,\n  Green,\n  Blue\n}\n", encoding="utf-8",
            )
            symbols = TypeScriptAnalyzer().collect_symbols(d)
            self.assertIn("Color", symbols.get("colors.ts", []))

    def test_collect_symbols_const_enum(self):
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "dir.ts").write_text(
                "export const enum Direction {\n  Up,\n  Down\n}\n", encoding="utf-8",
            )
            symbols = TypeScriptAnalyzer().collect_symbols(d)
            self.assertIn("Direction", symbols.get("dir.ts", []))

    def test_collect_symbols_type_alias(self):
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "types.ts").write_text(
                "export type ID = string | number;\n", encoding="utf-8",
            )
            symbols = TypeScriptAnalyzer().collect_symbols(d)
            self.assertIn("ID", symbols.get("types.ts", []))

    def test_collect_symbols_abstract_class(self):
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "base.ts").write_text(
                "export abstract class Base {\n  abstract run(): void;\n}\n", encoding="utf-8",
            )
            symbols = TypeScriptAnalyzer().collect_symbols(d)
            self.assertIn("Base", symbols.get("base.ts", []))

    def test_collect_symbols_decorated_class(self):
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "comp.ts").write_text(
                "@Component({selector: 'app'})\nexport class MyComponent {\n}\n", encoding="utf-8",
            )
            symbols = TypeScriptAnalyzer().collect_symbols(d)
            self.assertIn("MyComponent", symbols.get("comp.ts", []))

    def test_collect_symbols_function_expression(self):
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "handler.ts").write_text(
                "export const handler = function(req: Request) {\n  return null;\n}\n", encoding="utf-8",
            )
            symbols = TypeScriptAnalyzer().collect_symbols(d)
            self.assertIn("handler", symbols.get("handler.ts", []))

    def test_import_reexport(self):
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

    def test_import_barrel_export(self):
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

    def test_import_dynamic(self):
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

    def test_import_type_reexport(self):
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

    def test_mts_mjs_collected(self):
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
    def test_tsconfig_path_aliases(self):
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

    def test_tsconfig_missing_graceful(self):
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

    def test_tsconfig_invalid_json_graceful(self):
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


if __name__ == "__main__":
    unittest.main()
