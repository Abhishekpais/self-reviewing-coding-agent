import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.config import SANDBOX_ROOT, ensure_inside_sandbox
from core.schemas import (
    ReviewReport,
    ReviewerFeedbackItem,
    TraceSpan,
    utc_now_iso,
)


class WorkspaceManager:
    """Manages isolated per-project sandboxes under self_healing_agent/sandbox/workspaces/."""

    def __init__(self, sandbox_root: Path = SANDBOX_ROOT) -> None:
        self.sandbox_root = ensure_inside_sandbox(sandbox_root)
        self.sandbox_root.mkdir(parents=True, exist_ok=True)
        self.session_file = ensure_inside_sandbox(self.sandbox_root / "active_session.json")

    @staticmethod
    def _slugify(text: str, max_len: int = 28) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
        return (slug[:max_len].rstrip("_")) or "task"

    def create_or_load_project(self, name_or_prompt: str, project_id: Optional[str] = None) -> str:
        if not project_id:
            date_prefix = datetime.now().strftime("%Y%m%d_%H%M%S")
            project_id = f"proj_{date_prefix}_{self._slugify(name_or_prompt)}"

        proj_dir = self.get_project_dir(project_id)
        for subfolder in ("src", "tests", "traces", "reviews", "feedback"):
            ensure_inside_sandbox(proj_dir / subfolder).mkdir(parents=True, exist_ok=True)

        meta_file = ensure_inside_sandbox(proj_dir / "metadata.json")
        if not meta_file.exists():
            meta = {
                "project_id": project_id,
                "created_at": utc_now_iso(),
                "initial_prompt": name_or_prompt,
                "traces": [],
            }
            meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        self.set_active_session(project_id=project_id)
        return project_id

    def get_project_dir(self, project_id: str) -> Path:
        safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", project_id)
        return ensure_inside_sandbox(self.sandbox_root / safe_id)

    def get_src_dir(self, project_id: str) -> Path:
        src_dir = ensure_inside_sandbox(self.get_project_dir(project_id) / "src")
        src_dir.mkdir(parents=True, exist_ok=True)
        return src_dir

    def set_active_session(self, project_id: str, latest_trace_id: Optional[str] = None) -> None:
        current = self.get_active_session()
        if latest_trace_id is None and current.get("active_project_id") == project_id:
            latest_trace_id = current.get("latest_trace_id")
        payload = {
            "active_project_id": project_id,
            "latest_trace_id": latest_trace_id,
            "updated_at": utc_now_iso(),
        }
        self.session_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def get_active_session(self) -> dict[str, Optional[str]]:
        if not self.session_file.exists():
            return {"active_project_id": None, "latest_trace_id": None}
        return json.loads(self.session_file.read_text(encoding="utf-8"))

    def start_new_trace(self, project_id: str) -> str:
        traces_dir = ensure_inside_sandbox(self.get_project_dir(project_id) / "traces")
        existing = sorted(traces_dir.glob("trace_*.jsonl"))
        trace_id = f"trace_{len(existing) + 1:03d}"
        trace_path = ensure_inside_sandbox(traces_dir / f"{trace_id}.jsonl")
        trace_path.touch(exist_ok=True)
        self.set_active_session(project_id=project_id, latest_trace_id=trace_id)
        return trace_id

    def append_span(self, span: TraceSpan) -> Path:
        traces_dir = ensure_inside_sandbox(self.get_project_dir(span.project_id) / "traces")
        trace_file = ensure_inside_sandbox(traces_dir / f"{span.trace_id}.jsonl")
        with trace_file.open("a", encoding="utf-8") as f:
            f.write(span.model_dump_json() + "\n")
        self.set_active_session(project_id=span.project_id, latest_trace_id=span.trace_id)
        return trace_file

    def load_trace(self, project_id: Optional[str] = None, trace_id: Optional[str] = None) -> list[TraceSpan]:
        session = self.get_active_session()
        project_id = project_id or session.get("active_project_id")
        trace_id = trace_id or session.get("latest_trace_id")
        if not project_id or not trace_id:
            raise ValueError("No active project_id or trace_id found in sandbox/workspaces/active_session.json.")

        trace_file = ensure_inside_sandbox(self.get_project_dir(project_id) / "traces" / f"{trace_id}.jsonl")
        if not trace_file.exists():
            raise FileNotFoundError(f"Trace file not found: {trace_file}")

        spans: list[TraceSpan] = []
        for line in trace_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                spans.append(TraceSpan.model_validate_json(line))
        return spans

    def save_review(self, review: ReviewReport) -> Path:
        reviews_dir = ensure_inside_sandbox(self.get_project_dir(review.project_id) / "reviews")
        review_file = ensure_inside_sandbox(reviews_dir / f"review_{review.trace_id}.json")
        review_file.write_text(review.model_dump_json(indent=2), encoding="utf-8")
        return review_file

    def append_reviewer_feedback(self, item: ReviewerFeedbackItem) -> Path:
        feedback_dir = ensure_inside_sandbox(self.get_project_dir(item.project_id) / "feedback")
        feedback_file = ensure_inside_sandbox(feedback_dir / "reviewer_lessons.jsonl")
        with feedback_file.open("a", encoding="utf-8") as f:
            f.write(item.model_dump_json() + "\n")
        return feedback_file

    def load_reviewer_lessons(self, project_id: Optional[str] = None) -> list[ReviewerFeedbackItem]:
        lessons: list[ReviewerFeedbackItem] = []
        # Load lessons across all projects in the sandbox so the Reviewer AI improves globally
        for feedback_file in sorted(self.sandbox_root.glob("proj_*/feedback/reviewer_lessons.jsonl")):
            ensure_inside_sandbox(feedback_file)
            for line in feedback_file.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    lessons.append(ReviewerFeedbackItem.model_validate_json(line))
        return lessons