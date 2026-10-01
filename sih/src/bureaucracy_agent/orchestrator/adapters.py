"""Adapter module: builds each agent's Request from state and stores each Result.

This is the ONLY place where agent Request schemas are constructed.
"""

from __future__ import annotations

from typing import List, Optional

from agents.intent_understanding.schema import IntentRequest, IntentResult
from agents.user_context.schema import ProfileContextRequest, ProfileContextResult, ProfileFact
from agents.information_retrieval.schema import InformationRetrievalRequest, RetrievedEvidenceResult
from agents.workflow_planning.schema import WorkflowPlanningRequest, WorkflowPlan
from agents.compliance_validation.schema import (
    ComplianceValidationRequest,
    ValidationPhase,
    ValidationResult,
    UserApprovalRecord,
    ExecutionObservation,
)
from agents.execution_assistance.schema import ExecutionRequest, ExecutionResult, UserExecutionApproval
from agents.monitoring_update.schema import MonitoringRequest, MonitoringResult
from agents.response_generation.schema import ResponseGenerationRequest, CitizenResponse

from src.bureaucracy_agent.orchestrator.hosts import get_allowed_hosts, get_official_source_registry
from src.bureaucracy_agent.orchestrator.state import OrchestratorState


# --- Intent Understanding ---
def build_intent_request(state: OrchestratorState) -> IntentRequest:
    return IntentRequest(
        request_id=state.request_id,
        user_goal=state.user_goal or "RTI Online submit request",
        language=state.language,
    )


def store_intent_result(state: OrchestratorState, result: IntentResult) -> None:
    state.intent_result = result.model_dump(mode="json")


# --- User Context & Profile ---
def build_user_context_request(state: OrchestratorState) -> ProfileContextRequest:
    intent = IntentResult.model_validate(state.intent_result)
    return ProfileContextRequest(
        request_id=state.request_id,
        intent=intent,
        vault_dir=state.vault_dir,
        profile_path=state.profile_path,
        save_confirmed_facts=False,
    )


def store_user_context_result(state: OrchestratorState, result: ProfileContextResult) -> None:
    state.profile_result = result.model_dump(mode="json")


# --- Information Retrieval ---
def build_retrieval_request(state: OrchestratorState) -> InformationRetrievalRequest:
    intent = IntentResult.model_validate(state.intent_result)
    profile = ProfileContextResult.model_validate(state.profile_result)
    return InformationRetrievalRequest(
        request_id=state.request_id,
        intent=intent,
        profile_context=profile,
        allowed_source_hosts=get_allowed_hosts("retrieval"),
        source_registry=get_official_source_registry(),
    )


def store_retrieved_evidence(state: OrchestratorState, result: RetrievedEvidenceResult) -> None:
    state.evidence_result = result.model_dump(mode="json")


# --- Workflow Planning ---
def build_workflow_planning_request(state: OrchestratorState) -> WorkflowPlanningRequest:
    intent = IntentResult.model_validate(state.intent_result)
    profile = ProfileContextResult.model_validate(state.profile_result)
    evidence = RetrievedEvidenceResult.model_validate(state.evidence_result)
    return WorkflowPlanningRequest(
        intent=intent,
        profile_context=profile,
        retrieved_evidence=evidence,
    )


def store_workflow_plan(state: OrchestratorState, result: WorkflowPlan) -> None:
    state.workflow_plan_original = result.model_dump(mode="json")
    state.workflow_plan = result.model_dump(mode="json")


# --- Compliance Validation ---
def build_compliance_validation_request(
    state: OrchestratorState,
    phase: ValidationPhase = ValidationPhase.PRE_EXECUTION,
    user_approvals: Optional[List[UserApprovalRecord]] = None,
    execution_observations: Optional[List[ExecutionObservation]] = None,
) -> ComplianceValidationRequest:
    intent = IntentResult.model_validate(state.intent_result)
    profile = ProfileContextResult.model_validate(state.profile_result)
    evidence = RetrievedEvidenceResult.model_validate(state.evidence_result)
    # Validate the scoped workflow plan view
    plan = WorkflowPlan.model_validate(state.workflow_plan)

    return ComplianceValidationRequest(
        validation_phase=phase,
        intent=intent,
        profile_context=profile,
        retrieved_evidence=evidence,
        workflow_plan=plan,
        user_approvals=user_approvals or [],
        execution_observations=execution_observations or [],
        allowed_source_hosts=get_allowed_hosts("union"),
    )


def store_validation_result(
    state: OrchestratorState,
    result: ValidationResult,
    phase: ValidationPhase = ValidationPhase.PRE_EXECUTION,
) -> None:
    if phase == ValidationPhase.PRE_EXECUTION:
        state.validation_result = result.model_dump(mode="json")
    else:
        state.post_validation_result = result.model_dump(mode="json")


def resolve_portal_starting_url(intent: IntentResult, evidence: RetrievedEvidenceResult) -> str:
    """Dynamically route to the direct action/login/registration portal for the identified service."""
    service_name = (getattr(intent, "service_name", None) or "").lower()
    goal = (getattr(intent, "original_goal", None) or getattr(intent, "normalized_goal", None) or "").lower()

    # Determine service category keywords to scope evidence records
    service_keywords: List[str] = []
    if "rti" in goal or "rti" in service_name or "right to information" in goal:
        service_keywords = ["rtionline.gov.in", "rti"]
    elif "passport" in goal or "passport" in service_name:
        service_keywords = ["passportindia.gov.in", "passport"]
    elif "aadhaar" in goal or "aadhaar" in service_name or "uidai" in goal:
        service_keywords = ["myaadhaar.uidai.gov.in", "uidai.gov.in", "aadhaar"]
    elif "consumer" in goal or "consumer" in service_name or "grievance" in goal:
        service_keywords = ["consumerhelpline.gov.in", "consumer"]
    elif "voter" in goal or "voter" in service_name or "election" in goal or "eci" in goal:
        service_keywords = ["voters.eci.gov.in", "eci.gov.in", "voter"]

    is_tracking = any(kw in goal for kw in ("track", "status", "check", "enrolment", "search"))

    # 1. Primary: Look for direct action/login/registration URL among evidence matching THIS service
    if evidence and evidence.evidence:
        matching_evidence = [
            ev for ev in evidence.evidence
            if any(sk in (ev.source_url + " " + ev.source_host + " " + ev.source_title).lower() for sk in service_keywords)
        ]

        if matching_evidence:
            if is_tracking:
                for ev in matching_evidence:
                    url = ev.source_url
                    if url and any(kw in url.lower() for kw in ("checkaadhaarstatus", "check-aadhaar-status", "status", "track")):
                        return url
            # Prioritize direct action/login/registration/application form URLs
            for ev in matching_evidence:
                url = ev.source_url
                if url and any(kw in url.lower() for kw in ("login", "signup", "register", "request", "guidelines", "myaadhaar", "user/index", "form")):
                    return url
            if "aadhaar" in service_keywords or "uidai" in service_name:
                return "https://myaadhaar.uidai.gov.in/CheckAadhaarStatus" if is_tracking else "https://myaadhaar.uidai.gov.in/login"
            return matching_evidence[0].source_url

    # 2. Secondary: Checked official sources from retrieval for THIS service
    if evidence and evidence.sources_checked:
        matching_checks = [
            c for c in evidence.sources_checked
            if c.status.value == "fetched" and c.url and any(sk in c.url.lower() for sk in service_keywords)
        ]
        if is_tracking:
            for check in matching_checks:
                if any(kw in check.url.lower() for kw in ("checkaadhaarstatus", "check-aadhaar-status", "status", "track")):
                    return check.url
        for check in matching_checks:
            if any(kw in check.url.lower() for kw in ("login", "signup", "register", "request", "guidelines", "myaadhaar")):
                return check.url
        if matching_checks and matching_checks[0].url:
            return matching_checks[0].url

    # 3. Dynamic service fallback
    if "passport" in goal or "passport" in service_name:
        return "https://services2.passportindia.gov.in/psp/trackApplication" if is_tracking else "https://services2.passportindia.gov.in/psp/login"
    if "aadhaar" in goal or "uidai" in goal or "aadhaar" in service_name:
        return "https://myaadhaar.uidai.gov.in/CheckAadhaarStatus" if is_tracking else "https://myaadhaar.uidai.gov.in/login"
    if "consumer" in goal or "grievance" in goal or "consumer" in service_name:
        return "https://consumerhelpline.gov.in/user/signup.php"
    if "voter" in goal or "election" in goal or "voter" in service_name:
        return "https://voters.eci.gov.in/login"

    if is_tracking and ("rti" in goal or "rti" in service_name):
        return "https://rtionline.gov.in/request/status.php"

    return "https://rtionline.gov.in/guidelines.php?request"


# --- Execution Assistance ---
def build_execution_request(
    state: OrchestratorState,
    selected_step_ids: List[str],
    user_approvals: List[UserExecutionApproval],
    confirmed_facts: List[ProfileFact],
) -> ExecutionRequest:
    intent = IntentResult.model_validate(state.intent_result)
    profile = ProfileContextResult.model_validate(state.profile_result)
    evidence = RetrievedEvidenceResult.model_validate(state.evidence_result)
    plan = WorkflowPlan.model_validate(state.workflow_plan)
    validation = ValidationResult.model_validate(state.validation_result)

    starting_url = resolve_portal_starting_url(intent, evidence)

    return ExecutionRequest(
        request_id=state.request_id,
        intent=intent,
        profile_context=profile,
        retrieved_evidence=evidence,
        workflow_plan=plan,
        validation_result=validation,
        selected_step_ids=selected_step_ids,
        user_approvals=user_approvals,
        confirmed_facts=confirmed_facts,
        starting_url=starting_url,
        dry_run=state.is_dry_run,
    )


def store_execution_result(state: OrchestratorState, result: ExecutionResult) -> None:
    state.execution_result = result.model_dump(mode="json")
    state.submission_attempted = result.submission_attempted
    state.confirmation_observed = result.confirmation_observed


# --- Monitoring Update ---
def build_monitoring_request(state: OrchestratorState) -> MonitoringRequest:
    intent = IntentResult.model_validate(state.intent_result)
    plan = WorkflowPlan.model_validate(state.workflow_plan)
    val_data = state.post_validation_result or state.validation_result
    validation = ValidationResult.model_validate(val_data)
    exec_result = ExecutionResult.model_validate(state.execution_result) if state.execution_result else None

    return MonitoringRequest(
        request_id=state.request_id,
        intent=intent,
        workflow_plan=plan,
        validation_result=validation,
        execution_result=exec_result,
    )


def store_monitoring_result(state: OrchestratorState, result: MonitoringResult) -> None:
    state.monitoring_result = result.model_dump(mode="json")


# --- Response Generation ---
def build_response_generation_request(state: OrchestratorState) -> ResponseGenerationRequest:
    intent = IntentResult.model_validate(state.intent_result)
    profile = ProfileContextResult.model_validate(state.profile_result)
    evidence = RetrievedEvidenceResult.model_validate(state.evidence_result)
    
    # Use original plan for full descriptive summary in citizen response
    plan_data = state.workflow_plan_original or state.workflow_plan
    plan = WorkflowPlan.model_validate(plan_data)

    # Response gets pre-execution validation_result for correct status precedence
    validation = ValidationResult.model_validate(state.validation_result)

    exec_result = ExecutionResult.model_validate(state.execution_result) if state.execution_result else None
    mon_result = MonitoringResult.model_validate(state.monitoring_result) if state.monitoring_result else None

    return ResponseGenerationRequest(
        request_id=state.request_id,
        intent=intent,
        profile_context=profile,
        retrieved_evidence=evidence,
        workflow_plan=plan,
        validation_result=validation,
        execution_result=exec_result,
        monitoring_result=mon_result,
        response_language=state.language,
    )


def store_citizen_response(state: OrchestratorState, result: CitizenResponse) -> None:
    state.citizen_response = result.model_dump(mode="json")
