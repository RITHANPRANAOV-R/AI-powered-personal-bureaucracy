"""End-to-end Local Multi-Agent Graph Runner for Bureaucracy Assistant."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from src.bureaucracy_agent.orchestrator.state import OrchestratorState
from src.bureaucracy_agent.orchestrator.checkpoints import SqliteCheckpointStore
from src.bureaucracy_agent.orchestrator import router
from src.bureaucracy_agent.orchestrator.retries import execute_with_retry

# Specialist agent imports
from agents.intent_understanding.agent import IntentUnderstandingAgent
from agents.intent_understanding.schema import IntentRequest, IntentResult

from agents.user_context.agent import UserContextAgent
from agents.user_context.schema import ProfileContextRequest, ProfileContextResult

from agents.information_retrieval.agent import InformationRetrievalAgent
from agents.information_retrieval.schema import InformationRetrievalRequest, RetrievedEvidenceResult

from agents.workflow_planning.agent import WorkflowPlanningAgent
from agents.workflow_planning.schema import WorkflowPlanningRequest, WorkflowPlan

from agents.compliance_validation.agent import ComplianceValidationAgent
from agents.compliance_validation.schema import (
    ComplianceValidationRequest,
    ValidationPhase,
    ValidationResult,
    UserApprovalRecord,
)

from agents.execution_assistance.agent import ExecutionAgent
from agents.execution_assistance.schema import ExecutionRequest, ExecutionResult, UserExecutionApproval

from agents.monitoring_update.agent import MonitoringUpdateAgent
from agents.monitoring_update.schema import MonitoringRequest, MonitoringResult

from agents.response_generation.agent import ResponseGenerationAgent
from agents.response_generation.schema import ResponseGenerationRequest, CitizenResponse


logger = logging.getLogger(__name__)


class OrchestratorGraph:
    """End-to-end multi-agent workflow coordinator with state checkpointing."""

    def __init__(self, checkpoint_store: Optional[SqliteCheckpointStore] = None) -> None:
        self.checkpoint_store = checkpoint_store or SqliteCheckpointStore()
        
        # Instantiate specialist agents
        self.agent1_intent = IntentUnderstandingAgent(prefer_ollama=False)
        self.agent2_context = UserContextAgent()
        self.agent3_retrieval = InformationRetrievalAgent(allow_llm=False)
        self.agent4_planning = WorkflowPlanningAgent()
        self.agent5_compliance = ComplianceValidationAgent()
        self.agent6_execution = ExecutionAgent()
        self.agent7_monitoring = MonitoringUpdateAgent()
        self.agent8_response = ResponseGenerationAgent(allow_llm=False)

    def run(self, state: OrchestratorState) -> OrchestratorState:
        """Run or resume state machine execution from current state.current_node."""
        state.workflow_status = "IN_PROGRESS"
        self.checkpoint_store.save_checkpoint(state)

        while state.workflow_status == "IN_PROGRESS" and state.current_node != "END":
            node = state.current_node
            
            if node in ("START", "INTENT_UNDERSTANDING"):
                state = self._node_intent_understanding(state)
            elif node == "USER_CONTEXT":
                state = self._node_user_context(state)
            elif node == "INFORMATION_RETRIEVAL":
                state = self._node_information_retrieval(state)
            elif node == "WORKFLOW_PLANNING":
                state = self._node_workflow_planning(state)
            elif node == "COMPLIANCE_VALIDATION_PRE":
                state = self._node_compliance_validation_pre(state)
            elif node == "EXECUTION_ASSISTANCE":
                state = self._node_execution_assistance(state)
            elif node == "COMPLIANCE_VALIDATION_POST":
                state = self._node_compliance_validation_post(state)
            elif node == "MONITORING_UPDATE":
                state = self._node_monitoring_update(state)
            elif node == "RESPONSE_GENERATION":
                state = self._node_response_generation(state)
            elif node == "STOP_BLOCKED":
                state.workflow_status = "STOP_BLOCKED"
                state = self._node_response_generation(state)
                break
            elif node in ("NEEDS_USER_INPUT", "AUTHORIZATION_REQUIRED", "PAUSED_CAPTCHA"):
                if node == "NEEDS_USER_INPUT":
                    state.workflow_status = "PAUSED_NEEDS_INPUT"
                elif node == "PAUSED_CAPTCHA":
                    state.workflow_status = "PAUSED_CAPTCHA"
                elif node == "AUTHORIZATION_REQUIRED":
                    state.workflow_status = "PAUSED_NEEDS_AUTHORIZATION"
                self.checkpoint_store.save_checkpoint(state)
                break
            else:
                logger.error(f"Unknown graph node: {node}")
                state.workflow_status = "FAILED"
                state.errors.append(f"Unknown node: {node}")
                self.checkpoint_store.save_checkpoint(state)
                break

        return state

    # --- Graph Node Implementations ---

    def _node_intent_understanding(self, state: OrchestratorState) -> OrchestratorState:
        state.current_node = "INTENT_UNDERSTANDING"
        req = IntentRequest(
            user_goal=state.user_goal or "Passport Seva online registration",
            request_id=state.request_id,
        )
        res = self.agent1_intent.understand_intent(req)
        state.intent_result = res.model_dump(mode="json")
        
        next_node = router.route_after_intent_understanding(state)
        state.current_node = next_node
        self.checkpoint_store.save_checkpoint(state)
        return state

    def _node_user_context(self, state: OrchestratorState) -> OrchestratorState:
        state.current_node = "USER_CONTEXT"
        intent_obj = IntentResult.model_validate(state.intent_result)
        req = ProfileContextRequest(
            request_id=state.request_id,
            intent=intent_obj,
            vault_dir="data/vault",
            profile_path="data/profile.example.json",
        )
        res = self.agent2_context.build_user_context(req)
        state.profile_result = res.model_dump(mode="json")

        next_node = router.route_after_user_context(state)
        state.current_node = next_node
        self.checkpoint_store.save_checkpoint(state)
        return state

    def _node_information_retrieval(self, state: OrchestratorState) -> OrchestratorState:
        state.current_node = "INFORMATION_RETRIEVAL"
        intent_obj = IntentResult.model_validate(state.intent_result)
        profile_obj = ProfileContextResult.model_validate(state.profile_result)
        
        req = InformationRetrievalRequest(
            request_id=state.request_id,
            intent=intent_obj,
            profile_context=profile_obj,
        )
        res = execute_with_retry(
            lambda: self.agent3_retrieval.retrieve_information(req),
            is_idempotent=True,
            max_retries=3,
        )
        state.evidence_result = res.model_dump(mode="json")

        next_node = router.route_after_information_retrieval(state)
        state.current_node = next_node
        self.checkpoint_store.save_checkpoint(state)
        return state

    def _node_workflow_planning(self, state: OrchestratorState) -> OrchestratorState:
        state.current_node = "WORKFLOW_PLANNING"
        intent_obj = IntentResult.model_validate(state.intent_result)
        profile_obj = ProfileContextResult.model_validate(state.profile_result)
        evidence_obj = RetrievedEvidenceResult.model_validate(state.evidence_result)

        req = WorkflowPlanningRequest(
            intent=intent_obj,
            profile_context=profile_obj,
            retrieved_evidence=evidence_obj,
        )
        res = self.agent4_planning.create_workflow_plan(req)
        state.workflow_plan = res.model_dump(mode="json")

        next_node = router.route_after_workflow_planning(state)
        state.current_node = next_node
        self.checkpoint_store.save_checkpoint(state)
        return state

    def _node_compliance_validation_pre(self, state: OrchestratorState) -> OrchestratorState:
        state.current_node = "COMPLIANCE_VALIDATION_PRE"
        intent_obj = IntentResult.model_validate(state.intent_result)
        profile_obj = ProfileContextResult.model_validate(state.profile_result)
        evidence_obj = RetrievedEvidenceResult.model_validate(state.evidence_result)
        plan_obj = WorkflowPlan.model_validate(state.workflow_plan)

        val_user_apps = []
        if state.one_run_authorization and state.one_run_authorization.authorized:
            now_iso = datetime.now(timezone.utc).isoformat()
            for s in plan_obj.steps:
                val_user_apps.append(
                    UserApprovalRecord(
                        step_id=s.step_id,
                        exact_approval_phrase="SUBMIT PASSPORT SEVA REGISTRATION",
                        timestamp=now_iso,
                        confirmed_by_user=True,
                    )
                )

        req = ComplianceValidationRequest(
            validation_phase=ValidationPhase.PRE_EXECUTION,
            intent=intent_obj,
            profile_context=profile_obj,
            retrieved_evidence=evidence_obj,
            workflow_plan=plan_obj,
            user_approvals=val_user_apps,
        )
        res = self.agent5_compliance.validate_workflow(req)
        state.validation_result = res.model_dump(mode="json")

        next_node = router.route_after_compliance_validation_pre(state)
        state.current_node = next_node
        self.checkpoint_store.save_checkpoint(state)
        return state

    def _node_execution_assistance(self, state: OrchestratorState) -> OrchestratorState:
        state.current_node = "EXECUTION_ASSISTANCE"
        intent_obj = IntentResult.model_validate(state.intent_result)
        profile_obj = ProfileContextResult.model_validate(state.profile_result)
        evidence_obj = RetrievedEvidenceResult.model_validate(state.evidence_result)
        plan_obj = WorkflowPlan.model_validate(state.workflow_plan)
        validation_obj = ValidationResult.model_validate(state.validation_result)

        if validation_obj and validation_obj.eligible_step_ids:
            step_ids = list(validation_obj.eligible_step_ids)
        elif plan_obj and plan_obj.steps:
            step_ids = [s.step_id for s in plan_obj.steps]
        else:
            step_ids = ["step-1"]

        exec_user_apps = []
        if state.one_run_authorization and state.one_run_authorization.authorized:
            now_iso = datetime.now(timezone.utc).isoformat()
            for sid in step_ids:
                exec_user_apps.append(
                    UserExecutionApproval(
                        step_id=sid,
                        approved_by_user=True,
                        approved_at=now_iso,
                        exact_approval_phrase=state.one_run_authorization.phrase,
                    )
                )

        req = ExecutionRequest(
            request_id=state.request_id,
            intent=intent_obj,
            profile_context=profile_obj,
            retrieved_evidence=evidence_obj,
            workflow_plan=plan_obj,
            validation_result=validation_obj,
            selected_step_ids=step_ids,
            user_approvals=exec_user_apps,
        )
        
        # persist pre-submit marker
        state.submission_attempted = True
        self.checkpoint_store.save_checkpoint(state)

        # Execute once - zero retry for execution/submission
        res = execute_with_retry(
            lambda: self.agent6_execution.execute_approved_steps(req, interactive=True),
            is_idempotent=False,
            max_retries=1,
        )
        state.execution_result = res.model_dump(mode="json")

        next_node = router.route_after_execution_assistance(state)
        state.current_node = next_node
        self.checkpoint_store.save_checkpoint(state)
        return state

    def _node_compliance_validation_post(self, state: OrchestratorState) -> OrchestratorState:
        state.current_node = "COMPLIANCE_VALIDATION_POST"
        intent_obj = IntentResult.model_validate(state.intent_result)
        profile_obj = ProfileContextResult.model_validate(state.profile_result)
        evidence_obj = RetrievedEvidenceResult.model_validate(state.evidence_result)
        plan_obj = WorkflowPlan.model_validate(state.workflow_plan)

        req = ComplianceValidationRequest(
            validation_phase=ValidationPhase.POST_EXECUTION,
            intent=intent_obj,
            profile_context=profile_obj,
            retrieved_evidence=evidence_obj,
            workflow_plan=plan_obj,
        )
        res = self.agent5_compliance.validate_workflow(req)
        state.validation_result = res.model_dump(mode="json")

        next_node = router.route_after_compliance_validation_post(state)
        state.current_node = next_node
        self.checkpoint_store.save_checkpoint(state)
        return state

    def _node_monitoring_update(self, state: OrchestratorState) -> OrchestratorState:
        state.current_node = "MONITORING_UPDATE"
        intent_obj = IntentResult.model_validate(state.intent_result)
        plan_obj = WorkflowPlan.model_validate(state.workflow_plan)
        validation_obj = ValidationResult.model_validate(state.validation_result)
        exec_obj = ExecutionResult.model_validate(state.execution_result) if state.execution_result else None

        req = MonitoringRequest(
            request_id=state.request_id,
            intent=intent_obj,
            workflow_plan=plan_obj,
            validation_result=validation_obj,
            execution_result=exec_obj,
        )
        res = self.agent7_monitoring.update_monitoring_state(req)
        state.monitoring_result = res.model_dump(mode="json")

        next_node = router.route_after_monitoring_update(state)
        state.current_node = next_node
        self.checkpoint_store.save_checkpoint(state)
        return state

    def _node_response_generation(self, state: OrchestratorState) -> OrchestratorState:
        state.current_node = "RESPONSE_GENERATION"
        intent_obj = IntentResult.model_validate(state.intent_result)
        profile_obj = ProfileContextResult.model_validate(state.profile_result)
        evidence_obj = RetrievedEvidenceResult.model_validate(state.evidence_result)
        plan_obj = WorkflowPlan.model_validate(state.workflow_plan)
        validation_obj = ValidationResult.model_validate(state.validation_result)
        exec_obj = ExecutionResult.model_validate(state.execution_result) if state.execution_result else None
        mon_obj = MonitoringResult.model_validate(state.monitoring_result) if state.monitoring_result else None

        req = ResponseGenerationRequest(
            request_id=state.request_id,
            intent=intent_obj,
            profile_context=profile_obj,
            retrieved_evidence=evidence_obj,
            workflow_plan=plan_obj,
            validation_result=validation_obj,
            execution_result=exec_obj,
            monitoring_result=mon_obj,
            response_language=state.language,
        )
        res = self.agent8_response.generate_citizen_response(req)
        state.citizen_response = res.model_dump(mode="json")

        state.current_node = "END"
        state.workflow_status = "COMPLETED"
        self.checkpoint_store.save_checkpoint(state)
        return state
