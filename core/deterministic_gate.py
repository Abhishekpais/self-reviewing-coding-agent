import ast
import os
import py_compile
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.config import VENV_PYTHON, ensure_inside_sandbox
from core.memory_manager import WorkspaceManager


@dataclass
class GateResult:
    passed: bool
    rolled_back: bool
    summary: str
    details: list[str] = field(default_factory=list)


class DeterministicGate:
    """Snapshots sandbox src/, runs deterministic .venv verification checks, and rolls back broken fixes."""

    def __init__(self, workspace_manager: Optional[WorkspaceManager] = None) -> None:
        self.wm = workspace_manager or WorkspaceManager()

    def _get_snapshot_dir(self, project_id: str) -> Path:
        proj_dir = self.wm.get_project_dir(project_id)
        return ensure_inside_sandbox(proj_dir / ".snapshot_src")

    def create_snapshot(self, project_id: str) -> Path:
        """Backup sandbox/workspaces/<project_id>/src/ before running a self-healing pass."""
        src_dir = self.wm.get_src_dir(project_id)
        snap_dir = self._get_snapshot_dir(project_id)
        if snap_dir.exists():
            shutil.rmtree(snap_dir)
        shutil.copytree(src_dir, snap_dir)
        return snap_dir

    def restore_snapshot(self, project_id: str) -> bool:
        """Restore src/ from .snapshot_src/ when a self-healing patch fails deterministic checks."""
        src_dir = self.wm.get_src_dir(project_id)
        snap_dir = self._get_snapshot_dir(project_id)
        if not snap_dir.exists():
            return False
        if src_dir.exists():
            shutil.rmtree(src_dir)
        shutil.copytree(snap_dir, src_dir)
        shutil.rmtree(snap_dir)
        return True

    def clear_snapshot(self, project_id: str) -> None:
        snap_dir = self._get_snapshot_dir(project_id)
        if snap_dir.exists():
            shutil.rmtree(snap_dir)

    def verify_and_gate(self, project_id: str, timeout_sec: int = 15) -> GateResult:
        """Run 3 deterministic checks on all .py files in sandbox src/ using .venv Python."""
        src_dir = self.wm.get_src_dir(project_id)
        tests_dir = ensure_inside_sandbox(self.wm.get_project_dir(project_id) / "tests")
        py_files = sorted(src_dir.glob("*.py"))

        details: list[str] = []
        if not py_files:
            rolled = self.restore_snapshot(project_id)
            return GateResult(
                passed=False,
                rolled_back=rolled,
                summary="GATE FAILED: No Python files found in sandbox src/.",
                details=["src/ directory is empty."],
            )

        env = os.environ.copy()
        env["PYTHONPATH"] = str(src_dir)
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        for py_file in py_files:
            # Check 1: AST & py_compile Syntax Verification
            try:
                source = py_file.read_text(encoding="utf-8")
                ast.parse(source, filename=py_file.name)
                py_compile.compile(str(py_file), doraise=True)
                details.append(f"[PASS] Syntax & AST check: {py_file.name}")
            except Exception as syn_err:
                rolled = self.restore_snapshot(project_id)
                details.append(f"[FAIL] Syntax check failed on {py_file.name}: {syn_err}")
                return GateResult(
                    passed=False,
                    rolled_back=rolled,
                    summary=f"GATE FAILED (Syntax Error in {py_file.name}) -> Rolled back to snapshot.",
                    details=details,
                )

            # Check 2: Subprocess Execution inside .venv & Sandbox
            try:
                proc = subprocess.run(
                    [VENV_PYTHON, str(py_file)],
                    cwd=str(src_dir),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=timeout_sec,
                )
                if proc.returncode != 0:
                    rolled = self.restore_snapshot(project_id)
                    err_msg = (proc.stderr or proc.stdout).strip()
                    details.append(f"[FAIL] Runtime execution failed on {py_file.name} (exit_code={proc.returncode}): {err_msg}")
                    return GateResult(
                        passed=False,
                        rolled_back=rolled,
                        summary=f"GATE FAILED (Runtime Error in {py_file.name}) -> Rolled back to snapshot.",
                        details=details,
                    )
                details.append(f"[PASS] Execution check ({py_file.name}, exit_code=0): {proc.stdout.strip()[:120]}")
            except subprocess.TimeoutExpired:
                rolled = self.restore_snapshot(project_id)
                details.append(f"[FAIL] Execution timed out after {timeout_sec}s on {py_file.name}")
                return GateResult(
                    passed=False,
                    rolled_back=rolled,
                    summary=f"GATE FAILED (Timeout in {py_file.name}) -> Rolled back to snapshot.",
                    details=details,
                )

        # Check 3: Optional pytest suite if tests/ contains test_*.py files
        test_files = list(tests_dir.glob("test_*.py"))
        if test_files:
            proc = subprocess.run(
                [VENV_PYTHON, "-m", "pytest", str(tests_dir)],
                cwd=str(self.wm.get_project_dir(project_id)),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            if proc.returncode != 0:
                rolled = self.restore_snapshot(project_id)
                details.append(f"[FAIL] Pytest regression suite failed:\n{proc.stdout}\n{proc.stderr}")
                return GateResult(
                    passed=False,
                    rolled_back=rolled,
                    summary="GATE FAILED (Pytest suite failed) -> Rolled back to snapshot.",
                    details=details,
                )
            details.append("[PASS] Pytest suite passed.")

        self.clear_snapshot(project_id)
        return GateResult(
            passed=True,
            rolled_back=False,
            summary="GATE PASSED: All syntax, AST, and .venv runtime checks succeeded.",
            details=details,
        )