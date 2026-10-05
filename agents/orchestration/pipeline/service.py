from __future__ import annotations

from typing import Callable, Protocol

from agents.knowledge_based.information_retrieval.agent import InformationRetrievalAgent
from agents.knowledge_based.information_retrieval.schemas import RetrievalRequest, RetrievalStatus
from agents.orchestration.integration import ExecutionIntegrationService
from agents.orchestration.integration.schema import IntegrationStatus
from agents.orchestration.intent_understanding import IntentUnderstandingService
from agents.orchestration.intent_understanding.schemas import IntentClassificationResult, UserRequestInput
from agents.orchestration.monitoring import MonitoringService
from agents.orchestration.workflow_planning import (
    PlanStatus,
    WorkflowPlan,
    WorkflowPlanningRequest,
    create_workflow_plan,
)
from agents.response_generation.schema import ExecutionResult as ResponseExecutionResult
from agents.utility_based.execution_assistance.schema import ExecutionStatus

from .schema import OrchestrationRequest, OrchestrationResult, OrchestrationStatus


class ResponseGenerator(Protocol):
    def generate(self, result: ResponseExecutionResult) -> object:
        """Generate the repository's structured citizen response."""


class TopLevelOrchestrator:
    def __init__(
        self,
        intent_service: IntentUnderstandingService,
        retrieval_agent: InformationRetrievalAgent,
        workflow_planner: Callable[[WorkflowPlanningRequest], WorkflowPlan] = create_workflow_plan,
        execution_integration: ExecutionIntegrationService | None = None,
        monitoring_service: MonitoringService | None = None,
        response_generator: ResponseGenerator | None = None,
    ):
        self.intent_service = intent_service
        self.retrieval_agent = retrieval_agent
        self.workflow_planner = workflow_planner
        self.execution_integration = execution_integration
        self.monitoring_service = monitoring_service or MonitoringService()
        self.response_generator = response_generator

    def run(self, request: OrchestrationRequest) -> OrchestrationResult:
        request_id = request.user_request.session_id
        result = OrchestrationResult(request_id=request_id, status=OrchestrationStatus.FAILED)

        try:
            intent_result = self.intent_service.process(request.user_request)
        except Exception as error:
            return self._finish(result, OrchestrationStatus.FAILED, f"Intent understanding failed: {error}")
        result.intent_result = intent_result

        try:
            monitoring_result = self.monitoring_service.process(
                request.previous_session_state,
                intent_result,
            )
            result.session_state = monitoring_result.updated_state
            result.session_changes = list(monitoring_result.changes)
        except Exception as error:
            return self._finish(result, OrchestrationStatus.FAILED, f"Session state update failed: {error}")

        if intent_result.missing_information:
            return self._finish(
                result,
                OrchestrationStatus.NEEDS_CLARIFICATION,
                "Required user information is missing.",
            )

        retrieval_request = self._build_retrieval_request(request.user_request, intent_result, request.user_documents)
        try:
            retrieval_result = self.retrieval_agent.retrieve(
                retrieval_request,
                user_documents=request.user_documents,
            )
        except Exception as error:
            return self._finish(result, OrchestrationStatus.RETRIEVAL_BLOCKED, f"Information retrieval failed: {error}")
        result.retrieval_result = retrieval_result

        if retrieval_result.retrieval_status in {
            RetrievalStatus.FAILED,
            RetrievalStatus.SOURCE_UNAVAILABLE,
            RetrievalStatus.NO_EVIDENCE_FOUND,
        }:
            return self._finish(
                result,
                OrchestrationStatus.RETRIEVAL_BLOCKED,
                "Required retrieval evidence is unavailable.",
            )

        planning_request = WorkflowPlanningRequest(
            intent=intent_result,
            session_state=result.session_state,
            retrieved_evidence=retrieval_result,
            user_constraints=request.user_constraints,
        )
        try:
            workflow_plan = self.workflow_planner(planning_request)
        except Exception as error:
            return self._finish(result, OrchestrationStatus.PLANNING_FAILED, f"Workflow planning failed: {error}")
        result.workflow_plan = workflow_plan

        if workflow_plan.plan_status == PlanStatus.NEEDS_USER_INPUT:
            return self._finish(
                result,
                OrchestrationStatus.NEEDS_CLARIFICATION,
                "Workflow planning requires additional user information.",
            )
        if workflow_plan.plan_status not in {PlanStatus.READY, PlanStatus.PARTIAL}:
            return self._finish(
                result,
                OrchestrationStatus.PLANNING_FAILED,
                f"Workflow plan is not executable in status '{workflow_plan.plan_status.value}'.",
            )
        if self.execution_integration is None:
            return self._finish(result, OrchestrationStatus.FAILED, "Execution integration is unavailable.")
        if request.confirmed_context is None:
            return self._finish(
                result,
                OrchestrationStatus.NEEDS_CLARIFICATION,
                "Confirmed execution context is required before execution.",
            )

        from agents.orchestration.integration.schema import IntegrationRequest

        integration_request = IntegrationRequest(
            workflow_plan=workflow_plan,
            plan_id=workflow_plan.request_id,
            plan_version=workflow_plan.plan_version,
            execution_authorization=request.execution_authorization,
            confirmed_context=request.confirmed_context,
            resume_checkpoint=request.resume_checkpoint,
        )
        try:
            integration_result = self.execution_integration.run(integration_request)
        except Exception as error:
            return self._finish(result, OrchestrationStatus.FAILED, f"Execution integration failed: {error}")
        result.integration_result = integration_result
        if integration_result.execution_result is not None:
            result.execution_events = list(integration_result.execution_result.events)
        return self._finish(
            result,
            self._orchestration_status(integration_result.status),
            integration_result.blocking_reason,
        )

    @staticmethod
    def _build_retrieval_request(
        user_request: UserRequestInput,
        intent_result: IntentClassificationResult,
        user_documents,
    ) -> RetrievalRequest:
        entities = {
            entity.entity_type: entity.normalized_value
            for entity in intent_result.entities
        }
        service = intent_result.update_type or user_request.domain.title()
        return RetrievalRequest(
            request_id=user_request.session_id,
            goal=intent_result.summary,
            service=service,
            domain=user_request.domain,
            entities=entities,
            user_documents=list(user_documents) if user_documents is not None else [],
        )

    def _finish(
        self,
        result: OrchestrationResult,
        status: OrchestrationStatus,
        reason: str | None = None,
    ) -> OrchestrationResult:
        result.status = status
        result.blocking_reason = reason
        response_input = self._response_input(result)
        if self.response_generator is not None:
            try:
                result.response_result = self.response_generator.generate(response_input)
            except Exception as error:
                result.errors.append(f"Response generation failed: {error}")
        return result

    @staticmethod
    def _orchestration_status(status: IntegrationStatus) -> OrchestrationStatus:
        return {
            IntegrationStatus.BLOCKED_BY_COMPLIANCE: OrchestrationStatus.COMPLIANCE_BLOCKED,
            IntegrationStatus.BLOCKED_BY_MISSING_INFORMATION: OrchestrationStatus.NEEDS_CLARIFICATION,
            IntegrationStatus.BLOCKED_BY_AUTHORIZATION: OrchestrationStatus.AUTHORIZATION_BLOCKED,
            IntegrationStatus.HUMAN_INTERVENTION_REQUIRED: OrchestrationStatus.AWAITING_HUMAN_ACTION,
            IntegrationStatus.EXECUTION_COMPLETED: OrchestrationStatus.EXECUTION_COMPLETED,
            IntegrationStatus.EXECUTION_PENDING: OrchestrationStatus.EXECUTION_PENDING,
            IntegrationStatus.EXECUTION_PARTIAL: OrchestrationStatus.EXECUTION_PARTIAL,
            IntegrationStatus.EXECUTION_FAILED: OrchestrationStatus.EXECUTION_FAILED,
            IntegrationStatus.BLOCKED_BY_PLAN: OrchestrationStatus.PLANNING_FAILED,
            IntegrationStatus.EXECUTION_BLOCKED: OrchestrationStatus.FAILED,
        }[status]

    @staticmethod
    def _response_input(result: OrchestrationResult) -> ResponseExecutionResult:
        plan = result.workflow_plan
        integration = result.integration_result
        execution = integration.execution_result if integration is not None else None
        completed_steps = []
        if execution is not None:
            completed_steps = [
                step.action_attempted
                for step in execution.step_results
                if step.status.value in {"completed", "submitted_pending"}
            ]
        completed_ids = {
            step.step_id for step in execution.step_results
        } if execution is not None else set()
        pending_steps = [
            step.title for step in plan.steps
            if step.step_id not in completed_ids
        ] if plan is not None else []
        missing_information = []
        if result.intent_result is not None:
            missing_information.extend(item.reason for item in result.intent_result.missing_information)
        if plan is not None:
            missing_information.extend(item.question for item in plan.missing_information)
        action_required = result.blocking_reason
        if execution is not None and execution.human_intervention is not None:
            action_required = execution.human_intervention.required_user_action
        status_map = {
            OrchestrationStatus.EXECUTION_COMPLETED: "COMPLETED",
            OrchestrationStatus.EXECUTION_PENDING: "IN_PROGRESS",
            OrchestrationStatus.COMPLETED: "IN_PROGRESS",
            OrchestrationStatus.EXECUTION_PARTIAL: "IN_PROGRESS",
            OrchestrationStatus.AWAITING_HUMAN_ACTION: "ACTION_REQUIRED",
            OrchestrationStatus.NEEDS_CLARIFICATION: "ACTION_REQUIRED",
            OrchestrationStatus.COMPLIANCE_BLOCKED: "BLOCKED",
            OrchestrationStatus.AUTHORIZATION_BLOCKED: "BLOCKED",
            OrchestrationStatus.RETRIEVAL_BLOCKED: "BLOCKED",
            OrchestrationStatus.PLANNING_FAILED: "BLOCKED",
            OrchestrationStatus.EXECUTION_FAILED: "FAILED",
            OrchestrationStatus.FAILED: "FAILED",
        }
        return ResponseExecutionResult(
            service_name=plan.service if plan is not None else "Aadhaar",
            document_type=plan.domain if plan is not None else "aadhaar",
            overall_status=status_map[result.status],
            completed_steps=completed_steps,
            pending_steps=pending_steps,
            action_required=action_required,
            missing_information=missing_information,
        )
