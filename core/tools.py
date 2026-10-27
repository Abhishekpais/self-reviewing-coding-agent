import ast
import os
import py_compile
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from core.config import VENV_PYTHON, ensure_inside_sandbox
from core.schemas import Observation


def _truncate_lines(text: str, max_lines: int = 100) -> str:
    """Cap tool output at 100 lines (SWE-agent ACI pattern) to protect Colab GPU context."""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    kept = "\n".join(lines[:max_lines])
    return f"{kept}\n... [TRUNCATED {len(lines) - max_lines} ADDITIONAL LINES]"


class ToolRegistry:
    """Sandboxed atomic tools scoped strictly to sandbox/workspaces/<project_id>/."""

    def __init__(self, project_dir: Path, default_prompt: str = "") -> None:
        self.project_dir = ensure_inside_sandbox(project_dir)
        self.src_dir = ensure_inside_sandbox(self.project_dir / "src")
        self.tests_dir = ensure_inside_sandbox(self.project_dir / "tests")
        self.src_dir.mkdir(parents=True, exist_ok=True)
        self.tests_dir.mkdir(parents=True, exist_ok=True)
        self.default_prompt = default_prompt

    def _resolve_safe_src_path(self, filepath: Optional[str] = None, auto_create_name: bool = False) -> Path:
        """Ensure target file stays strictly inside the project's sandbox src/ (or tests/) directory."""
        cleaned = (filepath or "").strip().replace("\\", "/")
        if not cleaned:
            if not auto_create_name:
                raise ValueError("Missing 'filepath' argument.")
            cleaned = self.generate_default_filename(self.default_prompt)

        # Strip leading 'src/' if the LLM includes it
        if cleaned.startswith("src/"):
            cleaned = cleaned[len("src/"):]

        # Allow test files inside tests/ or regular files inside src/
        if cleaned.startswith("tests/"):
            target = (self.project_dir / cleaned).resolve()
            if not target.is_relative_to(self.tests_dir):
                raise PermissionError(f"Path '{filepath}' escapes sandbox tests/ directory!")
        else:
            target = (self.src_dir / cleaned).resolve()
            if not target.is_relative_to(self.src_dir):
                raise PermissionError(f"Path '{filepath}' escapes sandbox src/ directory!")

        return ensure_inside_sandbox(target)

    def generate_default_filename(self, prompt: str) -> str:
        """Deterministically generate a clean Python filename when none is provided."""
        stop_words = {"write", "create", "build", "make", "a", "an", "the", "python", "program", "script", "to", "for", "in"}
        words = [w for w in re.findall(r"[a-zA-Z0-9]+", prompt.lower()) if w not in stop_words]
        slug = "_".join(words[:3]) if words else "solution"
        existing = list(self.src_dir.glob(f"task_{slug}_*.py"))
        index = len(existing) + 1
        return f"task_{slug}_{index:02d}.py"

    @staticmethod
    def get_tools_prompt() -> str:
        return (
            "AVAILABLE ATOMIC TOOLS (All scoped strictly to the project sandbox src/ directory):\n"
            "1. write_code_file(filepath: optional str, code_content: str)\n"
            "   - Writes full Python code to src/<filepath> (auto-generates filename if filepath is omitted) and runs py_compile syntax check.\n"
            "2. patch_code_file(filepath: str, search_block: str, replace_block: str)\n"
            "   - Replaces exact search_block with replace_block in src/<filepath> and validates syntax.\n"
            "3. read_code_file(filepath: str, start_line: int = 1, end_line: int = 100)\n"
            "   - Reads line-numbered source code from src/<filepath>.\n"
            "4. inspect_ast_symbols(filepath: str)\n"
            "   - Parses src/<filepath> with Python AST and lists classes, functions, arguments, and line ranges.\n"
            "5. run_terminal_test(command_or_filepath: str, timeout_sec: int = 10)\n"
            "   - Executes the script or pytest inside the sandbox using the local .venv Python interpreter.\n"
            "6. finish_task()\n"
            "   - Call ONLY whenworkflow_state == 'FINISH' and code has been verified via run_terminal_test."
        )

    def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> Observation:
        start_ns = time.perf_counter_ns()
        try:
            if tool_name == "write_code_file":
                obs = self.write_code_file(
                    filepath=arguments.get("filepath"),
                    code_content=arguments.get("code_content", ""),
                )
            elif tool_name == "patch_code_file":
                obs = self.patch_code_file(
                    filepath=arguments.get("filepath", ""),
                    search_block=arguments.get("search_block", ""),
                    replace_block=arguments.get("replace_block", ""),
                )
            elif tool_name == "read_code_file":
                obs = self.read_code_file(
                    filepath=arguments.get("filepath", ""),
                    start_line=int(arguments.get("start_line", 1)),
                    end_line=int(arguments.get("end_line", 100)),
                )
            elif tool_name == "inspect_ast_symbols":
                obs = self.inspect_ast_symbols(filepath=arguments.get("filepath", ""))
            elif tool_name == "run_terminal_test":
                obs = self.run_terminal_test(
                    command_or_filepath=arguments.get("command_or_filepath")
                    or arguments.get("filepath", ""),
                    timeout_sec=int(arguments.get("timeout_sec", 10)),
                )
            elif tool_name in ("finish_task", "none", ""):
                obs = Observation(status="SUCCESS", stdout="Task marked complete.", exit_code=0)
            else:
                obs = Observation(
                    status="ERROR",
                    stderr=f"Unknown tool '{tool_name}'. Valid tools: write_code_file, patch_code_file, read_code_file, inspect_ast_symbols, run_terminal_test, finish_task.",
                    exit_code=1,
                )
        except Exception as exc:
            obs = Observation(status="ERROR", stderr=f"{type(exc).__name__}: {exc}", exit_code=1)

        elapsed_ms = int((time.perf_counter_ns() - start_ns) / 1_000_000)
        obs.duration_ms = max(obs.duration_ms, elapsed_ms)
        return obs

    def write_code_file(self, filepath: Optional[str], code_content: str) -> Observation:
        if not code_content or not code_content.strip():
            return Observation(status="ERROR", stderr="code_content cannot be empty.", exit_code=1)

        target = self._resolve_safe_src_path(filepath, auto_create_name=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(code_content, encoding="utf-8")

        try:
            py_compile.compile(str(target), doraise=True)
        except py_compile.PyCompileError as syn_err:
            return Observation(
                status="ERROR",
                stdout=f"Wrote {target.name}, but syntax check FAILED.",
                stderr=_truncate_lines(str(syn_err)),
                exit_code=1,
            )

        rel_name = target.relative_to(self.project_dir)
        return Observation(
            status="SUCCESS",
            stdout=f"Successfully wrote {rel_name} ({len(code_content.splitlines())} lines) and verified Python syntax.",
            exit_code=0,
        )

    def patch_code_file(self, filepath: str, search_block: str, replace_block: str) -> Observation:
        target = self._resolve_safe_src_path(filepath, auto_create_name=False)
        if not target.exists():
            return Observation(status="ERROR", stderr=f"File '{filepath}' does not exist in sandbox.", exit_code=1)

        original = target.read_text(encoding="utf-8")
        if not search_block or search_block not in original:
            return Observation(
                status="ERROR",
                stderr="search_block not found verbatim in file. Call read_code_file first to inspect exact lines.",
                exit_code=1,
            )

        patched = original.replace(search_block, replace_block, 1)
        target.write_text(patched, encoding="utf-8")

        try:
            py_compile.compile(str(target), doraise=True)
        except py_compile.PyCompileError as syn_err:
            target.write_text(original, encoding="utf-8")  # Rollback broken syntax edit immediately
            return Observation(
                status="ERROR",
                stderr=f"Patch introduced a SyntaxError and was rolled back:\n{_truncate_lines(str(syn_err))}",
                exit_code=1,
            )

        return Observation(
            status="SUCCESS",
            stdout=f"Successfully patched {target.name} and verified Python syntax.",
            exit_code=0,
        )

    def read_code_file(self, filepath: str, start_line: int = 1, end_line: int = 100) -> Observation:
        target = self._resolve_safe_src_path(filepath, auto_create_name=False)
        if not target.exists():
            return Observation(status="ERROR", stderr=f"File '{filepath}' does not exist in sandbox.", exit_code=1)

        lines = target.read_text(encoding="utf-8").splitlines()
        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), max(start_line, end_line))
        numbered = [f"{i + 1:4d} | {lines[i]}" for i in range(start_idx, end_idx)]
        return Observation(
            status="SUCCESS",
            stdout=_truncate_lines("\n".join(numbered), max_lines=100),
            exit_code=0,
        )

    def inspect_ast_symbols(self, filepath: str) -> Observation:
        target = self._resolve_safe_src_path(filepath, auto_create_name=False)
        if not target.exists():
            return Observation(status="ERROR", stderr=f"File '{filepath}' does not exist in sandbox.", exit_code=1)

        source = target.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=target.name)
        symbols: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                symbols.append(f"Class '{node.name}' (lines {node.lineno}-{getattr(node, 'end_lineno', node.lineno)})")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [a.arg for a in node.args.args]
                symbols.append(
                    f"Function '{node.name}({', '.join(args)})' (lines {node.lineno}-{getattr(node, 'end_lineno', node.lineno)})"
                )

        summary = "\n".join(symbols) if symbols else "No top-level classes or functions defined."
        return Observation(status="SUCCESS", stdout=_truncate_lines(summary), exit_code=0)

    def run_terminal_test(self, command_or_filepath: str, timeout_sec: int = 10) -> Observation:
        cleaned = (command_or_filepath or "").strip()
        if not cleaned:
            # Default to running the most recently modified .py file in src/
            py_files = sorted(self.src_dir.glob("*.py"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not py_files:
                return Observation(status="ERROR", stderr="No Python files found in sandbox src/ to execute.", exit_code=1)
            target_script = py_files[0]
            cmd = [VENV_PYTHON, str(target_script)]
        elif cleaned.startswith("pytest"):
            cmd = [VENV_PYTHON, "-m", "pytest", str(self.project_dir)]
        else:
            # Extract filename if the LLM passed "python foo.py" or "python3 src/foo.py"
            parts = cleaned.split()
            script_arg = parts[-1] if parts[0] in ("python", "python3") and len(parts) > 1 else cleaned
            target_script = self._resolve_safe_src_path(script_arg, auto_create_name=False)
            if not target_script.exists():
                return Observation(
                    status="ERROR",
                    stderr=f"Cannot execute '{script_arg}': file does not exist in sandbox src/.",
                    exit_code=1,
                )
            cmd = [VENV_PYTHON, str(target_script)]

        # Construct isolated environment locked to .venv and the project sandbox
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self.src_dir)
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self.src_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=min(max(timeout_sec, 1), 30),
            )
            status = "SUCCESS" if proc.returncode == 0 else "ERROR"
            return Observation(
                status=status,
                stdout=_truncate_lines(proc.stdout.strip()),
                stderr=_truncate_lines(proc.stderr.strip()),
                exit_code=proc.returncode,
            )
        except subprocess.TimeoutExpired:
            return Observation(
                status="ERROR",
                stderr=f"Execution timed out after {timeout_sec}s inside sandbox (possible infinite loop).",
                exit_code=124,
            )