"""Finalizer module: derives terminal workflow status from state and execution evidence.

Response generation never sets workflow status. Status is derived deterministically here.
"""

from __future__ import annotations

from agents.execution_assistance.schema import ExecutionResult, ExecutionStatus
from src.bureaucracy_agent.orchestrator.state import OrchestratorState
from src.bureaucracy_agent.orchestrator.statuses import WorkflowStatus


def derive_terminal_status(state: OrchestratorState) -> WorkflowStatus:
    """
    Derive final WorkflowStatus after ResponseGeneration.

    Precedence:
    1. If currently in a PAUSED_* state -> keep PAUSED_*
    2. If confirmation_observed is True -> COMPLETED
    3. If submission_attempted is True but no confirmation -> UNCERTAIN
    4. If user explicitly cancelled / declined at review -> CANCELLED
    5. If gate / compliance blocked state -> STOP_BLOCKED
    6. If driver or execution failed -> FAILED
    """
    # 1. Retain active pauses
    if state.workflow_status.is_paused:
        return state.workflow_status

    # Check execution result if available
    exec_status = None
    if state.execution_result:
        try:
            exec_res = ExecutionResult.model_validate(state.execution_result)
            exec_status = exec_res.execution_status
        except Exception:  # noqa: BLE001
            pass

    # 2. Confirmation observed -> COMPLETED
    if state.confirmation_observed or exec_status == ExecutionStatus.CONFIRMATION_OBSERVED:
        return WorkflowStatus.COMPLETED

    # 3. Submission attempted without confirmation -> UNCERTAIN
    if state.submission_attempted or exec_status == ExecutionStatus.SUBMISSION_ATTEMPTED:
        return WorkflowStatus.UNCERTAIN

    # 4. Cancelled at review
    if exec_status == ExecutionStatus.CANCELLED:
        return WorkflowStatus.CANCELLED

    # 5. Gate / compliance stop
    if state.workflow_status == WorkflowStatus.STOP_BLOCKED or state.terminal_reason.startswith("STOP_BLOCKED"):
        return WorkflowStatus.STOP_BLOCKED

    # 6. Driver failure / error
    if state.workflow_status == WorkflowStatus.FAILED or exec_status == ExecutionStatus.FAILED:
        return WorkflowStatus.FAILED

    # Default fallback if plan completed without browser execution (e.g. info-only plan)
    if state.validation_result and not state.errors:
        return WorkflowStatus.COMPLETED

    return WorkflowStatus.FAILED
