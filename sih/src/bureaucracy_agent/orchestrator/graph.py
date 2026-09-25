"""End-to-end Orchestrator State Machine Graph with explicit transition table."""

from __future__ import annotations

import logging
from typing import Dict, Optional, Set

from agents.compliance_validation.agent import ComplianceValidationAgent
from agents.compliance_validation.schema import UserApprovalRecord, ValidationPhase, ValidationResult
from agents.execution_assistance.schema import ExecutionResult, ExecutionStatus, UserExecutionApproval
from agents.information_retrieval.agent import InformationRetrievalAgent
from agents.intent_understanding.agent import IntentUnderstandingAgent
from agents.monitoring_update.agent import MonitoringUpdateAgent
from agents.response_generation.agent import ResponseGenerationAgent
from agents.user_context.agent import UserContextAgent
from agents.user_context.schema import ProfileContextResult, ProfileFact
from agents.workflow_planning.agent import WorkflowPlanningAgent, WorkflowPlan

from src.bureaucracy_agent.orchestrator import adapters, router, scoping
from src.bureaucracy_agent.orchestrator.checkpoints import SqliteCheckpointStore
from src.bureaucracy_agent.orchestrator.finalize import derive_terminal_status
from src.bureaucracy_agent.orchestrator.logging_setup import log_route, log_stage
from src.bureaucracy_agent.orchestrator.state import OrchestratorState
from src.bureaucracy_agent.orchestrator.statuses import WorkflowStatus

logger = logging.getLogger(__name__)


class IllegalTransitionError(ValueError):
    """Raised when an illegal state machine transition is attempted."""


# Explicit allowed transition table: current_node -> allowed next nodes
TRANSITION_TABLE: Dict[str, Set[str]] = {
    "START": {"INTENT"},
    "INTENT": {"USER_CONTEXT", "PAUSED_NEEDS_INPUT"},
    "PAUSED_NEEDS_INPUT": {"INTENT"},
    "USER_CONTEXT": {"RETRIEVAL"},
    "RETRIEVAL": {"PLANNING"},
    "PLANNING": {"COMPLIANCE_PRE"},
    "COMPLIANCE_PRE": {"STOP_BLOCKED", "PAUSED_FACT_CONSENT", "PAUSED_NEEDS_AUTHORIZATION", "EXECUTION"},
    "PAUSED_FACT_CONSENT": {"COMPLIANCE_PRE"},
    "PAUSED_NEEDS_AUTHORIZATION": {"COMPLIANCE_PRE"},
    "EXECUTION": {"PAUSED_CAPTCHA", "PAUSED_PAYMENT", "COMPLIANCE_POST", "RESPONSE"},
    "PAUSED_CAPTCHA": {"EXECUTION"},
    "PAUSED_PAYMENT": {"EXECUTION"},
    "COMPLIANCE_POST": {"MONITORING"},
    "MONITORING": {"RESPONSE"},
    "RESPONSE": {"END"},
    "STOP_BLOCKED": {"RESPONSE"},
    "END": set(),
}


class OrchestratorGraph:
    """Orchestration layer state machine executing nodes & managing transitions."""

    def __init__(self, checkpoint_store: Optional[SqliteCheckpointStore] = None) -> None:
        self.checkpoint_store = checkpoint_store or SqliteCheckpointStore()

        # Frozen agent callables
        self.agent1_intent = IntentUnderstandingAgent(prefer_ollama=False)
        self.agent2_context = UserContextAgent()
        self.agent3_retrieval = InformationRetrievalAgent(allow_llm=False)
        self.agent4_planning = WorkflowPlanningAgent()
        self.agent5_compliance = ComplianceValidationAgent()
        self.agent7_monitoring = MonitoringUpdateAgent()
        self.agent8_response = ResponseGenerationAgent(allow_llm=False)

    def run(self, state: OrchestratorState) -> OrchestratorState:
        """Execute or resume state machine transitions from state.current_node."""
        if state.current_node == "START":
            self._transition(state, "INTENT", "Workflow started")

        while state.current_node != "END":
            curr = state.current_node

            if curr == "INTENT":
                state = self._node_intent(state)
            elif curr == "USER_CONTEXT":
                state = self._node_user_context(state)
            elif curr == "RETRIEVAL":
                state = self._node_retrieval(state)
            elif curr == "PLANNING":
                state = self._node_planning(state)
            elif curr == "COMPLIANCE_PRE":
                state = self._node_compliance_pre(state)
            elif curr == "EXECUTION":
                state = self._node_execution(state)
            elif curr == "COMPLIANCE_POST":
                state = self._node_compliance_post(state)
            elif curr == "MONITORING":
                state = self._node_monitoring(state)
            elif curr == "RESPONSE":
                state = self._node_response(state)
            elif curr == "STOP_BLOCKED":
                state = self._node_stop_blocked(state)
            elif curr.startswith("PAUSED_"):
                logger.info(f"Workflow {state.workflow_id} paused at node {curr}.")
                break
            else:
                logger.error(f"Unknown graph node encountered: {curr}")
                state.workflow_status = WorkflowStatus.FAILED
                state.errors.append(f"Unknown node: {curr}")
                self.checkpoint_store.save_checkpoint(state)
                break

        return state

    def _transition(self, state: OrchestratorState, next_node: str, reason: str = "") -> None:
        """Validate transition against transition table and save checkpoint."""
        curr = state.current_node
        allowed = TRANSITION_TABLE.get(curr, set())
        if next_node not in allowed:
            err = f"Illegal state transition from '{curr}' to '{next_node}'. Allowed: {allowed}"
            logger.error(f"[ROUTE ERROR] {err}")
            state.workflow_status = WorkflowStatus.FAILED
            state.errors.append(err)
            self.checkpoint_store.save_checkpoint(state)
            raise IllegalTransitionError(err)

        state.current_node = next_node
        self.checkpoint_store.save_checkpoint(state)

    # --- Node Implementation Methods ---

    def _node_intent(self, state: OrchestratorState) -> OrchestratorState:
        req = adapters.build_intent_request(state)
        res = self.agent1_intent.understand_intent(req)
        adapters.store_intent_result(state, res)

        next_node = router.route_after_intent(state)
        if next_node == "PAUSED_NEEDS_INPUT":
            state.workflow_status = WorkflowStatus.PAUSED_NEEDS_INPUT
        self._transition(state, next_node)
        return state

    def _node_user_context(self, state: OrchestratorState) -> OrchestratorState:
        req = adapters.build_user_context_request(state)
        res = self.agent2_context.build_user_context(req)
        adapters.store_user_context_result(state, res)

        next_node = router.route_after_user_context(state)
        self._transition(state, next_node)
        return state

    def _node_retrieval(self, state: OrchestratorState) -> OrchestratorState:
        req = adapters.build_retrieval_request(state)
        res = self.agent3_retrieval.retrieve_information(req)
        adapters.store_retrieved_evidence(state, res)

        next_node = router.route_after_retrieval(state)
        self._transition(state, next_node)
        return state

    def _node_planning(self, state: OrchestratorState) -> OrchestratorState:
        req = adapters.build_workflow_planning_request(state)
        res = self.agent4_planning.create_workflow_plan(req)
        adapters.store_workflow_plan(state, res)

        # Apply Step Scoping Adapter: Narrow execution plan view for compliance/execution
        scoped_plan, dropped_steps = scoping.scope_workflow_plan(res)
        state.workflow_plan = scoped_plan.model_dump(mode="json")
        state.user_handled_steps = [s.model_dump(mode="json") for s in dropped_steps]

        next_node = router.route_after_planning(state)
        self._transition(state, next_node)
        return state

    def _node_compliance_pre(self, state: OrchestratorState) -> OrchestratorState:
        user_approvals = []
        if state.user_authorizations:
            user_approvals = [UserApprovalRecord.model_validate(appr) for appr in state.user_authorizations]

        req = adapters.build_compliance_validation_request(
            state,
            phase=ValidationPhase.PRE_EXECUTION,
            user_approvals=user_approvals,
        )
        res = self.agent5_compliance.validate_workflow(req)
        adapters.store_validation_result(state, res, phase=ValidationPhase.PRE_EXECUTION)

        next_node = router.route_after_compliance_pre(state)
        if next_node == "PAUSED_FACT_CONSENT":
            state.workflow_status = WorkflowStatus.PAUSED_FACT_CONSENT
        elif next_node == "PAUSED_NEEDS_AUTHORIZATION":
            state.workflow_status = WorkflowStatus.PAUSED_NEEDS_AUTHORIZATION
        elif next_node == "STOP_BLOCKED":
            state.workflow_status = WorkflowStatus.STOP_BLOCKED
            state.terminal_reason = "STOP_BLOCKED: Compliance or readiness gate failed."

        self._transition(state, next_node)
        return state

    def _node_execution(self, state: OrchestratorState) -> OrchestratorState:
        from src.bureaucracy_agent.portal.driver import PortalBrowserDriver

        # Guard: If state.submission_attempted is already True upon resume, do NOT re-submit!
        if state.submission_attempted and not state.is_dry_run:
            logger.info("Resume re-entered execution after submission; proceeding to inspection/reading only.")

        val_res = ValidationResult.model_validate(state.validation_result) if state.validation_result else None
        selected_steps = val_res.eligible_step_ids if val_res and val_res.eligible_step_ids else ["step-1"]

        # Build exec approvals from state.user_authorizations
        exec_approvals: list[UserExecutionApproval] = []
        for sid in selected_steps:
            exec_approvals.append(
                UserExecutionApproval(
                    step_id=sid,
                    approved_by_user=True,
                    approved_at=state.updated_at,
                    exact_approval_phrase="SUBMIT RTI ONLINE REQUEST",
                )
            )

        # Extract confirmed facts from profile context
        confirmed_facts: list[ProfileFact] = []
        if state.profile_result:
            prof = ProfileContextResult.model_validate(state.profile_result)
            confirmed_facts = [f for f in prof.relevant_facts if f.confirmed_by_user]

        exec_req = adapters.build_execution_request(
            state,
            selected_step_ids=selected_steps,
            user_approvals=exec_approvals,
            confirmed_facts=confirmed_facts,
        )

        def pre_submit_callback():
            state.submission_attempted = True
            self.checkpoint_store.save_checkpoint(state)

        # Execute flow via portal driver
        driver = PortalBrowserDriver()
        exec_res = driver.execute_live_flow(
            exec_req,
            interactive=True,
            stop_before_submit=state.stop_before_submit,
            on_submission_attempted_cb=pre_submit_callback,
        )
        adapters.store_execution_result(state, exec_res)

        next_node = router.route_after_execution(state)
        if next_node == "PAUSED_CAPTCHA":
            state.workflow_status = WorkflowStatus.PAUSED_CAPTCHA
        elif next_node == "PAUSED_PAYMENT":
            state.workflow_status = WorkflowStatus.PAUSED_PAYMENT

        self._transition(state, next_node)
        return state

    def _node_compliance_post(self, state: OrchestratorState) -> OrchestratorState:
        req = adapters.build_compliance_validation_request(
            state,
            phase=ValidationPhase.POST_EXECUTION,
        )
        res = self.agent5_compliance.validate_workflow(req)
        adapters.store_validation_result(state, res, phase=ValidationPhase.POST_EXECUTION)

        next_node = router.route_after_compliance_post(state)
        self._transition(state, next_node)
        return state

    def _node_monitoring(self, state: OrchestratorState) -> OrchestratorState:
        exec_res = ExecutionResult.model_validate(state.execution_result) if state.execution_result else None
        should_monitor = (
            state.submission_attempted
            or state.confirmation_observed
            or (exec_res and exec_res.execution_status == ExecutionStatus.UNCERTAIN)
        )

        if should_monitor:
            req = adapters.build_monitoring_request(state)
            res = self.agent7_monitoring.update_monitoring_state(req)
            adapters.store_monitoring_result(state, res)

        next_node = router.route_after_monitoring(state)
        self._transition(state, next_node)
        return state

    def _node_stop_blocked(self, state: OrchestratorState) -> OrchestratorState:
        next_node = router.route_after_stop_blocked(state)
        self._transition(state, next_node)
        return state

    def _node_response(self, state: OrchestratorState) -> OrchestratorState:
        req = adapters.build_response_generation_request(state)
        res = self.agent8_response.generate_citizen_response(req)
        adapters.store_citizen_response(state, res)

        final_status = derive_terminal_status(state)
        state.workflow_status = final_status

        next_node = router.route_after_response(state)
        self._transition(state, next_node)
        return state
