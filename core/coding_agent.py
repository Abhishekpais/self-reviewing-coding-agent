from typing import Literal, Optional
from pydantic import BaseModel, Field

from core.llm_client import OllamaColabClient
from core.memory_manager import WorkspaceManager
from core.schemas import Observation, TraceSpan
from core.tools import ToolRegistry


class ToolArgumentsSchema(BaseModel):
    """Explicit tool arguments schema so Ollama's JSON grammar compiler never drops fields."""
    filepath: Optional[str] = Field(
        default=None,
        description="Target Python filename inside sandbox src/ (e.g., 'solution.py'). Leave null to auto-generate.",
    )
    code_content: Optional[str] = Field(
        default=None,
        description="Complete valid Python source code when calling write_code_file.",
    )
    search_block: Optional[str] = Field(
        default=None,
        description="Exact lines to search for when calling patch_code_file.",
    )
    replace_block: Optional[str] = Field(
        default=None,
        description="Replacement lines when calling patch_code_file.",
    )
    command_or_filepath: Optional[str] = Field(
        default=None,
        description="Filename (e.g., 'solution.py') or 'pytest' when calling run_terminal_test.",
    )
    start_line: Optional[int] = Field(default=1, description="Start line for read_code_file.")
    end_line: Optional[int] = Field(default=100, description="End line for read_code_file.")


class AgentStepResponse(BaseModel):
    workflow_state: Literal["PLAN", "WRITE", "EXECUTE", "VERIFY", "FINISH"]
    thought: str = Field(
        description="Clear reasoning explaining why you chose this workflow_state and tool."
    )
    tool_selected: Literal[
        "write_code_file",
        "patch_code_file",
        "read_code_file",
        "inspect_ast_symbols",
        "run_terminal_test",
        "finish_task",
    ]
    tool_arguments: ToolArgumentsSchema = Field(default_factory=ToolArgumentsSchema)
    final_summary: Optional[str] = Field(
        default=None,
        description="Populate when workflow_state is FINISH to summarize the verified solution.",
    )


CODING_AGENT_SYSTEM_PROMPT = """You are an autonomous Software Engineering Coding Agent running inside a strict local Python virtual environment (.venv) and project sandbox.
You solve coding tasks step-by-step using a strict Thought-Action-Result (TAR) loop.

{tools_prompt}

MANDATORY WORKFLOW RULES:
1. Follow a logical state progression: PLAN -> WRITE -> EXECUTE -> VERIFY -> FINISH.
2. When writing a new script, call `write_code_file` with complete, runnable Python code in `code_content` (include a `if __name__ == "__main__":` block with `print(...)` and `assert` statements so execution produces verifiable output).
3. After calling `write_code_file` or `patch_code_file`, you MUST call `run_terminal_test` in the next step to execute the script and verify `exit_code == 0` before transitioning to `FINISH`.
4. If `run_terminal_test` returns an `ERROR` or non-empty `stderr`, inspect and fix the bug using `write_code_file` or `patch_code_file`, then re-run `run_terminal_test`.
5. Only set `workflow_state = "FINISH"` and `tool_selected = "finish_task"` AFTER `run_terminal_test` succeeds with `exit_code == 0`.
"""


class CodingAgent:
    """Target Coding Agent that executes tasks inside the sandbox and logs TAR trace spans."""

    def __init__(
        self,
        workspace_manager: Optional[WorkspaceManager] = None,
        llm_client: Optional[OllamaColabClient] = None,
    ) -> None:
        self.wm = workspace_manager or WorkspaceManager()
        self.llm = llm_client or OllamaColabClient()

    def _get_existing_sandbox_context(self, project_id: str) -> str:
        """Include existing files in sandbox src/ when running a self-healing correction pass."""
        src_dir = self.wm.get_src_dir(project_id)
        py_files = sorted(src_dir.glob("*.py"))
        if not py_files:
            return "Sandbox src/ directory is currently empty (no files created yet)."

        snippets: list[str] = ["EXISTING FILES IN SANDBOX src/:"]
        for f in py_files:
            content = f.read_text(encoding="utf-8")
            snippets.append(f"--- {f.name} ---\n{content}\n-------------------")
        return "\n".join(snippets)

    def run_coding_task(
        self,
        user_prompt: str,
        project_id: Optional[str] = None,
        default_filename: Optional[str] = None,
        max_steps: int = 6,
    ) -> tuple[str, str, list[TraceSpan]]:
        """Execute a coding task or Reviewer correction prompt and return (project_id, trace_id, spans)."""
        project_id = self.wm.create_or_load_project(user_prompt, project_id=project_id)
        trace_id = self.wm.start_new_trace(project_id)
        project_dir = self.wm.get_project_dir(project_id)
        tools = ToolRegistry(project_dir=project_dir, default_prompt=user_prompt)

        system_prompt = CODING_AGENT_SYSTEM_PROMPT.format(tools_prompt=tools.get_tools_prompt())
        sandbox_context = self._get_existing_sandbox_context(project_id)

        history_lines: list[str] = []
        recorded_spans: list[TraceSpan] = []

        for step_idx in range(1, max_steps + 1):
            history_block = (
                "\n".join(history_lines)
                if history_lines
                else "No steps executed yet. Start by writing or inspecting code."
            )
            file_hint = (
                f"\nPreferred filename: {default_filename}"
                if default_filename
                else "\nIf creating a new file, you may provide a clean `.py` filename or leave `filepath` null to auto-generate."
            )

            step_user_prompt = (
                f"TASK / INSTRUCTION:\n{user_prompt}{file_hint}\n\n"
                f"{sandbox_context}\n\n"
                f"TRAJECTORY HISTORY (Current Trace {trace_id}, Step {step_idx} of {max_steps}):\n"
                f"{history_block}\n\n"
                "Respond with your next structured JSON action."
            )

            step_resp = self.llm.chat_structured(
                system_prompt=system_prompt,
                user_prompt=step_user_prompt,
                response_model=AgentStepResponse,
                temperature=0.2,
            )

            args_dict = step_resp.tool_arguments.model_dump(exclude_none=True)
            if default_filename and step_resp.tool_selected == "write_code_file" and not args_dict.get("filepath"):
                args_dict["filepath"] = default_filename

            if step_resp.workflow_state == "FINISH" or step_resp.tool_selected == "finish_task":
                obs = Observation(
                    status="SUCCESS",
                    stdout=step_resp.final_summary or "Agent finished task.",
                    exit_code=0,
                    duration_ms=0,
                )
            else:
                obs = tools.execute_tool(step_resp.tool_selected, args_dict)

            span = TraceSpan(
                project_id=project_id,
                trace_id=trace_id,
                span_id=f"span_{step_idx:02d}",
                step_index=step_idx,
                workflow_state=step_resp.workflow_state,
                thought=step_resp.thought,
                tool_selected=step_resp.tool_selected,
                tool_arguments=args_dict,
                observation=obs,
            )
            self.wm.append_span(span)
            recorded_spans.append(span)

            history_lines.append(
                f"[Step {step_idx} | State={span.workflow_state} | Tool={span.tool_selected}({args_dict})]\n"
                f"  Thought: {span.thought}\n"
                f"  Observation ({obs.status}, exit_code={obs.exit_code}):\n"
                f"  STDOUT: {obs.stdout}\n"
                f"  STDERR: {obs.stderr}"
            )

            if step_resp.workflow_state == "FINISH" or step_resp.tool_selected == "finish_task":
                break

        return project_id, trace_id, recorded_spans