"""Pure routing functions for the Orchestrator transition table.

Every function logs a structured [ROUTE] line.
"""

from __future__ import annotations

from typing import Tuple

from agents.compliance_validation.schema import IssueCategory, IssueSeverity, ValidationDecision, ValidationResult
from agents.execution_assistance.schema import ExecutionResult, ExecutionStatus
from agents.intent_understanding.schema import IntentResult

from src.bureaucracy_agent.orchestrator.gates import pre_execution_gate, readiness_gate
from src.bureaucracy_agent.orchestrator.logging_setup import log_route
from src.bureaucracy_agent.orchestrator.state import OrchestratorState


def route_after_intent(state: OrchestratorState) -> str:
    """Route after Intent Understanding Agent node."""
    res_dict = state.intent_result or {}
    try:
        intent = IntentResult.model_validate(res_dict)
        if intent.needs_clarification or len(intent.clarification_questions) > 0:
            log_route("INTENT", "PAUSED_NEEDS_INPUT", "Intent requested clarification")
            return "PAUSED_NEEDS_INPUT"
    except Exception:  # noqa: BLE001
        pass

    log_route("INTENT", "USER_CONTEXT", "Intent understanding complete")
    return "USER_CONTEXT"


def route_after_user_context(state: OrchestratorState) -> str:
    """Route after User Context & Profile Agent node."""
    log_route("USER_CONTEXT", "RETRIEVAL", "User context built")
    return "RETRIEVAL"


def route_after_retrieval(state: OrchestratorState) -> str:
    """Route after Information Retrieval Agent node."""
    log_route("RETRIEVAL", "PLANNING", "Retrieval complete (encoding status in evidence result)")
    return "PLANNING"


def route_after_planning(state: OrchestratorState) -> str:
    """Route after Workflow Planning Agent node."""
    log_route("PLANNING", "COMPLIANCE_PRE", "Workflow plan created")
    return "COMPLIANCE_PRE"


def route_after_compliance_pre(state: OrchestratorState) -> str:
    """
    Route after Pre-Execution Compliance Validation Agent node.

    Classifies validation issues & gates:
    1. Blocker issue / decision=block / readiness_gate fails -> STOP_BLOCKED
    2. fact_unconfirmed issue present -> PAUSED_FACT_CONSENT
    3. approval_missing issue present -> PAUSED_NEEDS_AUTHORIZATION
    4. decision=approve with approvals valid -> pre_execution_gate -> EXECUTION
    """
    val_res = ValidationResult.model_validate(state.validation_result) if state.validation_result else None
    if not val_res:
        log_route("COMPLIANCE_PRE", "STOP_BLOCKED", "Missing validation result")
        return "STOP_BLOCKED"

    # Check readiness gate
    ok_readiness, readiness_reasons = readiness_gate(state)
    if not ok_readiness:
        state.gate_reasons = readiness_reasons
        log_route("COMPLIANCE_PRE", "STOP_BLOCKED", f"Readiness gate failed: {readiness_reasons}")
        return "STOP_BLOCKED"

    # Check top-level validation decision & issues
    if val_res.decision == ValidationDecision.BLOCK:
        log_route("COMPLIANCE_PRE", "STOP_BLOCKED", "Validation decision is BLOCK")
        return "STOP_BLOCKED"

    has_blocker = any(issue.severity == IssueSeverity.BLOCKER for issue in val_res.issues)
    if has_blocker:
        log_route("COMPLIANCE_PRE", "STOP_BLOCKED", "Validation contains blocker issue")
        return "STOP_BLOCKED"

    # Check unconfirmed facts issue
    has_unconfirmed_fact = any(issue.category == IssueCategory.FACT_UNCONFIRMED for issue in val_res.issues)
    if has_unconfirmed_fact:
        log_route("COMPLIANCE_PRE", "PAUSED_FACT_CONSENT", "Validation flagged unconfirmed facts")
        return "PAUSED_FACT_CONSENT"

    # Check authorization missing issue or state user_authorizations
    has_approval_missing = any(issue.category == IssueCategory.APPROVAL_MISSING for issue in val_res.issues)
    if has_approval_missing or not state.user_authorizations:
        log_route("COMPLIANCE_PRE", "PAUSED_NEEDS_AUTHORIZATION", "User authorization required for plan execution")
        return "PAUSED_NEEDS_AUTHORIZATION"

    # Evaluate pre-execution gate before entering execution
    ok_pre_exec, pre_exec_reasons = pre_execution_gate(state)
    if not ok_pre_exec:
        state.gate_reasons = pre_exec_reasons
        log_route("COMPLIANCE_PRE", "STOP_BLOCKED", f"Pre-execution gate failed: {pre_exec_reasons}")
        return "STOP_BLOCKED"

    log_route("COMPLIANCE_PRE", "EXECUTION", "Pre-execution compliance checks passed")
    return "EXECUTION"


def route_after_execution(state: OrchestratorState) -> str:
    """Route after Execution stage."""
    exec_res = ExecutionResult.model_validate(state.execution_result) if state.execution_result else None
    if not exec_res:
        log_route("EXECUTION", "RESPONSE", "Missing execution result")
        return "RESPONSE"

    status = exec_res.execution_status
    if status == ExecutionStatus.PAUSED_FOR_USER or status == ExecutionStatus.NEEDS_USER_INPUT:
        # Check if pause reason was payment
        if any("payment" in p.reason.lower() for p in exec_res.user_pause_points):
            log_route("EXECUTION", "PAUSED_PAYMENT", "Execution paused for payment")
            return "PAUSED_PAYMENT"
        log_route("EXECUTION", "PAUSED_CAPTCHA", "Execution paused for CAPTCHA/user challenge")
        return "PAUSED_CAPTCHA"

    if status in {ExecutionStatus.FAILED, ExecutionStatus.CANCELLED, ExecutionStatus.BLOCKED}:
        log_route("EXECUTION", "RESPONSE", f"Execution exited with status {status.value}")
        return "RESPONSE"

    log_route("EXECUTION", "COMPLIANCE_POST", "Execution complete, proceeding to post-execution compliance")
    return "COMPLIANCE_POST"


def route_after_compliance_post(state: OrchestratorState) -> str:
    """Route after Post-Execution Compliance Validation Agent node."""
    log_route("COMPLIANCE_POST", "MONITORING", "Post-execution compliance check complete")
    return "MONITORING"


def route_after_monitoring(state: OrchestratorState) -> str:
    """Route after Monitoring Update Agent node."""
    log_route("MONITORING", "RESPONSE", "Monitoring update complete")
    return "RESPONSE"


def route_after_response(state: OrchestratorState) -> str:
    """Route after Response Generation Agent node."""
    log_route("RESPONSE", "END", "Response generation complete")
    return "END"


def route_after_stop_blocked(state: OrchestratorState) -> str:
    """Route when workflow is blocked at compliance/gate."""
    log_route("STOP_BLOCKED", "RESPONSE", "Bypassing execution to response generation")
    return "RESPONSE"
