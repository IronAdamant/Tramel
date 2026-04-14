"""Backward-compatibility shim — analyzers moved to analyzer_engine.py."""

from __future__ import annotations

from .analyzer_engine import (
    CSharpAnalyzer, DartAnalyzer, PhpAnalyzer, RubyAnalyzer, SwiftAnalyzer, ZigAnalyzer,
)

__all__ = [
    "CSharpAnalyzer", "DartAnalyzer", "PhpAnalyzer",
    "RubyAnalyzer", "SwiftAnalyzer", "ZigAnalyzer",
]
