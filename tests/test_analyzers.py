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
    PythonAnalyzer,
    TypeScriptAnalyzer,
    detect_language,
)
from trammel.utils import analyze_imports  # noqa: E402


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


# ── Backward compat ──────────────────────────────────────────────────────────

class TestBackwardCompat(unittest.TestCase):
    def test_utils_analyze_imports_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pkg = pathlib.Path(d) / "pkg"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("", encoding="utf-8")
            (pkg / "a.py").write_text("X = 1\n", encoding="utf-8")
            (pkg / "b.py").write_text("from pkg.a import X\n", encoding="utf-8")
            graph = analyze_imports(d)
            b_deps = graph.get(os.path.join("pkg", "b.py"), [])
            self.assertIn(os.path.join("pkg", "a.py"), b_deps)


if __name__ == "__main__":
    unittest.main()
