from __future__ import annotations

from datetime import datetime, timezone

from agents.orchestration.workflow_planning.schema import PlanStatus, PlanStep, StepStatus, StepType

from .adapter import ExecutionAdapter
from .authorization import authorization_contains_approval, validate_authorization
from .context_validator import validate_context
from .schema import (
    AdapterStatus,
    ExecutionEvent,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    StepExecutionResult,
    StepExecutionStatus,
)


SUPPORTED_EXECUTABLE_STEP_TYPES = {
    StepType.PREPARE_DOCUMENT,
    StepType.PREPARE_INFORMATION,
    StepType.USER_ACTION,
}


class ExecutionCoordinator:
    def __init__(self, adapter: ExecutionAdapter):
        self.adapter = adapter

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        execution_id = request.execution_options.execution_id
        base = {
            "execution_id": execution_id,
            "plan_id": request.plan_id,
            "plan_version": request.plan_version,
        }
        error = self._validate_request(request)
        if error:
            return self._blocked(base, error)

        completed_ids = set(request.resume_checkpoint.completed_step_ids if request.resume_checkpoint else [])
        completed_ids.update(
            point.step_id
            for point in request.workflow_plan.approval_points
            if request.execution_authorization
            and point.step_id in request.execution_authorization.satisfied_approval_step_ids
        )
        step_results: list[StepExecutionResult] = []
        events = [ExecutionEvent(event_type="execution_started", execution_id=execution_id)]
        steps = sorted(request.workflow_plan.steps, key=lambda step: (step.sequence, step.step_id))

        for step in steps:
            if step.step_id in completed_ids or step.step_type == StepType.HUMAN_APPROVAL:
                continue
            if step.step_type not in SUPPORTED_EXECUTABLE_STEP_TYPES:
                return self._blocked(base, f"Step '{step.step_id}' has an unsupported execution type.", step_results, events)
            if step.status not in {StepStatus.NOT_STARTED, StepStatus.READY}:
                return self._blocked(base, f"Step '{step.step_id}' is not executable in status '{step.status.value}'.", step_results, events)
            missing_dependency = self._missing_dependency(step, completed_ids, step_results)
            if missing_dependency:
                return self._blocked(base, missing_dependency, step_results, events)
            authorization_error = validate_authorization(request, step.step_id)
            if authorization_error:
                return self._blocked(base, authorization_error, step_results, events)
            if step.step_id not in request.compliance_decision.authorized_step_ids:
                return self._blocked(base, f"Compliance does not authorize step '{step.step_id}'.", step_results, events)
            context_error = validate_context(
                request.confirmed_context,
                step.required_fact_keys,
                step.required_document_refs,
            )
            if context_error:
                return self._blocked(base, context_error, step_results, events)

            started_at = datetime.now(timezone.utc)
            adapter_result = self.adapter.execute_step(step, request.confirmed_context)
            completed_at = datetime.now(timezone.utc)
            step_result = StepExecutionResult(
                step_id=step.step_id,
                status=self._step_status(adapter_result.status),
                action_attempted=step.title,
                outcome=adapter_result.outcome,
                error_category=adapter_result.error_category,
                retryable=adapter_result.retryable,
                portal_reference=adapter_result.portal_reference,
                human_intervention=adapter_result.human_intervention,
                started_at=started_at,
                completed_at=completed_at,
            )
            step_results.append(step_result)
            if adapter_result.status == AdapterStatus.HUMAN_INTERVENTION_REQUIRED:
                if adapter_result.human_intervention is None:
                    return self._blocked(
                        base,
                        f"Adapter requested human intervention for step '{step.step_id}' without a checkpoint.",
                        step_results,
                        events,
                    )
                if not adapter_result.human_intervention.resumable:
                    return self._blocked(
                        base,
                        f"Human intervention for step '{step.step_id}' is not resumable.",
                        step_results,
                        events,
                    )
                events.append(ExecutionEvent(event_type="human_intervention_required", execution_id=execution_id, step_id=step.step_id))
                return ExecutionResult(
                    **base,
                    status=ExecutionStatus.HUMAN_INTERVENTION_REQUIRED,
                    step_results=step_results,
                    events=events,
                    human_intervention=adapter_result.human_intervention,
                )
            if adapter_result.status == AdapterStatus.FAILED:
                events.append(ExecutionEvent(event_type="execution_failed", execution_id=execution_id, step_id=step.step_id))
                status = ExecutionStatus.PARTIAL if step_results[:-1] else ExecutionStatus.FAILED
                return ExecutionResult(
                    **base,
                    status=status,
                    step_results=step_results,
                    events=events,
                    failure_reason=adapter_result.outcome,
                )
            completed_ids.add(step.step_id)
            events.append(ExecutionEvent(event_type="step_completed", execution_id=execution_id, step_id=step.step_id))

            if adapter_result.status == AdapterStatus.SUBMITTED_PENDING:
                events.append(ExecutionEvent(event_type="execution_submitted_pending", execution_id=execution_id, step_id=step.step_id))
                return ExecutionResult(**base, status=ExecutionStatus.SUBMITTED_PENDING, step_results=step_results, events=events)

        events.append(ExecutionEvent(event_type="execution_completed", execution_id=execution_id))
        return ExecutionResult(**base, status=ExecutionStatus.COMPLETED, step_results=step_results, events=events)

    def _validate_request(self, request: ExecutionRequest) -> str | None:
        plan = request.workflow_plan
        if request.plan_id != plan.request_id:
            return "Execution request plan_id does not match the workflow plan request_id."
        if request.plan_version != plan.plan_version:
            return "Execution request plan_version does not match the workflow plan."
        if plan.plan_status != PlanStatus.READY:
            return f"Workflow plan is not executable in status '{plan.plan_status.value}'."
        if not request.compliance_decision.allowed:
            return f"Compliance blocked execution: {request.compliance_decision.reason}"
        if request.confirmed_context.session_id != plan.session_id:
            return "Confirmed execution context does not match the workflow session."
        authorization_error = validate_authorization(request)
        if authorization_error:
            return authorization_error
        authorization = request.execution_authorization
        assert authorization is not None
        approval_ids = {
            step.step_id
            for step in plan.steps
            if step.step_type == StepType.HUMAN_APPROVAL or step.requires_explicit_approval
        }
        if not authorization_contains_approval(authorization, approval_ids):
            return "Required human approval steps have not been satisfied."
        plan_step_ids = {step.step_id for step in plan.steps}
        unknown_authorized_steps = set(authorization.approved_step_ids) - plan_step_ids
        if unknown_authorized_steps:
            return f"Authorization references steps absent from the workflow plan: {sorted(unknown_authorized_steps)}."
        checkpoint = request.resume_checkpoint
        if checkpoint is not None:
            if not checkpoint.human_action_completed:
                return "Human intervention has not been completed for the resume checkpoint."
            unknown_completed_steps = set(checkpoint.completed_step_ids) - plan_step_ids
            if unknown_completed_steps:
                return f"Resume checkpoint references steps absent from the workflow plan: {sorted(unknown_completed_steps)}."
            unauthorized_completed_steps = set(checkpoint.completed_step_ids) - set(authorization.approved_step_ids)
            if unauthorized_completed_steps:
                return f"Resume checkpoint references unauthorized steps: {sorted(unauthorized_completed_steps)}."
        return None

    @staticmethod
    def _missing_dependency(step: PlanStep, completed_ids: set[str], results: list[StepExecutionResult]) -> str | None:
        failed_ids = {result.step_id for result in results if result.status in {StepExecutionStatus.FAILED, StepExecutionStatus.BLOCKED}}
        for dependency in step.depends_on:
            if dependency in failed_ids:
                return f"Step '{step.step_id}' depends on failed step '{dependency}'."
            if dependency not in completed_ids:
                return f"Step '{step.step_id}' has unsatisfied dependency '{dependency}'."
        return None

    @staticmethod
    def _step_status(status: AdapterStatus) -> StepExecutionStatus:
        return {
            AdapterStatus.COMPLETED: StepExecutionStatus.COMPLETED,
            AdapterStatus.SUBMITTED_PENDING: StepExecutionStatus.SUBMITTED_PENDING,
            AdapterStatus.FAILED: StepExecutionStatus.FAILED,
            AdapterStatus.HUMAN_INTERVENTION_REQUIRED: StepExecutionStatus.HUMAN_INTERVENTION_REQUIRED,
        }[status]

    @staticmethod
    def _blocked(base: dict, reason: str, step_results: list[StepExecutionResult] | None = None, events: list[ExecutionEvent] | None = None) -> ExecutionResult:
        execution_id = base["execution_id"]
        blocked_events = list(events or [])
        blocked_events.append(ExecutionEvent(event_type="execution_blocked", execution_id=execution_id))
        return ExecutionResult(
            **base,
            status=ExecutionStatus.BLOCKED,
            step_results=list(step_results or []),
            events=blocked_events,
            failure_reason=reason,
        )


ExecutionAgent = ExecutionCoordinator