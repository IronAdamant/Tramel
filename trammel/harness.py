"""Isolated execution: copy project, apply edits, run tests with timeout.

Supports both full-run verification and incremental per-step verification
with structured failure analysis.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import TYPE_CHECKING, Any

from .utils import _is_ignored_dir, analyze_failure

if TYPE_CHECKING:
    from .analyzers import LanguageAnalyzer


def _ignore_copy(_path: str, names: list[str]) -> set[str]:
    return {n for n in names if _is_ignored_dir(n) or n.endswith(".pyc")}


def _apply_edits(root: str, edits: list[dict[str, Any]]) -> None:
    for ed in edits:
        rel = ed.get("path") or ed.get("file")
        content = ed.get("content")
        if not rel or content is None:
            continue
        dest = os.path.join(root, rel)
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        with open(dest, "w", encoding="utf-8") as fp:
            fp.write(content if isinstance(content, str) else str(content))


def _static_analysis(
    edits: list[dict[str, Any]],
    project_root: str,
) -> dict[str, Any]:
    """Run lightweight static-analysis heuristics on a step's edits.

    Checks file-path conventions and test coverage without executing code.
    Returns warnings and a confidence score (0.0–1.0).
    """
    warnings: list[str] = []
    score = 1.0

    edited_paths: list[str] = []
    for ed in edits:
        rel = ed.get("path") or ed.get("file")
        if not rel:
            warnings.append("edit missing path/file")
            score -= 0.2
            continue
        if os.path.isabs(rel) or ".." in rel.replace("\\", "/").split("/"):
            warnings.append(f"suspicious path: {rel}")
            score -= 0.1
        edited_paths.append(rel)

    # Test-coverage heuristic: if we're editing a source file, does a matching
    # test file exist in the project?
    test_misses: list[str] = []
    for rel in edited_paths:
        base = os.path.basename(rel)
        name, ext = os.path.splitext(base)
        parent = os.path.dirname(rel)
        # Common test file patterns
        candidates: list[str] = []
        if parent.startswith("src/"):
            test_parent = parent.replace("src/", "tests/", 1)
            candidates.append(os.path.join(test_parent, f"{name}.test{ext}"))
            candidates.append(os.path.join(test_parent, f"test_{name}{ext}"))
        candidates.append(os.path.join(parent, f"{name}.test{ext}"))
        candidates.append(os.path.join(parent, f"test_{name}{ext}"))
        candidates.append(os.path.join("tests", parent, f"{name}.test{ext}"))
        if not any(os.path.isfile(os.path.join(project_root, c)) for c in candidates):
            test_misses.append(rel)
    if test_misses:
        warnings.append(
            f"no matching test file found for {len(test_misses)} edited source file(s)"
        )
        score -= 0.1

    score = max(score, 0.0)
    return {
        "confidence": round(score, 2),
        "warnings": warnings,
        "edited_files": edited_paths,
        "test_coverage_checked": True,
    }


def _run_tests(
    tmp: str,
    timeout_s: int,
    test_cmd: list[str] | None = None,
    error_patterns: list[tuple[str, str, str]] | None = None,
) -> dict[str, Any]:
    """Run tests in the given directory and return structured results."""
    if test_cmd:
        cmd = test_cmd
    else:
        from .analyzers import PythonAnalyzer
        cmd = PythonAnalyzer().pick_test_cmd(tmp)
    env = os.environ.copy()
    env.setdefault("PYTHONHASHSEED", "0")
    try:
        result = subprocess.run(
            cmd, cwd=tmp, env=env, timeout=timeout_s,
            capture_output=True, text=True,
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "timeout", "trace": "", "score": 0.0}
    except OSError as e:
        return {"success": False, "output": "", "trace": str(e)[:500], "score": 0.0}

    success = result.returncode == 0
    out = result.stdout[:500]
    err = result.stderr[:500]
    outcome: dict[str, Any] = {
        "success": success,
        "output": out,
        "trace": err,
        "score": 1.0 if success else 0.0,
    }
    if not success:
        outcome["failure_analysis"] = analyze_failure(err, out, error_patterns)
    return outcome


class ExecutionHarness:
    def __init__(
        self,
        timeout_s: int = 60,
        test_cmd: list[str] | None = None,
        analyzer: LanguageAnalyzer | None = None,
    ) -> None:
        self.timeout_s = timeout_s
        self.test_cmd = test_cmd
        self._analyzer = analyzer

    def _effective_test_cmd(self, project_root: str) -> list[str] | None:
        if self.test_cmd is not None:
            return self.test_cmd
        if self._analyzer is not None:
            return self._analyzer.pick_test_cmd(project_root)
        return None

    def _effective_error_patterns(self) -> list[tuple[str, str, str]] | None:
        if self._analyzer is not None:
            return self._analyzer.error_patterns()
        return None

    def prepare_base(self, project_root: str) -> str:
        """Create a filtered base copy of the project. Caller must clean up."""
        project_root = os.path.abspath(project_root)
        base_dir = tempfile.mkdtemp(prefix="trammel_base_")
        shutil.copytree(project_root, base_dir, dirs_exist_ok=True, ignore=_ignore_copy)
        return base_dir

    def run_from_base(self, edits: list[dict[str, Any]], base_dir: str) -> dict[str, Any]:
        """Run verification using a pre-prepared base copy (avoids re-filtering)."""
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(base_dir, tmp, dirs_exist_ok=True)
            _apply_edits(tmp, edits)
            return _run_tests(
                tmp, self.timeout_s,
                self._effective_test_cmd(base_dir),
                self._effective_error_patterns(),
            )

    def verify_step(
        self,
        edits: list[dict[str, Any]],
        project_root: str,
        prior_edits: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Verify a single step's edits in isolation.

        prior_edits: edits from already-verified steps to apply first.
        """
        project_root = os.path.abspath(project_root)
        static = _static_analysis(edits, project_root)
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(
                project_root, tmp, dirs_exist_ok=True, ignore=_ignore_copy,
            )
            if prior_edits:
                _apply_edits(tmp, prior_edits)
            _apply_edits(tmp, edits)
            result = _run_tests(
                tmp, self.timeout_s,
                self._effective_test_cmd(project_root),
                self._effective_error_patterns(),
            )
        result["static_analysis"] = static
        return result

    def run_incremental(
        self,
        step_edits: list[list[dict[str, Any]]],
        project_root: str,
    ) -> dict[str, Any]:
        """Verify edits step-by-step. Stop at first failure.

        step_edits: list of edit lists, one per step in order.
        Returns outcome with steps_completed count and failure details if any.

        Uses a persistent base copy that accumulates edits, so each step
        only applies its own edits (O(K) total instead of O(K^2)).
        """
        project_root = os.path.abspath(project_root)

        with tempfile.TemporaryDirectory() as base:
            shutil.copytree(
                project_root, base, dirs_exist_ok=True, ignore=_ignore_copy,
            )
            for i, edits in enumerate(step_edits):
                with tempfile.TemporaryDirectory() as tmp:
                    shutil.copytree(base, tmp, dirs_exist_ok=True)
                    _apply_edits(tmp, edits)
                    result = _run_tests(
                        tmp, self.timeout_s,
                        self._effective_test_cmd(project_root),
                        self._effective_error_patterns(),
                    )

                if not result["success"]:
                    return {
                        "success": False,
                        "steps_completed": i,
                        "failed_at_step": i,
                        "output": result.get("output", ""),
                        "trace": result.get("trace", ""),
                        "score": 0.0,
                        "failure_analysis": result.get("failure_analysis"),
                        "failure_reason": (result.get("failure_analysis") or {}).get("message", ""),
                    }

                # Apply content edits to base for next step
                content_edits = [ed for ed in edits if ed.get("content") is not None]
                if content_edits:
                    _apply_edits(base, content_edits)

        return {
            "success": True,
            "steps_completed": len(step_edits),
            "output": "all steps passed",
            "trace": "",
            "score": 1.0,
        }
