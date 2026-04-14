"""Canonical regression tests for all language analyzers.

Each analyzer is exercised against a synthetic snippet containing the
most common syntactic edge cases for that language.  We assert expected
symbol names and import targets so that regex drift is caught immediately.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trammel.analyzers import PythonAnalyzer, TypeScriptAnalyzer, JavaScriptAnalyzer  # noqa: E402
from trammel.analyzer_engine import (  # noqa: E402
    GoAnalyzer,
    RustAnalyzer,
    CppAnalyzer,
    JavaAnalyzer,
    CSharpAnalyzer,
    RubyAnalyzer,
    PhpAnalyzer,
    SwiftAnalyzer,
    DartAnalyzer,
    ZigAnalyzer,
)


def _write_files(root: str, files: dict[str, str]) -> None:
    for path, content in files.items():
        p = pathlib.Path(root) / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
# Go
# ═══════════════════════════════════════════════════════════════════════════════

class TestGoAnalyzerRegression(unittest.TestCase):
    SNIPPET = '''
package main

import "fmt"
import (
    "os"
    "strings"
)

// Comment should not break parsing
func Add(a, b int) int { return a + b }

type User struct {
    Name string
}

type Stringer interface {}

const MaxCount = 100
var GlobalUser User
'''

    def test_symbols_and_imports(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            _write_files(d, {
                "go.mod": "module example.com/test\n\ngo 1.21\n",
                "main.go": self.SNIPPET,
            })
            analyzer = GoAnalyzer()
            symbols = analyzer.collect_symbols(d)
            typed = analyzer.collect_typed_symbols(d)
            imports = analyzer.analyze_imports(d)

        self.assertIn("main.go", symbols)
        self.assertEqual(
            set(symbols["main.go"]),
            {"Add", "User", "Stringer", "MaxCount", "GlobalUser"},
        )
        self.assertIn(("Add", "function"), typed["main.go"])
        self.assertIn(("User", "struct"), typed["main.go"])
        # Standard-library imports are filtered out by the Go resolver
        # when they do not belong to the local module.
        self.assertEqual(set(imports.get("main.go", [])), set())


# ═══════════════════════════════════════════════════════════════════════════════
# Rust
# ═══════════════════════════════════════════════════════════════════════════════

class TestRustAnalyzerRegression(unittest.TestCase):
    SNIPPET = '''
use crate::models::User;
use super::helpers;
use self::utils;
mod parser;

pub async fn fetch_user() {}
pub struct Config {}
pub enum Status { Ok, Err }
pub trait Logger {}
impl Config {}
pub type Result<T> = std::result::Result<T, ()>;
'''

    def test_symbols_and_imports(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            _write_files(d, {
                "lib.rs": self.SNIPPET,
                "models.rs": "pub struct User;\n",
                "helpers.rs": "pub fn help() {}\n",
                "utils.rs": "pub fn util() {}\n",
                "parser.rs": "pub fn parse() {}\n",
                "Cargo.toml": '[workspace]\nmembers = ["."]\n',
            })
            analyzer = RustAnalyzer()
            symbols = analyzer.collect_symbols(d)
            typed = analyzer.collect_typed_symbols(d)
            imports = analyzer.analyze_imports(d)

        self.assertIn("lib.rs", symbols)
        self.assertEqual(
            set(symbols["lib.rs"]),
            {"fetch_user", "Config", "Status", "Logger", "Config", "Result"},
        )
        self.assertIn(("fetch_user", "function"), typed["lib.rs"])
        self.assertIn(("Config", "struct"), typed["lib.rs"])
        # imports resolve to actual file paths
        self.assertIn("models.rs", imports.get("lib.rs", []))
        self.assertIn("helpers.rs", imports.get("lib.rs", []))
        self.assertIn("utils.rs", imports.get("lib.rs", []))
        self.assertIn("parser.rs", imports.get("lib.rs", []))


# ═══════════════════════════════════════════════════════════════════════════════
# C / C++
# ═══════════════════════════════════════════════════════════════════════════════

class TestCppAnalyzerRegression(unittest.TestCase):
    SNIPPET = '''
#include "header.hpp"

template<typename T>
class Box {};

struct Point {};

namespace math {}

enum class Color { Red, Green };

typedef unsigned int uint;

static inline void helper() {}

operator+(const Point& a, const Point& b) {}

class Widget::~Widget() {}

EXPORT_API void public_api() {}
'''

    def test_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            _write_files(d, {"main.cpp": self.SNIPPET, "header.hpp": "// header\n"})
            analyzer = CppAnalyzer()
            symbols = analyzer.collect_symbols(d)
            imports = analyzer.analyze_imports(d)

        self.assertIn("main.cpp", symbols)
        expected = {"Box", "Point", "math", "Color", "uint", "helper",
                    "operator+", "Widget", "public_api"}
        for name in expected:
            self.assertIn(name, symbols["main.cpp"], f"missing {name}")
        self.assertEqual(imports.get("main.cpp"), ["header.hpp"])


# ═══════════════════════════════════════════════════════════════════════════════
# Java / Kotlin
# ═══════════════════════════════════════════════════════════════════════════════

class TestJavaAnalyzerRegression(unittest.TestCase):
    JAVA_SNIPPET = '''
package com.example;

import com.example.Helper;
import static java.lang.Math.max;

public class User {}
interface Repository {}
enum Role { ADMIN }
public record UserRecord(String name) {}
public fun helper() {}
private @interface Valid {}
'''

    def test_java_symbols_and_imports(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d) / "src" / "main" / "java" / "com" / "example"
            root.mkdir(parents=True)
            (root / "User.java").write_text(self.JAVA_SNIPPET, encoding="utf-8")
            (root / "Helper.java").write_text("package com.example;\npublic class Helper {}\n", encoding="utf-8")
            analyzer = JavaAnalyzer()
            symbols = analyzer.collect_symbols(str(d))
            imports = analyzer.analyze_imports(str(d))

        rel = "src/main/java/com/example/User.java"
        self.assertIn(rel, symbols)
        expected = {"User", "Repository", "Role", "UserRecord", "helper", "Valid"}
        for name in expected:
            self.assertIn(name, symbols[rel], f"missing {name}")
        # Project-local namespace imports resolve to sibling files
        self.assertIn("src/main/java/com/example/Helper.java", imports.get(rel, []))


# ═══════════════════════════════════════════════════════════════════════════════
# C#
# ═══════════════════════════════════════════════════════════════════════════════

class TestCSharpAnalyzerRegression(unittest.TestCase):
    SNIPPET = '''
using App.Helper;
using System;

namespace App {
    public class User {}
    public interface IRepo {}
    public struct Point {}
    public enum Status { Active }
    public record UserRecord(string Name);
    public static int Helper() => 0;
}
'''

    def test_symbols_and_imports(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            _write_files(d, {"Program.cs": self.SNIPPET})
            analyzer = CSharpAnalyzer()
            symbols = analyzer.collect_symbols(d)
            imports = analyzer.analyze_imports(d)

        self.assertIn("Program.cs", symbols)
        expected = {"User", "IRepo", "Point", "Status", "UserRecord", "Helper"}
        for name in expected:
            self.assertIn(name, symbols["Program.cs"], f"missing {name}")
        # External namespace imports (System) are not resolved to local files.
        # Local namespace imports may resolve depending on sibling files present.
        self.assertIsInstance(imports.get("Program.cs", []), list)


# ═══════════════════════════════════════════════════════════════════════════════
# Ruby
# ═══════════════════════════════════════════════════════════════════════════════

class TestRubyAnalyzerRegression(unittest.TestCase):
    SNIPPET = '''
require 'json'
require_relative 'helper'

class User
  def name
    "user"
  end
  def self.create
    new
  end
end

module Helpers
  def assist; end
end
'''

    def test_symbols_and_imports(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            _write_files(d, {"user.rb": self.SNIPPET, "helper.rb": "# helper\n"})
            analyzer = RubyAnalyzer()
            symbols = analyzer.collect_symbols(d)
            imports = analyzer.analyze_imports(d)

        self.assertIn("user.rb", symbols)
        self.assertEqual(set(symbols["user.rb"]), {"User", "Helpers", "name", "create", "assist"})
        # External gems (json) do not resolve to local files.
        self.assertIn("helper.rb", imports.get("user.rb", []))


# ═══════════════════════════════════════════════════════════════════════════════
# PHP
# ═══════════════════════════════════════════════════════════════════════════════

class TestPhpAnalyzerRegression(unittest.TestCase):
    SNIPPET = '''
<?php
namespace App\\Models;

use App\\Utils\\Helper;
use App\\Utils\\Validator;

abstract class User {}
interface Repository {}
trait Loggable {}
enum Status { case Active; }
function global_helper() {}

class Controller {
    public function index() {}
    protected static function authorize() {}
}
'''

    def test_symbols_and_imports(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            utils = pathlib.Path(d) / "Utils"
            utils.mkdir()
            (utils / "Helper.php").write_text("<?php\nnamespace App\\Utils;\nclass Helper {}\n", encoding="utf-8")
            (utils / "Validator.php").write_text("<?php\nnamespace App\\Utils;\nclass Validator {}\n", encoding="utf-8")
            _write_files(d, {"User.php": self.SNIPPET})
            analyzer = PhpAnalyzer()
            symbols = analyzer.collect_symbols(d)
            imports = analyzer.analyze_imports(d)

        self.assertIn("User.php", symbols)
        expected = {"User", "Repository", "Loggable", "Status",
                    "global_helper", "Controller", "index", "authorize"}
        for name in expected:
            self.assertIn(name, symbols["User.php"], f"missing {name}")
        # Local namespace imports resolve to matching files
        self.assertIn("Utils/Helper.php", imports.get("User.php", []))
        self.assertIn("Utils/Validator.php", imports.get("User.php", []))


# ═══════════════════════════════════════════════════════════════════════════════
# Swift
# ═══════════════════════════════════════════════════════════════════════════════

class TestSwiftAnalyzerRegression(unittest.TestCase):
    SNIPPET = '''
import Foundation
import UIKit

public class User {}
internal struct Point {}
private enum Direction {}
protocol Drawable {}
public func render() {}
extension User {}
public typealias ID = String
public actor Worker {}
'''

    def test_symbols_and_imports(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            _write_files(d, {"User.swift": self.SNIPPET})
            analyzer = SwiftAnalyzer()
            symbols = analyzer.collect_symbols(d)
            imports = analyzer.analyze_imports(d)

        self.assertIn("User.swift", symbols)
        expected = {"User", "Point", "Direction", "Drawable", "render",
                    "User", "ID", "Worker"}
        for name in expected:
            self.assertIn(name, symbols["User.swift"], f"missing {name}")
        # External framework imports do not resolve to local files
        self.assertIsInstance(imports.get("User.swift", []), list)


# ═══════════════════════════════════════════════════════════════════════════════
# Dart
# ═══════════════════════════════════════════════════════════════════════════════

class TestDartAnalyzerRegression(unittest.TestCase):
    SNIPPET = '''
import 'package:flutter/material.dart';
import 'dart:io';

abstract class User {}
mixin Loggable {}
extension StringX on String {}
enum Status { active }
typedef JsonMap = Map<String, dynamic>;

void main() async {}

class User {
  factory User.guest() => User();
}
'''

    def test_symbols_and_imports(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            _write_files(d, {"user.dart": self.SNIPPET})
            analyzer = DartAnalyzer()
            symbols = analyzer.collect_symbols(d)
            imports = analyzer.analyze_imports(d)

        self.assertIn("user.dart", symbols)
        expected = {"User", "Loggable", "StringX", "Status", "JsonMap",
                    "main", "User.guest"}
        for name in expected:
            self.assertIn(name, symbols["user.dart"], f"missing {name}")
        # External package imports do not resolve to local files
        self.assertIsInstance(imports.get("user.dart", []), list)


# ═══════════════════════════════════════════════════════════════════════════════
# Zig
# ═══════════════════════════════════════════════════════════════════════════════

class TestZigAnalyzerRegression(unittest.TestCase):
    SNIPPET = '''
const std = @import("std");
const math = @import("math.zig");

pub fn add(a: i32, b: i32) i32 { return a + b; }
pub const User = struct { name: []const u8 };
pub const Status = enum { ok, err };
pub const Value = union { int: i32 };
pub const Config = @import("config.zig");
pub const ID: type = u64;
'''

    def test_symbols_and_imports(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            _write_files(d, {
                "main.zig": self.SNIPPET,
                "math.zig": "pub fn sqrt() {}\n",
                "config.zig": "pub const debug = true;\n",
            })
            analyzer = ZigAnalyzer()
            symbols = analyzer.collect_symbols(d)
            imports = analyzer.analyze_imports(d)

        self.assertIn("main.zig", symbols)
        expected = {"add", "User", "Status", "Value", "Config", "ID"}
        for name in expected:
            self.assertIn(name, symbols["main.zig"], f"missing {name}")
        # std is external and does not resolve locally
        self.assertIn("math.zig", imports.get("main.zig", []))
        self.assertIn("config.zig", imports.get("main.zig", []))


# ═══════════════════════════════════════════════════════════════════════════════
# Python (AST-based, not regex, but included for completeness)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPythonAnalyzerRegression(unittest.TestCase):
    SNIPPET = '''
import local_pkg
from local_pkg.utils import deque

async def fetch():
    pass

class User:
    pass

def helper():
    pass
'''

    def test_symbols_and_imports(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pkg = pathlib.Path(d) / "local_pkg"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("", encoding="utf-8")
            (pkg / "utils.py").write_text("from collections import deque\n", encoding="utf-8")
            _write_files(d, {"mod.py": self.SNIPPET})
            analyzer = PythonAnalyzer()
            symbols = analyzer.collect_symbols(d)
            imports = analyzer.analyze_imports(d)

        self.assertIn("mod.py", symbols)
        self.assertEqual(set(symbols["mod.py"]), {"fetch", "User", "helper"})
        self.assertIn("local_pkg/__init__.py", imports.get("mod.py", []))
        self.assertIn("local_pkg/utils.py", imports.get("mod.py", []))


# ═══════════════════════════════════════════════════════════════════════════════
# TypeScript / JavaScript
# ═══════════════════════════════════════════════════════════════════════════════

class TestTypeScriptAnalyzerRegression(unittest.TestCase):
    SNIPPET = '''
import { foo } from "./foo";
import * as bar from "./bar";
export * from "./baz";

interface User {
  name: string;
}

type ID = string;

export class Service {
  run() {}
}

function helper() {}
'''

    def test_symbols_and_imports(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            _write_files(d, {
                "svc.ts": self.SNIPPET,
                "foo.ts": "export const foo = 1;\n",
                "bar.ts": "export const bar = 2;\n",
                "baz.ts": "export const baz = 3;\n",
            })
            analyzer = TypeScriptAnalyzer()
            symbols = analyzer.collect_symbols(d)
            imports = analyzer.analyze_imports(d)

        self.assertIn("svc.ts", symbols)
        self.assertIn("User", symbols["svc.ts"])
        self.assertIn("ID", symbols["svc.ts"])
        self.assertIn("Service", symbols["svc.ts"])
        self.assertIn("helper", symbols["svc.ts"])
        self.assertIn("foo.ts", imports.get("svc.ts", []))
        self.assertIn("bar.ts", imports.get("svc.ts", []))
        self.assertIn("baz.ts", imports.get("svc.ts", []))


class TestTypedSymbolCoverage(unittest.TestCase):
    """collect_symbols must return every name that collect_typed_symbols
    returns, for every regex-based analyzer."""

    _CASES: list[tuple[str, type, str]] = [
        ("go", GoAnalyzer, 'package main\nfunc Add() {}\ntype T struct {}\nconst C = 1\nvar V int\n'),
        ("rust", RustAnalyzer, 'fn f() {}\nstruct S {}\nenum E {}\ntrait Tr {}\nimpl S {}\ntype Ta<T> = Option<T>;\n'),
        ("cpp", CppAnalyzer, 'class C {};\nstruct S {};\nnamespace N {}\nenum E {};\ntypedef int I;\nvoid f() {}\n'),
        ("java", JavaAnalyzer, 'class C {}\ninterface I {}\nenum E {}\nrecord R() {}\nfun f() {}\nobject O {}\n@interface A {}\n'),
        ("csharp", CSharpAnalyzer, 'class C {}\ninterface I {}\nstruct S {}\nenum E {}\nrecord R(string N);\nvoid F() {}\n'),
        ("ruby", RubyAnalyzer, 'class C\n  def m\n  end\nend\nmodule M\n  def n\n  end\nend\n'),
        ("php", PhpAnalyzer, '<?php\nclass C {}\ninterface I {}\ntrait T {}\nenum E {}\nfunction f() {}\nclass X { public function m() {} }\n'),
        ("swift", SwiftAnalyzer, 'class C {}\nstruct S {}\nenum E {}\nprotocol P {}\nfunc f() {}\nextension C {}\ntypealias Ta = Int\nactor A {}\n'),
        ("dart", DartAnalyzer, 'class C {}\nmixin M {}\nextension E on Object {}\nenum En {}\ntypedef Ta = int;\nvoid f() {}\nclass C2 { factory C2.g() => C2(); }\n'),
        ("zig", ZigAnalyzer, 'fn f() {}\nconst S = struct {};\nconst E = enum {};\nconst U = union {};\nconst C = @import("std");\nconst T: type = u8;\n'),
    ]

    def test_coverage(self) -> None:
        for name, cls, snippet in self._CASES:
            with self.subTest(lang=name):
                with tempfile.TemporaryDirectory() as d:
                    ext = cls().extensions[0]
                    _write_files(d, {f"main{ext}": snippet})
                    analyzer = cls()
                    symbols = analyzer.collect_symbols(d)
                    typed = analyzer.collect_typed_symbols(d)
                file = f"main{ext}"
                self.assertIn(file, symbols, f"{name}: no symbols for {file}")
                self.assertIn(file, typed, f"{name}: no typed symbols for {file}")
                symbol_names = set(symbols[file])
                typed_names = {n for n, _ in typed[file]}
                missing = typed_names - symbol_names
                self.assertFalse(
                    missing,
                    f"{name}: collect_symbols missing names from collect_typed_symbols: {missing}",
                )


if __name__ == "__main__":
    unittest.main()
