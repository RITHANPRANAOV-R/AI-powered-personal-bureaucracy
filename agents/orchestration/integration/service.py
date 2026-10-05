from __future__ import annotations

from typing import Protocol

from agents.orchestration.workflow_planning.schema import PlanStatus, WorkflowPlan
from agents.utility_based.execution_assistance import (
    ComplianceDecision,
    ExecutionCoordinator,
    ExecutionRequest,
    ExecutionStatus,
)

from .schema import ApprovalState, IntegrationRequest, IntegrationResult, IntegrationStatus


class ComplianceValidator(Protocol):
    def validate(self, workflow_plan: WorkflowPlan) -> ComplianceDecision | None:
        """Return the policy decision for a plan, or None when unavailable."""


class ExecutionIntegrationService:
    def __init__(self, executor: ExecutionCoordinator, compliance_validator: ComplianceValidator | None = None):
        self.executor = executor
        self.compliance_validator = compliance_validator

    def run(self, request: IntegrationRequest) -> IntegrationResult:
        plan = request.workflow_plan
        approval_state = self._approval_state(request)
        base = {
            "plan_id": request.plan_id,
            "plan_version": request.plan_version,
            "approval_state": approval_state,
        }
        if plan is None:
            return IntegrationResult(
                **base,
                status=IntegrationStatus.BLOCKED_BY_PLAN,
                blocking_reason="Workflow plan is required.",
            )
        if request.plan_id != plan.request_id:
            return IntegrationResult(
                **base,
                status=IntegrationStatus.BLOCKED_BY_PLAN,
                blocking_reason="Integration request plan_id does not match the workflow plan.",
                warnings=list(plan.warnings),
            )
        if request.plan_version != plan.plan_version:
            return IntegrationResult(
                **base,
                status=IntegrationStatus.BLOCKED_BY_PLAN,
                blocking_reason="Integration request plan_version does not match the workflow plan.",
                warnings=list(plan.warnings),
            )
        if plan.plan_status == PlanStatus.NEEDS_USER_INPUT:
            return IntegrationResult(
                **base,
                status=IntegrationStatus.BLOCKED_BY_MISSING_INFORMATION,
                blocking_reason="Workflow plan requires user information before execution.",
                warnings=list(plan.warnings),
            )
        if plan.plan_status not in {PlanStatus.READY, PlanStatus.PARTIAL}:
            return IntegrationResult(
                **base,
                status=IntegrationStatus.BLOCKED_BY_PLAN,
                blocking_reason=f"Workflow plan is not executable in status '{plan.plan_status.value}'.",
                warnings=list(plan.warnings),
            )

        compliance_decision, compliance_error = self._validate_compliance(plan, request.confirmed_context)
        if compliance_error:
            return IntegrationResult(
                **base,
                status=IntegrationStatus.BLOCKED_BY_COMPLIANCE,
                compliance_decision=compliance_decision,
                blocking_reason=compliance_error,
                warnings=list(plan.warnings),
            )

        execution_request = ExecutionRequest(
            workflow_plan=plan,
            plan_id=request.plan_id,
            plan_version=request.plan_version,
            execution_authorization=request.execution_authorization,
            compliance_decision=compliance_decision,
            confirmed_context=request.confirmed_context,
            resume_checkpoint=request.resume_checkpoint,
            execution_options=request.execution_options,
        )
        execution_result = self.executor.execute(execution_request)
        return IntegrationResult(
            **base,
            status=self._integration_status(execution_result.status, execution_result.failure_reason),
            compliance_decision=compliance_decision,
            execution_result=execution_result,
            blocking_reason=execution_result.failure_reason if execution_result.status == ExecutionStatus.BLOCKED else None,
            warnings=list(plan.warnings),
        )

    def _validate_compliance(
        self,
        plan: WorkflowPlan,
        confirmed_context: Optional[ConfirmedExecutionContext] = None,
    ) -> tuple[ComplianceDecision | None, str | None]:
        if self.compliance_validator is None:
            return None, "Compliance decision is unavailable."
        try:
            import inspect

            sig = inspect.signature(self.compliance_validator.validate)
            if len(sig.parameters) >= 2:
                decision = self.compliance_validator.validate(plan, confirmed_context)
            else:
                decision = self.compliance_validator.validate(plan)
        except Exception as error:
            return None, f"Compliance validation failed: {error}"
        if decision is None:
            return None, "Compliance decision is unavailable."
        if not decision.allowed:
            return decision, f"Compliance blocked execution: {decision.reason}"
        return decision, None

    @staticmethod
    def _approval_state(request: IntegrationRequest) -> ApprovalState:
        plan = request.workflow_plan
        if plan is None:
            return ApprovalState()
        required = [
            step.step_id
            for step in plan.steps
            if step.requires_explicit_approval or step.step_type.value == "human_approval"
        ]
        satisfied = set(request.execution_authorization.satisfied_approval_step_ids) if request.execution_authorization else set()
        return ApprovalState(
            required_step_ids=required,
            satisfied_step_ids=sorted(satisfied.intersection(required)),
            missing_step_ids=sorted(set(required) - satisfied),
        )

    @staticmethod
    def _integration_status(status: ExecutionStatus, failure_reason: str | None) -> IntegrationStatus:
        if status == ExecutionStatus.COMPLETED:
            return IntegrationStatus.EXECUTION_COMPLETED
        if status == ExecutionStatus.SUBMITTED_PENDING:
            return IntegrationStatus.EXECUTION_PENDING
        if status == ExecutionStatus.PARTIAL:
            return IntegrationStatus.EXECUTION_PARTIAL
        if status == ExecutionStatus.FAILED:
            return IntegrationStatus.EXECUTION_FAILED
        if status == ExecutionStatus.HUMAN_INTERVENTION_REQUIRED:
            return IntegrationStatus.HUMAN_INTERVENTION_REQUIRED
        if failure_reason and ("approval" in failure_reason.lower() or "authorization" in failure_reason.lower()):
            return IntegrationStatus.BLOCKED_BY_AUTHORIZATION
        if failure_reason and any(value in failure_reason.lower() for value in ("fact", "document", "information")):
            return IntegrationStatus.BLOCKED_BY_MISSING_INFORMATION
        return IntegrationStatus.EXECUTION_BLOCKED
