"""Isolated execution: copy project, apply edits, run tests with timeout.

Supports both full-run verification and incremental per-step verification
with structured failure analysis.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from .utils import _is_ignored_dir, analyze_failure


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


def _pick_test_cmd(project_root: str) -> list[str]:
    """Stdlib unittest discover (no pytest required)."""
    tests_dir = os.path.join(project_root, "tests")
    exe = sys.executable
    if os.path.isdir(tests_dir):
        return [exe, "-m", "unittest", "discover", "-q", "-s", "tests", "-p", "test_*.py"]
    return [exe, "-m", "unittest", "discover", "-q", "-s", ".", "-p", "test_*.py"]


def _run_tests(
    tmp: str, timeout_s: int, test_cmd: list[str] | None = None,
) -> dict[str, Any]:
    """Run tests in the given directory and return structured results."""
    cmd = test_cmd if test_cmd else _pick_test_cmd(tmp)
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
    out = (result.stdout or "")[:500]
    err = (result.stderr or "")[:500]
    outcome: dict[str, Any] = {
        "success": success,
        "output": out,
        "trace": err,
        "score": 1.0 if success else 0.0,
    }
    if not success:
        outcome["failure_analysis"] = analyze_failure(err, out)
    return outcome


class ExecutionHarness:
    def __init__(
        self, timeout_s: int = 60, test_cmd: list[str] | None = None,
    ) -> None:
        self.timeout_s = timeout_s
        self.test_cmd = test_cmd

    def run(self, edits: list[dict[str, Any]], project_root: str) -> dict[str, Any]:
        """Full verification: apply all edits, run tests once."""
        project_root = os.path.abspath(project_root)
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(
                project_root, tmp, dirs_exist_ok=True, ignore=_ignore_copy,
            )
            _apply_edits(tmp, edits)
            return _run_tests(tmp, self.timeout_s, self.test_cmd)

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
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(
                project_root, tmp, dirs_exist_ok=True, ignore=_ignore_copy,
            )
            if prior_edits:
                _apply_edits(tmp, prior_edits)
            _apply_edits(tmp, edits)
            return _run_tests(tmp, self.timeout_s, self.test_cmd)

    def run_incremental(
        self,
        step_edits: list[list[dict[str, Any]]],
        project_root: str,
    ) -> dict[str, Any]:
        """Verify edits step-by-step. Stop at first failure.

        step_edits: list of edit lists, one per step in order.
        Returns outcome with steps_completed count and failure details if any.
        """
        project_root = os.path.abspath(project_root)
        accumulated: list[dict[str, Any]] = []

        for i, edits in enumerate(step_edits):
            with tempfile.TemporaryDirectory() as tmp:
                shutil.copytree(
                    project_root, tmp, dirs_exist_ok=True, ignore=_ignore_copy,
                )
                _apply_edits(tmp, accumulated)
                _apply_edits(tmp, edits)
                result = _run_tests(tmp, self.timeout_s, self.test_cmd)

            if not result["success"]:
                return {
                    "success": False,
                    "steps_completed": i,
                    "failed_at_step": i,
                    "output": result.get("output", ""),
                    "trace": result.get("trace", ""),
                    "score": 0.0,
                    "failure_analysis": result.get("failure_analysis"),
                    "failure_reason": result.get("failure_analysis", {}).get("message", ""),
                }

            for ed in edits:
                if ed.get("content") is not None:
                    accumulated.append(ed)

        return {
            "success": True,
            "steps_completed": len(step_edits),
            "output": "all steps passed",
            "trace": "",
            "score": 1.0,
        }
