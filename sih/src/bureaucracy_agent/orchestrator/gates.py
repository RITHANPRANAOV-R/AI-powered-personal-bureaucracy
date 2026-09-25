"""Pure gate functions evaluating workflow readiness and pre-execution prerequisites."""

from __future__ import annotations

import importlib.util
from typing import List, Tuple

from agents.compliance_validation.schema import ValidationDecision, ValidationResult
from agents.information_retrieval.schema import RetrievedEvidenceResult, RetrievalStatus
from agents.user_context.schema import FactStatus, ProfileContextResult
from agents.workflow_planning.schema import WorkflowPlan

from src.bureaucracy_agent.orchestrator.state import OrchestratorState


def readiness_gate(state: OrchestratorState) -> Tuple[bool, List[str]]:
    """
    Readiness Gate: Pure function over agent outputs.

    Enforces that retrieval was successful, evidence and requirements were found,
    pre-execution validation did not block the plan, and portal steps are eligible.
    """
    reasons: List[str] = []

    # Check retrieval evidence
    if not state.evidence_result:
        reasons.append("No retrieval result present in workflow state.")
        return False, reasons

    evidence = RetrievedEvidenceResult.model_validate(state.evidence_result)
    if evidence.retrieval_status == RetrievalStatus.BLOCKED:
        reasons.append("Information retrieval was blocked by official sources.")
    if not evidence.evidence:
        reasons.append("Zero evidence records were retrieved from official sources.")
    if not evidence.requirements_found and not evidence.evidence:
        reasons.append("Zero requirement candidates were extracted from evidence.")

    # Check pre-execution compliance validation
    if not state.validation_result:
        reasons.append("No pre-execution validation result present in workflow state.")
        return False, reasons

    val_res = ValidationResult.model_validate(state.validation_result)
    if val_res.decision == ValidationDecision.BLOCK:
        reasons.append(f"Pre-execution validation decision is BLOCK ({val_res.summary}).")

    # Resolve portal step from plan
    if state.workflow_plan:
        plan = WorkflowPlan.model_validate(state.workflow_plan)
        portal_steps = [
            step for step in plan.steps
            if getattr(step, "step_type", None) == "manual_user_action"
            or getattr(step.step_type, "value", str(step.step_type)) == "manual_user_action"
            or step.step_id == "user-controlled-portal-action"
        ]
        if not portal_steps and plan.steps:
            # Fallback to step requiring user action or execution
            portal_steps = plan.steps

        for step in portal_steps:
            if step.step_id in val_res.blocked_step_ids:
                reasons.append(f"Portal step '{step.step_id}' is in blocked_step_ids.")
            if val_res.eligible_step_ids and step.step_id not in val_res.eligible_step_ids:
                reasons.append(f"Portal step '{step.step_id}' is not in eligible_step_ids.")

            # Check step dependencies
            for dep_id in step.depends_on:
                if dep_id in val_res.blocked_step_ids:
                    reasons.append(f"Step '{step.step_id}' depends on blocked step '{dep_id}'.")

    ok = len(reasons) == 0
    return ok, reasons


def check_browser_available() -> Tuple[bool, str]:
    """Check if Playwright and Chromium are available on the system."""
    if importlib.util.find_spec("playwright") is None:
        return False, "Playwright package is not installed."
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            # Check executable path without launching
            browser_type = p.chromium
            executable = browser_type.executable_path
            if not executable:
                return False, "Chromium browser executable not found."
    except Exception as exc:  # noqa: BLE001
        return False, f"Playwright Chromium doctor check failed: {exc}"
    return True, "Playwright Chromium available."


def pre_execution_gate(state: OrchestratorState) -> Tuple[bool, List[str]]:
    """
    Pre-execution Gate: Runs immediately before browser launch.

    Re-checks readiness_gate, authorization presence, fact consent completeness,
    browser availability, and prior submission guards.
    """
    ok_readiness, reasons = readiness_gate(state)
    if not ok_readiness:
        return False, reasons

    # 1. Authorization check
    if not state.user_authorizations:
        reasons.append("No explicit user execution authorizations present in state.")

    # 2. Fact consent completeness check for required profile facts
    if state.profile_result and state.workflow_plan:
        plan = WorkflowPlan.model_validate(state.workflow_plan)
        profile = ProfileContextResult.model_validate(state.profile_result)
        required_keys = set()
        for step in plan.steps:
            required_keys.update(step.required_fact_keys)

        for fact in profile.relevant_facts:
            if fact.key in required_keys:
                if not fact.confirmed_by_user or fact.status != FactStatus.USER_CONFIRMED:
                    reasons.append(
                        f"Fact '{fact.key}' (source: {fact.source_type.value}) is not user_confirmed."
                    )

    # 3. Doctor check: Playwright + Chromium installed (unless dry_run)
    if not state.is_dry_run:
        browser_ok, browser_msg = check_browser_available()
        if not browser_ok:
            reasons.append(f"Live execution requires browser: {browser_msg}")

    # 4. Submission guard check: No prior submission_attempted for this workflow ID
    if state.submission_attempted:
        reasons.append("Workflow has already attempted submission; re-submission is forbidden.")

    ok = len(reasons) == 0
    return ok, reasons
