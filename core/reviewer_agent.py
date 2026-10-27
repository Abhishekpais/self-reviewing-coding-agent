from typing import Optional
from pydantic import BaseModel, Field

from core.llm_client import OllamaColabClient
from core.memory_manager import WorkspaceManager
from core.schemas import MistakeItem, ReviewReport, TraceSpan
from core.trajectory_analyzer import DeterministicTrajectoryScanner


class LLMReviewAssessment(BaseModel):
    overall_process_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Process quality score from 0.0 (completely broken) to 1.0 (flawless TAR workflow and code).",
    )
    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Reviewer confidence in this diagnosis from 0.0 to 1.0.",
    )
    llm_detected_mistakes: list[MistakeItem] = Field(
        default_factory=list,
        description="Additional tool selection, workflow execution, or code bugs found in the trace or code.",
    )
    recommended_correction_prompt: str = Field(
        description="Clear, numbered instructions for the Coding Agent to fix any mistakes or improve the code."
    )


REVIEWER_SYSTEM_PROMPT = """You are an expert AI Process Reward Model (PRM) and Software Engineering Trajectory Reviewer.
Your job is to evaluate the full Thought-Action-Result (TAR) trajectory of a Coding Agent and the resulting Python code inside the sandbox.

You evaluate three specific dimensions:
1. TOOL_SELECTION_ERROR: Did the agent pick the wrong tool, pass invalid arguments, or repeat failing tool calls?
2. WORKFLOW_EXECUTION_ERROR: Did the agent skip `run_terminal_test` after editing code, use the wrong `workflow_state` label, or finish prematurely?
3. CODE_GENERATION_BUG: Does the final Python code contain logic bugs, unhandled edge cases, missing assertions, or runtime errors?

{self_healing_rules_block}

Respond strictly in the requested JSON schema. If the final code already passed `run_terminal_test` with `exit_code == 0` and has no critical bugs, give a high `overall_process_score` (>= 0.85) and only note minor workflow improvements if any exist.
"""


class ReviewerAgent:
    """Evaluates Coding Agent TAR trajectories and improves itself from user meta-feedback."""

    def __init__(
        self,
        workspace_manager: Optional[WorkspaceManager] = None,
        llm_client: Optional[OllamaColabClient] = None,
        confidence_threshold: float = 0.75,
    ) -> None:
        self.wm = workspace_manager or WorkspaceManager()
        self.llm = llm_client or OllamaColabClient()
        self.confidence_threshold = confidence_threshold

    def _build_self_healing_rules_block(self, project_id: str) -> str:
        lessons = self.wm.load_reviewer_lessons(project_id)
        if not lessons:
            return "CRITICAL SELF-CORRECTION RULES FROM USER FEEDBACK:\n- None recorded yet."

        lines = ["CRITICAL SELF-CORRECTION RULES FROM USER FEEDBACK (NEVER VIOLATE THESE):"]
        for idx, item in enumerate(lessons[-10:], start=1):
            lines.append(f"{idx}. {item.reviewer_self_healing_rule} (User correction: {item.user_correction})")
        return "\n".join(lines)

    def _format_trace_for_llm(self, spans: list[TraceSpan], project_id: str) -> str:
        parts: list[str] = [f"PROJECT ID: {project_id} | TRACE ID: {spans[0].trace_id}"]
        parts.append("\n=== FULL THOUGHT-ACTION-RESULT (TAR) TRAJECTORY ===")
        for s in spans:
            parts.append(
                f"[{s.span_id} | step={s.step_index} | state={s.workflow_state} | tool={s.tool_selected}]\n"
                f"  Thought: {s.thought}\n"
                f"  Arguments: {s.tool_arguments}\n"
                f"  Observation: status={s.observation.status}, exit_code={s.observation.exit_code}\n"
                f"  STDOUT: {s.observation.stdout}\n"
                f"  STDERR: {s.observation.stderr}"
            )

        src_dir = self.wm.get_src_dir(project_id)
        parts.append("\n=== CURRENT CODE FILES IN SANDBOX src/ ===")
        for py_file in sorted(src_dir.glob("*.py")):
            parts.append(f"--- {py_file.name} ---\n{py_file.read_text(encoding='utf-8')}\n-------------------")

        return "\n".join(parts)

    def evaluate_latest_trace(
        self,
        project_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> ReviewReport:
        """Load the active trace, run deterministic + LLM PRM evaluation, and save ReviewReport."""
        session = self.wm.get_active_session()
        project_id = project_id or session.get("active_project_id")
        trace_id = trace_id or session.get("latest_trace_id")
        if not project_id or not trace_id:
            raise ValueError("No active project or trace found in sandbox/workspaces/active_session.json.")

        spans = self.wm.load_trace(project_id=project_id, trace_id=trace_id)
        deterministic_mistakes = DeterministicTrajectoryScanner.scan(spans)

        rules_block = self._build_self_healing_rules_block(project_id)
        system_prompt = REVIEWER_SYSTEM_PROMPT.format(self_healing_rules_block=rules_block)
        trace_context = self._format_trace_for_llm(spans, project_id)

        det_summary = (
            "\n".join(
                f"- [{m.span_id}] {m.category} ({m.anti_pattern_code}, {m.severity}): {m.description}"
                for m in deterministic_mistakes
            )
            if deterministic_mistakes
            else "None detected by deterministic scanner."
        )

        user_prompt = (
            f"{trace_context}\n\n"
            f"=== DETERMINISTIC SCANNER FINDINGS ===\n{det_summary}\n\n"
            "Evaluate the trajectory and final code. Provide your structured JSON assessment."
        )

        llm_eval = self.llm.chat_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=LLMReviewAssessment,
            temperature=0.0,
        )

        # Merge deterministic findings and LLM findings without duplicating identical (span_id, anti_pattern_code)
        merged_mistakes: list[MistakeItem] = list(deterministic_mistakes)
        seen_keys = {(m.span_id, m.anti_pattern_code) for m in merged_mistakes}
        for m in llm_eval.llm_detected_mistakes:
            if (m.span_id, m.anti_pattern_code) not in seen_keys:
                merged_mistakes.append(m)
                seen_keys.add((m.span_id, m.anti_pattern_code))

        reviews_dir = self.wm.get_project_dir(project_id) / "reviews"
        review_id = f"rev_{len(list(reviews_dir.glob('review_*.json'))) + 1:03d}"

        report = ReviewReport(
            project_id=project_id,
            trace_id=trace_id,
            review_id=review_id,
            overall_process_score=round(llm_eval.overall_process_score, 2),
            confidence_score=round(llm_eval.confidence_score, 2),
            passes_confidence_threshold=llm_eval.confidence_score >= self.confidence_threshold,
            mistakes_found=merged_mistakes,
            recommended_correction_prompt=llm_eval.recommended_correction_prompt,
        )

        self.wm.save_review(report)
        return report