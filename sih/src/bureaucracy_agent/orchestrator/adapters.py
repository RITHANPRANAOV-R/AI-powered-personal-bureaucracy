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
        starting_url="https://rtionline.gov.in/guidelines.php?request",
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
