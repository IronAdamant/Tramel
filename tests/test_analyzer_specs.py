"""Spec-driven analyzer validation — every regex compiles, every capture is consistent."""

from __future__ import annotations

import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trammel.analyzer_specs import (  # noqa: E402
    AnalyzerSpec,
    SPEC_REGISTRY,
    _COMMENT_STRIPPERS,
)


class TestAnalyzerSpecValidation(unittest.TestCase):
    def test_every_spec_has_valid_regex(self) -> None:
        for name, spec in SPEC_REGISTRY.items():
            with self.subTest(lang=name):
                self.assertTrue(spec.symbol_patterns, f"{name}: no symbol_patterns")
                for i, p in enumerate(spec.symbol_patterns):
                    self.assertIsInstance(
                        p, re.Pattern,
                        f"{name}: symbol_patterns[{i}] is not a compiled regex",
                    )
                for i, (p, t) in enumerate(spec.typed_patterns):
                    self.assertIsInstance(
                        p, re.Pattern,
                        f"{name}: typed_patterns[{i}] is not a compiled regex",
                    )
                    self.assertIsInstance(
                        t, str,
                        f"{name}: typed_patterns[{i}] type is not a string",
                    )

    def test_symbol_patterns_non_empty(self) -> None:
        for name, spec in SPEC_REGISTRY.items():
            with self.subTest(lang=name):
                self.assertTrue(spec.symbol_patterns, f"{name}: symbol_patterns is empty")
                self.assertTrue(spec.typed_patterns, f"{name}: typed_patterns is empty")

    def test_comment_stripper_exists(self) -> None:
        for name, spec in SPEC_REGISTRY.items():
            with self.subTest(lang=name):
                self.assertIn(
                    spec.strip_comments, _COMMENT_STRIPPERS,
                    f"{name}: strip_comments key '{spec.strip_comments}' not registered",
                )

    def test_error_patterns_well_formed(self) -> None:
        for name, spec in SPEC_REGISTRY.items():
            with self.subTest(lang=name):
                for i, (needle, code, suggestion) in enumerate(spec.error_patterns):
                    self.assertIsInstance(needle, str, f"{name}: error_patterns[{i}] needle")
                    self.assertIsInstance(code, str, f"{name}: error_patterns[{i}] code")
                    self.assertIsInstance(suggestion, str, f"{name}: error_patterns[{i}] suggestion")

    def test_imports_patterns_compile(self) -> None:
        for name, spec in SPEC_REGISTRY.items():
            with self.subTest(lang=name):
                if spec.imports is None:
                    continue
                for i, (p, kind) in enumerate(spec.imports.patterns):
                    self.assertIsInstance(
                        p, re.Pattern,
                        f"{name}: imports.patterns[{i}] is not a compiled regex",
                    )

    def test_extensions_non_empty(self) -> None:
        for name, spec in SPEC_REGISTRY.items():
            with self.subTest(lang=name):
                self.assertTrue(spec.extensions, f"{name}: extensions tuple is empty")
                for ext in spec.extensions:
                    self.assertTrue(ext.startswith("."), f"{name}: extension {ext!r} missing dot")


if __name__ == "__main__":
    unittest.main()
