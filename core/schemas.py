from datetime import datetime, timezone
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Observation(BaseModel):
    status: Literal["SUCCESS", "ERROR"]
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_ms: int = 0


class TraceSpan(BaseModel):
    project_id: str
    trace_id: str
    span_id: str
    step_index: int
    timestamp: str = Field(default_factory=utc_now_iso)
    workflow_state: Literal["PLAN", "WRITE", "EXECUTE", "VERIFY", "FINISH"]
    thought: str
    tool_selected: str
    tool_arguments: dict[str, Any] = Field(default_factory=dict)
    observation: Observation


class MistakeItem(BaseModel):
    span_id: str
    category: Literal[
        "TOOL_SELECTION_ERROR",
        "WORKFLOW_EXECUTION_ERROR",
        "CODE_GENERATION_BUG",
    ]
    anti_pattern_code: str
    description: str
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class ReviewReport(BaseModel):
    project_id: str
    trace_id: str
    review_id: str
    timestamp: str = Field(default_factory=utc_now_iso)
    overall_process_score: float = Field(ge=0.0, le=1.0)
    confidence_score: float = Field(ge=0.0, le=1.0)
    passes_confidence_threshold: bool
    mistakes_found: list[MistakeItem] = Field(default_factory=list)
    recommended_correction_prompt: str


class ReviewerFeedbackItem(BaseModel):
    feedback_id: str
    project_id: str
    trace_id: str
    timestamp: str = Field(default_factory=utc_now_iso)
    reviewer_original_claim: str
    user_correction: str
    reviewer_self_healing_rule: str