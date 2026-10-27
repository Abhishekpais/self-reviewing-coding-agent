from core.schemas import MistakeItem, TraceSpan


class DeterministicTrajectoryScanner:
    """Scans TAR trajectories for structural workflow & tool anti-patterns before LLM review."""

    @staticmethod
    def scan(spans: list[TraceSpan]) -> list[MistakeItem]:
        mistakes: list[MistakeItem] = []
        if not spans:
            return mistakes

        last_write_step = -1
        last_successful_test_step = -1

        for idx, span in enumerate(spans):
            # 1. Detect State-Tool Incoherence (e.g., calling write/patch while in PLAN state)
            if span.tool_selected in ("write_code_file", "patch_code_file") and span.workflow_state == "PLAN":
                mistakes.append(
                    MistakeItem(
                        span_id=span.span_id,
                        category="WORKFLOW_EXECUTION_ERROR",
                        anti_pattern_code="STATE_TOOL_MISMATCH",
                        description=(
                            f"In {span.span_id}, agent declared workflow_state='PLAN' while executing "
                            f"mutating tool '{span.tool_selected}' (expected workflow_state='WRITE')."
                        ),
                        severity="LOW",
                    )
                )

            # 2. Detect Thought-Action Mismatch (e.g., thought mentions running/testing, but calls read_code_file)
            thought_lower = span.thought.lower()
            if (
                any(k in thought_lower for k in ("run the script", "execute the code", "run terminal test"))
                and span.tool_selected == "read_code_file"
            ):
                mistakes.append(
                    MistakeItem(
                        span_id=span.span_id,
                        category="TOOL_SELECTION_ERROR",
                        anti_pattern_code="THOUGHT_ACTION_MISMATCH",
                        description=(
                            f"In {span.span_id}, thought stated intent to execute/test the script, "
                            f"but selected '{span.tool_selected}' instead of 'run_terminal_test'."
                        ),
                        severity="HIGH",
                    )
                )

            # 3. Detect Repeated Failing Tool Calls (Action Loop)
            if idx > 0:
                prev = spans[idx - 1]
                if (
                    prev.observation.status == "ERROR"
                    and span.tool_selected == prev.tool_selected
                    and span.tool_arguments == prev.tool_arguments
                ):
                    mistakes.append(
                        MistakeItem(
                            span_id=span.span_id,
                            category="TOOL_SELECTION_ERROR",
                            anti_pattern_code="REPEATED_FAILING_TOOL",
                            description=(
                                f"In {span.span_id}, agent repeated '{span.tool_selected}' with identical arguments "
                                f"immediately after an ERROR in {prev.span_id}."
                            ),
                            severity="HIGH",
                        )
                    )

            if span.tool_selected in ("write_code_file", "patch_code_file") and span.observation.status == "SUCCESS":
                last_write_step = span.step_index

            if span.tool_selected == "run_terminal_test" and span.observation.status == "SUCCESS":
                last_successful_test_step = span.step_index

        # 4. Detect Skipped Execution Verification before Finish
        if last_write_step != -1 and last_successful_test_step < last_write_step:
            mistakes.append(
                MistakeItem(
                    span_id=spans[-1].span_id,
                    category="WORKFLOW_EXECUTION_ERROR",
                    anti_pattern_code="SKIPPED_EXECUTION_VERIFICATION",
                    description=(
                        "Agent modified code via write_code_file/patch_code_file at step "
                        f"{last_write_step} but ended the trajectory without a subsequent successful run_terminal_test."
                    ),
                    severity="CRITICAL",
                )
            )

        # 5. Detect Ignored Error at Termination
        test_spans = [s for s in spans if s.tool_selected == "run_terminal_test"]
        if test_spans and test_spans[-1].observation.status == "ERROR":
            mistakes.append(
                MistakeItem(
                    span_id=test_spans[-1].span_id,
                    category="CODE_GENERATION_BUG",
                    anti_pattern_code="UNRESOLVED_RUNTIME_ERROR",
                    description=(
                        f"The final test execution in {test_spans[-1].span_id} failed with ERROR: "
                        f"{test_spans[-1].observation.stderr or test_spans[-1].observation.stdout}"
                    ),
                    severity="CRITICAL",
                )
            )

        return mistakes