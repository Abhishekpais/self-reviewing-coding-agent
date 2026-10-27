from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
import typer

from core.coding_agent import CodingAgent
from core.config import SANDBOX_ROOT, VENV_PYTHON
from core.deterministic_gate import DeterministicGate
from core.memory_manager import WorkspaceManager
from core.reviewer_agent import ReviewerAgent
from core.schemas import ReviewReport, ReviewerFeedbackItem, TraceSpan

app = typer.Typer(help="Self-Healing Coding Agent CLI (Dual-Agent TAR Evaluation & Deterministic Gating)")
console = Console()


def _print_trace_table(project_id: str, trace_id: str, spans: list[TraceSpan]) -> None:
    table = Table(title=f"TAR Trajectory | Project: {project_id} | Trace: {trace_id}", show_lines=True)
    table.add_column("Span", style="cyan", no_wrap=True)
    table.add_column("State", style="magenta", no_wrap=True)
    table.add_column("Tool Selected", style="yellow", no_wrap=True)
    table.add_column("Thought", style="white")
    table.add_column("Observation", style="green")

    for s in spans:
        status_tag = "[bold green]SUCCESS[/bold green]" if s.observation.status == "SUCCESS" else "[bold red]ERROR[/bold red]"
        out_preview = (s.observation.stdout or s.observation.stderr or "").strip()
        if len(out_preview) > 140:
            out_preview = out_preview[:140] + "..."
        table.add_row(
            s.span_id,
            s.workflow_state,
            s.tool_selected,
            s.thought,
            f"{status_tag} (exit={s.observation.exit_code})\n{out_preview}",
        )
    console.print(table)


def _print_review_report(report: ReviewReport) -> None:
    gate_badge = "[bold green]PASSES CONFIDENCE GATE[/bold green]" if report.passes_confidence_threshold else "[bold yellow]LOW CONFIDENCE[/bold yellow]"
    header = (
        f"[bold cyan]Project:[/bold cyan] {report.project_id} | "
        f"[bold cyan]Trace:[/bold cyan] {report.trace_id} | "
        f"[bold cyan]Review ID:[/bold cyan] {report.review_id}\n"
        f"[bold]Overall Process Score:[/bold] {report.overall_process_score:.2f} / 1.00 | "
        f"[bold]Confidence Score:[/bold] {report.confidence_score:.2f} ({gate_badge})"
    )
    console.print(Panel(header, title="Reviewer AI Trajectory Evaluation", border_style="cyan"))

    if report.mistakes_found:
        m_table = Table(title="Detected Trajectory & Code Mistakes", show_lines=True)
        m_table.add_column("Span", style="cyan", no_wrap=True)
        m_table.add_column("Category", style="yellow")
        m_table.add_column("Anti-Pattern", style="magenta")
        m_table.add_column("Severity", style="red", no_wrap=True)
        m_table.add_column("Description", style="white")
        for m in report.mistakes_found:
            m_table.add_row(m.span_id, m.category, m.anti_pattern_code, m.severity, m.description)
        console.print(m_table)
    else:
        console.print("[bold green]No trajectory or code mistakes flagged![/bold green]")

    console.print(
        Panel(
            report.recommended_correction_prompt,
            title="Recommended Correction Prompt for Coding Agent",
            border_style="yellow",
        )
    )


def _execute_gated_self_healing(
    wm: WorkspaceManager,
    project_id: str,
    correction_prompt: str,
) -> None:
    gate = DeterministicGate(workspace_manager=wm)
    console.print("\n[bold cyan]1. Creating deterministic snapshot of sandbox src/ ...[/bold cyan]")
    gate.create_snapshot(project_id)

    console.print("[bold cyan]2. Running Target Coding Agent with approved correction prompt...[/bold cyan]")
    coder = CodingAgent(workspace_manager=wm)
    _, new_trace_id, new_spans = coder.run_coding_task(
        user_prompt=correction_prompt,
        project_id=project_id,
    )
    _print_trace_table(project_id, new_trace_id, new_spans)

    console.print("[bold cyan]3. Running Deterministic Testing Gate (.venv syntax + AST + runtime checks)...[/bold cyan]")
    result = gate.verify_and_gate(project_id)
    style = "green" if result.passed else "red"
    console.print(
        Panel(
            "\n".join([f"[bold]{result.summary}[/bold]"] + result.details),
            title="Deterministic Gate Verdict",
            border_style=style,
        )
    )


def _interactive_hitl_loop(wm: WorkspaceManager, report: ReviewReport) -> None:
    console.print(
        "\n[bold]Human-in-the-Loop (HITL) & Reviewer Meta-Feedback Options:[/bold]\n"
        "  [bold green][A][/bold green] Approve & Auto-Heal (Send Reviewer correction to Coding Agent via Deterministic Gate)\n"
        "  [bold yellow][E][/bold yellow] Edit / Correct Reviewer AI (Teach Reviewer a self-healing lesson & optionally patch code)\n"
        "  [bold red][R][/bold red] Reject Review as False Positive (Log lesson so Reviewer stops flagging this pattern)\n"
        "  [bold cyan][S][/bold cyan] Skip / Exit without changes"
    )
    choice = Prompt.ask("Select action", choices=["A", "a", "E", "e", "R", "r", "S", "s"], default="A").upper()

    if choice == "A":
        _execute_gated_self_healing(wm, report.project_id, report.recommended_correction_prompt)

    elif choice == "E":
        wrong_claim = Prompt.ask("What did the Reviewer AI get wrong in this review?")
        user_fix = Prompt.ask("What is your corrected assessment / rule?")
        rule = Prompt.ask(
            "State a concise rule the Reviewer AI must follow on future runs",
            default=f"Do not flag false positives when: {user_fix}",
        )
        lessons = wm.load_reviewer_lessons(report.project_id)
        item = ReviewerFeedbackItem(
            feedback_id=f"fb_{len(lessons) + 1:03d}",
            project_id=report.project_id,
            trace_id=report.trace_id,
            reviewer_original_claim=wrong_claim,
            user_correction=user_fix,
            reviewer_self_healing_rule=rule,
        )
        saved_path = wm.append_reviewer_feedback(item)
        console.print(f"[bold green]Saved Reviewer Self-Healing Lesson to:[/bold green] {saved_path}")

        if Confirm.ask("Would you also like to send a custom correction prompt to the Coding Agent now?", default=False):
            custom_prompt = Prompt.ask("Enter correction prompt for Coding Agent", default=user_fix)
            _execute_gated_self_healing(wm, report.project_id, custom_prompt)

    elif choice == "R":
        reason = Prompt.ask("Briefly state why this review is a false positive so the Reviewer learns")
        lessons = wm.load_reviewer_lessons(report.project_id)
        item = ReviewerFeedbackItem(
            feedback_id=f"fb_{len(lessons) + 1:03d}",
            project_id=report.project_id,
            trace_id=report.trace_id,
            reviewer_original_claim=report.recommended_correction_prompt,
            user_correction=f"Rejected as false positive: {reason}",
            reviewer_self_healing_rule=f"NEVER flag as an error when: {reason}",
        )
        saved_path = wm.append_reviewer_feedback(item)
        console.print(f"[bold green]Logged false-positive suppression rule to:[/bold green] {saved_path}")
    else:
        console.print("[dim]Exited without applying changes.[/dim]")


@app.command()
def code(
    prompt: str = typer.Argument(..., help="Natural language coding task for the Target Coding Agent."),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Existing project_id in sandbox/workspaces/."),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Optional target Python filename in src/."),
    max_steps: int = typer.Option(6, "--max-steps", help="Maximum TAR steps."),
) -> None:
    """Run the Target Coding Agent inside the sandbox and record its TAR trajectory."""
    wm = WorkspaceManager()
    coder = CodingAgent(workspace_manager=wm)
    console.print(Panel(f"[bold]Task:[/bold] {prompt}\n[dim]Sandbox: {SANDBOX_ROOT} | Python: {VENV_PYTHON}[/dim]", title="Target Coding Agent", border_style="green"))
    project_id, trace_id, spans = coder.run_coding_task(
        user_prompt=prompt,
        project_id=project,
        default_filename=file,
        max_steps=max_steps,
    )
    _print_trace_table(project_id, trace_id, spans)


@app.command()
def review(
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID to review (defaults to active session)."),
    trace: Optional[str] = typer.Option(None, "--trace", "-t", help="Trace ID to review (defaults to latest trace)."),
) -> None:
    """Evaluate the latest TAR trajectory with Reviewer AI and launch the HITL Self-Healing Gate."""
    wm = WorkspaceManager()
    reviewer = ReviewerAgent(workspace_manager=wm)
    report = reviewer.evaluate_latest_trace(project_id=project, trace_id=trace)
    _print_review_report(report)
    _interactive_hitl_loop(wm, report)


@app.command()
def heal(
    prompt: str = typer.Argument(..., help="Natural language coding task for closed-loop Code -> Review -> Self-Heal."),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Optional project_id."),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Optional target Python filename in src/."),
) -> None:
    """Run the complete closed-loop pipeline: Code -> Trace -> Review -> HITL Gate -> Deterministic Self-Heal."""
    wm = WorkspaceManager()
    coder = CodingAgent(workspace_manager=wm)
    console.print(Panel(f"[bold]Closed-Loop Self-Healing Task:[/bold] {prompt}", border_style="magenta"))

    project_id, trace_id, spans = coder.run_coding_task(
        user_prompt=prompt,
        project_id=project,
        default_filename=file,
    )
    _print_trace_table(project_id, trace_id, spans)

    reviewer = ReviewerAgent(workspace_manager=wm)
    report = reviewer.evaluate_latest_trace(project_id=project_id, trace_id=trace_id)
    _print_review_report(report)
    _interactive_hitl_loop(wm, report)


@app.command()
def status() -> None:
    """Display active sandbox session, projects, and learned Reviewer self-correction rules."""
    wm = WorkspaceManager()
    session = wm.get_active_session()
    lessons = wm.load_reviewer_lessons()
    console.print(
        Panel(
            f"[bold cyan]Sandbox Root:[/bold cyan] {SANDBOX_ROOT}\n"
            f"[bold cyan]Active .venv Python:[/bold cyan] {VENV_PYTHON}\n"
            f"[bold cyan]Active Project ID:[/bold cyan] {session.get('active_project_id')}\n"
            f"[bold cyan]Latest Trace ID:[/bold cyan] {session.get('latest_trace_id')}\n"
            f"[bold cyan]Learned Reviewer Rules:[/bold cyan] {len(lessons)}",
            title="Self-Healing Coding Agent Status",
            border_style="green",
        )
    )


if __name__ == "__main__":
    app()