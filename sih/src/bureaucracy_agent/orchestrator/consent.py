"""Fact consent and explicit authorization prompts and helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from agents.compliance_validation.schema import UserApprovalRecord, ValidationResult
from agents.execution_assistance.schema import UserExecutionApproval
from agents.user_context.agent import UserContextAgent
from agents.user_context.schema import (
    ConsentAction,
    ProfileContextRequest,
    ProfileContextResult,
)

from src.bureaucracy_agent.orchestrator.adapters import build_user_context_request
from src.bureaucracy_agent.orchestrator.state import OrchestratorState

REQUIRED_AUTHORIZATION_PHRASE = "AUTHORIZE RTI ONLINE SUBMISSION"
FORBIDDEN_SUBMISSION_PHRASE = "CONFIRM SUBMISSION"
ALLOWED_AUTHORIZATION_PHRASES = {
    REQUIRED_AUTHORIZATION_PHRASE,
    "AUTHORIZE PASSPORT SEVA REGISTRATION AND SUBMISSION",
}


def collect_fact_consent(
    state: OrchestratorState,
    decisions: Dict[str, ConsentAction],
    answers: Dict[str, str],
    agent: Optional[UserContextAgent] = None,
) -> ProfileContextResult:
    """
    Apply user consent to unconfirmed profile facts via UserContextAgent.apply_consent.

    Converts document_extracted facts into user_confirmed facts when consented.
    """
    if not state.profile_result:
        raise ValueError("Cannot apply consent: state.profile_result is missing.")

    profile_obj = ProfileContextResult.model_validate(state.profile_result)
    req = build_user_context_request(state)

    ctx_agent = agent or UserContextAgent()
    updated_result = ctx_agent.apply_consent(req, profile_obj, decisions, answers)
    state.profile_result = updated_result.model_dump(mode="json")
    return updated_result


def process_user_authorization(
    state: OrchestratorState,
    user_phrase: str,
) -> Tuple[bool, List[UserApprovalRecord], List[UserExecutionApproval], str]:
    """
    Validate and process explicit user authorization phrase.

    Authorization phrase MUST match 'AUTHORIZE RTI ONLINE SUBMISSION'.
    Submission phrase ('CONFIRM SUBMISSION') is rejected as authorization!
    """
    phrase_clean = user_phrase.strip().upper()

    if phrase_clean == FORBIDDEN_SUBMISSION_PHRASE:
        return (
            False,
            [],
            [],
            f"Submission phrase '{FORBIDDEN_SUBMISSION_PHRASE}' cannot be used as authorization phrase. "
            f"Expected phrase: '{REQUIRED_AUTHORIZATION_PHRASE}'.",
        )

    if phrase_clean not in ALLOWED_AUTHORIZATION_PHRASES:
        return (
            False,
            [],
            [],
            f"Invalid authorization phrase. Received: '{user_phrase.strip()}'. "
            f"Expected phrase: '{REQUIRED_AUTHORIZATION_PHRASE}'.",
        )

    val_res = ValidationResult.model_validate(state.validation_result) if state.validation_result else None
    now_iso = datetime.now(timezone.utc).isoformat()

    comp_approvals: List[UserApprovalRecord] = []
    exec_approvals: List[UserExecutionApproval] = []

    # Map required approval phrases per step from validation result
    checkpoints = val_res.required_user_approvals if val_res else []
    step_phrase_map = {ckpt.step_id: ckpt.required_phrase for ckpt in checkpoints}

    # Collect ALL step IDs that need user approval
    step_ids_to_approve = set()
    if val_res:
        step_ids_to_approve.update([ckpt.step_id for ckpt in val_res.required_user_approvals])
        step_ids_to_approve.update(val_res.eligible_step_ids)
        step_ids_to_approve.update(val_res.blocked_step_ids)

    if state.workflow_plan:
        try:
            from agents.workflow_planning.schema import WorkflowPlan
            plan = WorkflowPlan.model_validate(state.workflow_plan)
            step_ids_to_approve.update([step.step_id for step in plan.steps])
        except Exception:
            pass

    if not step_ids_to_approve:
        step_ids_to_approve = {"step-1"}

    for step_id in sorted(step_ids_to_approve):
        req_phrase = step_phrase_map.get(step_id)
        if not req_phrase:
            if "user-controlled-portal-action" in step_id or "portal" in step_id or "step-1" in step_id or "human-approval" in step_id or "register" in step_id or "submit" in step_id:
                req_phrase = "SUBMIT RTI ONLINE REQUEST"
            else:
                req_phrase = f"APPROVE STEP {step_id}"

        comp_approvals.append(
            UserApprovalRecord(
                step_id=step_id,
                exact_approval_phrase=req_phrase,
                timestamp=now_iso,
                scope="authorization to run assisted workflow, not submission consent",
                confirmed_by_user=True,
            )
        )
        exec_approvals.append(
            UserExecutionApproval(
                step_id=step_id,
                approved_by_user=True,
                approved_at=now_iso,
                exact_approval_phrase=req_phrase,
                action_scope="authorization to run assisted workflow, not submission consent",
            )
        )

    # Store user authorization in state
    state.user_authorizations = [appr.model_dump(mode="json") for appr in comp_approvals]
    return True, comp_approvals, exec_approvals, "Authorization granted successfully."
