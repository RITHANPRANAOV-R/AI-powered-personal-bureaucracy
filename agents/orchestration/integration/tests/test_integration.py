from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from agents.knowledge_based.compliance_validation.agent import ComplianceValidationAgent
from agents.knowledge_based.compliance_validation.schema import ComplianceValidationInput
from agents.orchestration.integration import (
    ComplianceAgentAdapter,
    ExecutionIntegrationService,
    IntegrationRequest,
    IntegrationStatus,
)
from agents.orchestration.workflow_planning.schema import (
    ApprovalPoint,
    PlanStatus,
    PlanStep,
    StepType,
    WorkflowPlan,
)
from agents.utility_based.execution_assistance import (
    AdapterResult,
    ComplianceDecision,
    ConfirmedExecutionContext,
    ConfirmedFact,
    ExecutionAuthorization,
    ExecutionOptions,
    FactStatus,
    HumanIntervention,
    MockExecutionAdapter,
)


class StaticComplianceValidator:
    def __init__(self, decision):
        self.decision = decision
        self.calls = 0

    def validate(self, workflow_plan):
        self.calls += 1
        return self.decision


def make_request(*, outcomes=None, authorization=True, approval_satisfied=True, **changes):
    approval = PlanStep(
        step_id="approval",
        sequence=1,
        title="Approve action",
        description="Review the proposed action.",
        step_type=StepType.HUMAN_APPROVAL,
        requires_user_action=True,
        requires_explicit_approval=True,
    )
    action = PlanStep(
        step_id="action",
        sequence=2,
        title="Prepare Aadhaar information",
        description="Prepare the confirmed information.",
        step_type=StepType.PREPARE_INFORMATION,
        depends_on=["approval"],
        required_fact_keys=["new_address"],
    )
    plan = WorkflowPlan(
        planning_request_id="planning-1",
        request_id="plan-1",
        session_id="session-1",
        service="Aadhaar",
        task="update",
        target="address",
        plan_status=PlanStatus.READY,
        steps=[approval, action],
        approval_points=[ApprovalPoint(
            approval_id="approval-1",
            step_id="approval",
            reason="Review",
            confirmation="Confirmed",
        )],
    )
    now = datetime.now(timezone.utc)
    execution_authorization = None
    if authorization:
        execution_authorization = ExecutionAuthorization(
            authorization_id="auth-1",
            user_id="user-1",
            session_id="session-1",
            plan_id="plan-1",
            plan_version=1,
            approved_step_ids=["action"],
            satisfied_approval_step_ids=["approval"] if approval_satisfied else [],
            approved_at=now,
            expires_at=now + timedelta(hours=1),
        )
    request = IntegrationRequest(
        workflow_plan=plan,
        plan_id="plan-1",
        plan_version=1,
        execution_authorization=execution_authorization,
        confirmed_context=ConfirmedExecutionContext(
            session_id="session-1",
            facts={
                "new_address": ConfirmedFact(
                    value="Confirmed address",
                    provenance="user-confirmation",
                    status=FactStatus.CONFIRMED,
                    allowed_for_execution=True,
                )
            },
        ),
        execution_options=ExecutionOptions(execution_id="integration-1"),
    )
    return request.model_copy(update=changes), MockExecutionAdapter(outcomes)


def run(request, adapter, decision=None):
    validator = StaticComplianceValidator(decision)
    result = ExecutionIntegrationService(
        executor=__import__(
            "agents.utility_based.execution_assistance.executor",
            fromlist=["ExecutionCoordinator"],
        ).ExecutionCoordinator(adapter),
        compliance_validator=validator,
    ).run(request)
    return result, validator


def allowed_decision(step_ids=None):
    return ComplianceDecision(
        allowed=True,
        policy_version="policy-1",
        reason="Allowed",
        authorized_step_ids=step_ids or ["action"],
    )


def test_valid_plan_compliance_and_execution():
    request, adapter = make_request()

    result, validator = run(request, adapter, allowed_decision())

    assert result.status == IntegrationStatus.EXECUTION_COMPLETED
    assert result.execution_result is not None
    assert adapter.calls == ["action"]
    assert validator.calls == 1


def test_compliance_block_stops_before_execution():
    request, adapter = make_request()
    decision = ComplianceDecision(allowed=False, policy_version="policy-1", reason="Not allowed")

    result, _ = run(request, adapter, decision)

    assert result.status == IntegrationStatus.BLOCKED_BY_COMPLIANCE
    assert result.execution_result is None
    assert adapter.calls == []


def test_missing_authorization_stops_before_execution():
    request, adapter = make_request(authorization=False)

    result, _ = run(request, adapter, allowed_decision())

    assert result.status == IntegrationStatus.BLOCKED_BY_AUTHORIZATION
    assert result.execution_result.status.value == "blocked"
    assert adapter.calls == []


def test_missing_fact_stops_before_execution():
    request, adapter = make_request()
    request.confirmed_context.facts = {}

    result, _ = run(request, adapter, allowed_decision())

    assert result.status == IntegrationStatus.BLOCKED_BY_MISSING_INFORMATION
    assert adapter.calls == []


def test_missing_human_approval_is_preserved():
    request, adapter = make_request(approval_satisfied=False)

    result, _ = run(request, adapter, allowed_decision())

    assert result.status == IntegrationStatus.BLOCKED_BY_AUTHORIZATION
    assert result.approval_state.missing_step_ids == ["approval"]
    assert adapter.calls == []


@pytest.mark.parametrize("field, value", [("plan_id", "wrong-plan"), ("plan_version", 2)])
def test_plan_binding_mismatch_stops_before_compliance_and_execution(field, value):
    request, adapter = make_request(**{field: value})

    result, validator = run(request, adapter, allowed_decision())

    assert result.status == IntegrationStatus.BLOCKED_BY_PLAN
    assert validator.calls == 0
    assert adapter.calls == []


def test_partial_execution_is_preserved():
    request, adapter = make_request(outcomes={
        "action": AdapterResult(status="completed", outcome="Prepared"),
        "second-action": AdapterResult(status="failed", outcome="Failure", retryable=True),
    })
    second = request.workflow_plan.steps[1].model_copy(update={
        "step_id": "second-action",
        "sequence": 3,
        "depends_on": ["action"],
        "required_fact_keys": [],
    })
    request.workflow_plan.steps.append(second)
    request.execution_authorization.approved_step_ids.append("second-action")
    request.workflow_plan = request.workflow_plan.model_copy(update={"steps": request.workflow_plan.steps})

    result, _ = run(request, adapter, allowed_decision(["action", "second-action"]))

    assert result.status == IntegrationStatus.EXECUTION_PARTIAL
    assert result.execution_result.status.value == "partial"
    assert result.execution_result.step_results[1].retryable is True
    assert adapter.calls == ["action", "second-action"]


def test_execution_failure_is_preserved():
    request, adapter = make_request(outcomes={"action": AdapterResult(status="failed", outcome="Failure")})

    result, _ = run(request, adapter, allowed_decision())

    assert result.status == IntegrationStatus.EXECUTION_FAILED
    assert result.execution_result.failure_reason == "Failure"


def test_no_compliance_decision_fails_closed():
    request, adapter = make_request()

    result, _ = run(request, adapter, None)

    assert result.status == IntegrationStatus.BLOCKED_BY_COMPLIANCE
    assert result.execution_result is None
    assert adapter.calls == []


def test_human_intervention_result_is_preserved():
    request, adapter = make_request(outcomes={
        "action": AdapterResult(
            status="human_intervention_required",
            outcome="OTP required",
            human_intervention=HumanIntervention(
                reason="OTP required",
                required_user_action="Enter OTP",
                checkpoint_reference="checkpoint-1",
            ),
        )
    })

    result, _ = run(request, adapter, allowed_decision())

    assert result.status == IntegrationStatus.HUMAN_INTERVENTION_REQUIRED
    assert result.execution_result.human_intervention.checkpoint_reference == "checkpoint-1"


def test_integration_does_not_mutate_request_context():
    request, adapter = make_request()
    before = deepcopy(request.confirmed_context.model_dump())

    result, _ = run(request, adapter, allowed_decision())

    assert result.status == IntegrationStatus.EXECUTION_COMPLETED
    assert request.confirmed_context.model_dump() == before


def test_real_compliance_agent_is_wired_through_boundary_adapter():
    request, adapter = make_request()
    compliance_adapter = ComplianceAgentAdapter(
        agent=ComplianceValidationAgent(),
        validation_input=ComplianceValidationInput(
            document_type="AADHAAR",
            service_type="aadhaar_update",
            requirements={},
        ),
        policy_version="compliance-v1",
        authorized_step_ids=["action"],
    )
    result = ExecutionIntegrationService(
        executor=__import__(
            "agents.utility_based.execution_assistance.executor",
            fromlist=["ExecutionCoordinator"],
        ).ExecutionCoordinator(adapter),
        compliance_validator=compliance_adapter,
    ).run(request)

    assert result.status == IntegrationStatus.EXECUTION_COMPLETED
    assert result.compliance_decision.allowed is True
    assert result.compliance_decision.policy_version == "compliance-v1"
    assert adapter.calls == ["action"]


def test_real_compliance_adapter_requires_explicit_step_scope():
    request, adapter = make_request()
    compliance_adapter = ComplianceAgentAdapter(
        agent=ComplianceValidationAgent(),
        validation_input=ComplianceValidationInput(),
        policy_version="compliance-v1",
        authorized_step_ids=[],
    )
    result = ExecutionIntegrationService(
        executor=__import__(
            "agents.utility_based.execution_assistance.executor",
            fromlist=["ExecutionCoordinator"],
        ).ExecutionCoordinator(adapter),
        compliance_validator=compliance_adapter,
    ).run(request)

    assert result.status == IntegrationStatus.BLOCKED_BY_COMPLIANCE
    assert adapter.calls == []
