from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from agents.orchestration.monitoring.schemas import SessionState
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
    ExecutionRequest,
    ExecutionStatus,
    FactStatus,
    HumanIntervention,
    MockExecutionAdapter,
    StepExecutionStatus,
)
from agents.utility_based.execution_assistance.executor import ExecutionCoordinator


NOW = datetime.now(timezone.utc)


def make_request(*, outcomes=None, **changes):
    approval = PlanStep(
        step_id="approval",
        sequence=1,
        title="Approve action",
        description="Human approval",
        step_type=StepType.HUMAN_APPROVAL,
        requires_user_action=True,
        requires_explicit_approval=True,
    )
    action = PlanStep(
        step_id="action",
        sequence=2,
        title="Prepare Aadhaar information",
        description="Prepare information",
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
            approval_id="approval-approval",
            step_id="approval",
            reason="Review",
            confirmation="Confirmed",
        )],
    )
    request = ExecutionRequest(
        workflow_plan=plan,
        plan_id="plan-1",
        plan_version=1,
        execution_authorization=ExecutionAuthorization(
            authorization_id="auth-1",
            user_id="user-1",
            session_id="session-1",
            plan_id="plan-1",
            plan_version=1,
            approved_step_ids=["action"],
            satisfied_approval_step_ids=["approval"],
            approved_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        ),
        compliance_decision=ComplianceDecision(
            allowed=True,
            policy_version="policy-1",
            reason="Allowed",
            authorized_step_ids=["action"],
        ),
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
        execution_options=ExecutionOptions(execution_id="execution-1"),
    )
    return request.model_copy(update=changes), MockExecutionAdapter(outcomes)


def run(request, adapter):
    return ExecutionCoordinator(adapter).execute(request)


def test_valid_approved_execution():
    request, adapter = make_request()

    result = run(request, adapter)

    assert result.status == ExecutionStatus.COMPLETED
    assert adapter.calls == ["action"]
    assert result.step_results[0].status == StepExecutionStatus.COMPLETED


@pytest.mark.parametrize("change, text", [
    ({"execution_authorization": None}, "authorization"),
    ({"plan_id": "wrong-plan"}, "plan_id"),
    ({"plan_version": 2}, "plan_version"),
    ({"compliance_decision": ComplianceDecision(allowed=False, policy_version="p", reason="Blocked")}, "blocked"),
])
def test_request_safety_gates(change, text):
    request, adapter = make_request(**change)

    result = run(request, adapter)

    assert result.status == ExecutionStatus.BLOCKED
    assert text in (result.failure_reason or "").lower()
    assert adapter.calls == []


def test_expired_and_revoked_authorization():
    expired, adapter = make_request()
    expired.execution_authorization.expires_at = NOW - timedelta(seconds=1)
    assert run(expired, adapter).status == ExecutionStatus.BLOCKED

    revoked, adapter = make_request()
    revoked.execution_authorization.revoked = True
    assert run(revoked, adapter).status == ExecutionStatus.BLOCKED


def test_unapproved_step_and_blocked_compliance_scope():
    request, adapter = make_request()
    request.execution_authorization.approved_step_ids = []
    result = run(request, adapter)
    assert result.status == ExecutionStatus.BLOCKED
    assert "not authorized" in result.failure_reason

    request, adapter = make_request()
    request.compliance_decision.authorized_step_ids = []
    result = run(request, adapter)
    assert result.status == ExecutionStatus.BLOCKED
    assert adapter.calls == []


@pytest.mark.parametrize("fact_status", [FactStatus.UNCONFIRMED, FactStatus.AMBIGUOUS, FactStatus.CONFLICTING])
def test_unsafe_fact(fact_status):
    request, adapter = make_request()
    request.confirmed_context.facts["new_address"].status = fact_status

    result = run(request, adapter)

    assert result.status == ExecutionStatus.BLOCKED
    assert adapter.calls == []


def test_missing_fact_and_missing_provenance():
    request, adapter = make_request()
    request.confirmed_context.facts = {}
    assert run(request, adapter).status == ExecutionStatus.BLOCKED

    request, adapter = make_request()
    request.confirmed_context.facts["new_address"].provenance = " "
    assert run(request, adapter).status == ExecutionStatus.BLOCKED


def test_dependency_violation():
    request, adapter = make_request()
    request.workflow_plan.steps[0].step_type = StepType.PREPARE_INFORMATION
    request.workflow_plan.approval_points = []
    request.execution_authorization.satisfied_approval_step_ids = []
    result = run(request, adapter)

    assert result.status == ExecutionStatus.BLOCKED
    assert "dependency" in (result.failure_reason or "")


def test_human_intervention_pauses_execution():
    intervention = HumanIntervention(
        reason="OTP is required",
        required_user_action="Enter the OTP",
        checkpoint_reference="checkpoint-1",
    )
    request, adapter = make_request(outcomes={
        "action": AdapterResult(
            status="human_intervention_required",
            outcome="Paused for OTP",
            human_intervention=intervention,
        )
    })

    result = run(request, adapter)

    assert result.status == ExecutionStatus.HUMAN_INTERVENTION_REQUIRED
    assert result.human_intervention.checkpoint_reference == "checkpoint-1"


def test_human_intervention_without_checkpoint_fails_closed():
    request, adapter = make_request(outcomes={
        "action": AdapterResult(
            status="human_intervention_required",
            outcome="Paused without checkpoint",
        )
    })

    result = run(request, adapter)

    assert result.status == ExecutionStatus.BLOCKED
    assert "checkpoint" in (result.failure_reason or "").lower()


def test_resume_requires_completed_human_action():
    request, adapter = make_request(
        resume_checkpoint={
            "checkpoint_reference": "checkpoint-1",
            "completed_step_ids": [],
            "human_action_completed": False,
        }
    )

    result = run(request, adapter)

    assert result.status == ExecutionStatus.BLOCKED
    assert "human intervention" in (result.failure_reason or "").lower()


def test_resume_rejects_steps_absent_from_plan():
    request, adapter = make_request(
        resume_checkpoint={
            "checkpoint_reference": "checkpoint-1",
            "completed_step_ids": ["not-in-plan"],
            "human_action_completed": True,
        }
    )

    result = run(request, adapter)

    assert result.status == ExecutionStatus.BLOCKED
    assert "absent" in (result.failure_reason or "").lower()


@pytest.mark.parametrize("status, expected", [
    ("failed", ExecutionStatus.FAILED),
    ("submitted_pending", ExecutionStatus.SUBMITTED_PENDING),
])
def test_adapter_outcomes(status, expected):
    request, adapter = make_request(outcomes={"action": AdapterResult(status=status, outcome="Adapter result", retryable=status == "failed")})

    result = run(request, adapter)

    assert result.status == expected
    assert result.step_results[0].retryable is (status == "failed")


def test_partial_execution_and_stops_after_failure():
    request, adapter = make_request(outcomes={"action": AdapterResult(status="failed", outcome="Failed", retryable=False)})
    second = request.workflow_plan.steps[1].model_copy(update={
        "step_id": "second-action",
        "sequence": 3,
        "depends_on": ["action"],
        "required_fact_keys": [],
    })
    request.workflow_plan.steps.append(second)
    request.execution_authorization.approved_step_ids.append("second-action")
    request.compliance_decision.authorized_step_ids.append("second-action")

    result = run(request, adapter)

    assert result.status == ExecutionStatus.FAILED
    assert adapter.calls == ["action"]


def test_completed_step_then_failure_returns_partial():
    request, adapter = make_request(outcomes={
        "action": AdapterResult(status="completed", outcome="Prepared"),
        "second-action": AdapterResult(status="failed", outcome="Portal error", retryable=True),
    })
    second = request.workflow_plan.steps[1].model_copy(update={
        "step_id": "second-action",
        "sequence": 3,
        "depends_on": ["action"],
        "required_fact_keys": [],
    })
    request.workflow_plan.steps.append(second)
    request.execution_authorization.approved_step_ids.append("second-action")
    request.compliance_decision.authorized_step_ids.append("second-action")

    result = run(request, adapter)

    assert result.status == ExecutionStatus.PARTIAL
    assert adapter.calls == ["action", "second-action"]


def test_unsupported_step_and_absent_plan_step():
    request, adapter = make_request()
    request.workflow_plan.steps[1] = request.workflow_plan.steps[1].model_copy(update={"step_type": StepType.REVIEW_EVIDENCE})
    result = run(request, adapter)
    assert result.status == ExecutionStatus.BLOCKED
    assert adapter.calls == []

    request, adapter = make_request()
    request.execution_authorization.approved_step_ids.append("not-in-plan")
    result = run(request, adapter)
    assert result.status == ExecutionStatus.BLOCKED


def test_execution_does_not_mutate_session_or_confirmed_context():
    request, adapter = make_request()
    session = SessionState(session_id="session-1", summary="Conversation")
    before_context = deepcopy(request.confirmed_context.model_dump())
    before_session = deepcopy(session.model_dump())

    result = run(request, adapter)

    assert result.status == ExecutionStatus.COMPLETED
    assert request.confirmed_context.model_dump() == before_context
    assert session.model_dump() == before_session