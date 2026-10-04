from datetime import datetime, timedelta, timezone
from copy import deepcopy

import pytest

from agents.orchestration.integration import ExecutionIntegrationService, IntegrationResult, IntegrationStatus
from agents.orchestration.intent_understanding import IntentUnderstandingService
from agents.orchestration.monitoring import MonitoringService
from agents.orchestration.pipeline import OrchestrationRequest, OrchestrationStatus, TopLevelOrchestrator
from agents.orchestration.workflow_planning.schema import ApprovalPoint, PlanStatus, PlanStep, StepType, WorkflowPlan
from agents.knowledge_based.information_retrieval.schemas import RetrievalResult, RetrievalStatus
from agents.utility_based.execution_assistance import (
    AdapterResult,
    ComplianceDecision,
    ConfirmedExecutionContext,
    ConfirmedFact,
    ExecutionAuthorization,
    ExecutionOptions,
    ExecutionResult,
    ExecutionStatus,
    FactStatus,
    MockExecutionAdapter,
    StepExecutionResult,
    StepExecutionStatus,
)
from agents.utility_based.execution_assistance.executor import ExecutionCoordinator


class FakeRetrieval:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def retrieve(self, request, user_documents=None):
        self.calls += 1
        return self.result


class FakePlanner:
    def __init__(self, plan=None, error=None):
        self.plan = plan
        self.error = error
        self.calls = 0

    def __call__(self, request):
        self.calls += 1
        if self.error:
            raise self.error
        return self.plan


class FakeIntegration:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def run(self, request):
        self.calls += 1
        return self.result


class FakeResponse:
    def __init__(self):
        self.inputs = []

    def generate(self, result):
        self.inputs.append(result)
        return {"headline": result.overall_status}


class StaticCompliance:
    def __init__(self, decision):
        self.decision = decision

    def validate(self, workflow_plan):
        return self.decision


def make_plan(status=PlanStatus.READY):
    approval = PlanStep(
        step_id="approval",
        sequence=1,
        title="Approve action",
        description="Review action",
        step_type=StepType.HUMAN_APPROVAL,
        requires_explicit_approval=True,
    )
    action = PlanStep(
        step_id="action",
        sequence=2,
        title="Prepare address",
        description="Prepare confirmed address",
        step_type=StepType.PREPARE_INFORMATION,
        depends_on=["approval"],
        required_fact_keys=["address"],
    )
    return WorkflowPlan(
        planning_request_id="planning-1",
        request_id="plan-1",
        session_id="session-1",
        service="Aadhaar",
        task="update",
        target="address",
        plan_status=status,
        steps=[approval, action],
        approval_points=[ApprovalPoint(approval_id="approval-1", step_id="approval", reason="Review", confirmation="Confirmed")],
    )


def make_retrieval(status=RetrievalStatus.SUCCESS):
    return RetrievalResult(
        result_id="result-1",
        request_id="session-1",
        service="Aadhaar",
        domain="aadhaar",
        retrieval_status=status,
        requirements=[],
    )


def make_request(message="Update Aadhaar address to 12 Main Street", **changes):
    request = OrchestrationRequest(
        user_request={"session_id": "session-1", "user_message": message, "domain": "aadhaar"},
        execution_authorization=ExecutionAuthorization(
            authorization_id="auth-1",
            user_id="user-1",
            session_id="session-1",
            plan_id="plan-1",
            plan_version=1,
            approved_step_ids=["action"],
            satisfied_approval_step_ids=["approval"],
            approved_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ),
        confirmed_context=ConfirmedExecutionContext(
            session_id="session-1",
            facts={"address": ConfirmedFact(value="12 Main Street", provenance="user-confirmation", status=FactStatus.CONFIRMED, allowed_for_execution=True)},
        ),
    )
    return request.model_copy(update=changes)


def make_actual_integration(adapter=None, decision=None):
    adapter = adapter or MockExecutionAdapter()
    decision = decision or ComplianceDecision(allowed=True, policy_version="p1", reason="Allowed", authorized_step_ids=["action"])
    return ExecutionIntegrationService(ExecutionCoordinator(adapter), StaticCompliance(decision)), adapter


def run_orchestrator(retrieval=None, planner=None, integration=None, response=None):
    return TopLevelOrchestrator(
        intent_service=IntentUnderstandingService(),
        retrieval_agent=FakeRetrieval(retrieval or make_retrieval()),
        workflow_planner=planner or FakePlanner(make_plan()),
        execution_integration=integration,
        monitoring_service=MonitoringService(),
        response_generator=response or FakeResponse(),
    )


def test_successful_aadhaar_pipeline():
    integration, adapter = make_actual_integration()
    response = FakeResponse()

    result = run_orchestrator(integration=integration, response=response).run(make_request())

    assert result.status == OrchestrationStatus.EXECUTION_COMPLETED
    assert result.session_state.session_id == "session-1"
    assert result.integration_result.status == IntegrationStatus.EXECUTION_COMPLETED
    assert adapter.calls == ["action"]
    assert response.inputs[-1].overall_status == "COMPLETED"


def test_missing_user_information_stops_before_retrieval():
    retrieval = FakeRetrieval(make_retrieval())
    planner = FakePlanner(make_plan())
    response = FakeResponse()
    orchestrator = TopLevelOrchestrator(IntentUnderstandingService(), retrieval, planner, None, MonitoringService(), response)

    result = orchestrator.run(make_request("Update Aadhaar address"))

    assert result.status == OrchestrationStatus.NEEDS_CLARIFICATION
    assert retrieval.calls == 0
    assert planner.calls == 0
    assert response.inputs[-1].overall_status == "ACTION_REQUIRED"


def test_retrieval_failure_stops_before_planning():
    retrieval = FakeRetrieval(make_retrieval(RetrievalStatus.FAILED))
    planner = FakePlanner(make_plan())
    orchestrator = TopLevelOrchestrator(IntentUnderstandingService(), retrieval, planner, None, MonitoringService(), FakeResponse())

    result = orchestrator.run(make_request())

    assert result.status == OrchestrationStatus.RETRIEVAL_BLOCKED
    assert planner.calls == 0


def test_planning_failure_stops_before_execution():
    integration = FakeIntegration(None)
    planner = FakePlanner(error=RuntimeError("planner failure"))
    orchestrator = run_orchestrator(planner=planner, integration=integration)

    result = orchestrator.run(make_request())

    assert result.status == OrchestrationStatus.PLANNING_FAILED
    assert integration.calls == 0


@pytest.mark.parametrize("decision, expected", [
    (ComplianceDecision(allowed=False, policy_version="p1", reason="warning", authorized_step_ids=[]), OrchestrationStatus.COMPLIANCE_BLOCKED),
    (ComplianceDecision(allowed=False, policy_version="p1", reason="blocked", authorized_step_ids=[]), OrchestrationStatus.COMPLIANCE_BLOCKED),
])
def test_compliance_non_allow_stops_execution(decision, expected):
    integration, adapter = make_actual_integration(decision=decision)
    result = run_orchestrator(integration=integration).run(make_request())

    assert result.status == expected
    assert adapter.calls == []


def test_missing_execution_authorization_is_preserved():
    integration, adapter = make_actual_integration()
    request = make_request(execution_authorization=None)

    result = run_orchestrator(integration=integration).run(request)

    assert result.status == OrchestrationStatus.AUTHORIZATION_BLOCKED
    assert adapter.calls == []


def test_human_intervention_pauses_pipeline():
    intervention_adapter = MockExecutionAdapter({
        "action": AdapterResult(
            status="human_intervention_required",
            outcome="OTP required",
            human_intervention={
                "reason": "OTP required",
                "required_user_action": "Enter OTP",
                "checkpoint_reference": "checkpoint-1",
            },
        )
    })
    integration, adapter = make_actual_integration(intervention_adapter)

    result = run_orchestrator(integration=integration).run(make_request())

    assert result.status == OrchestrationStatus.AWAITING_HUMAN_ACTION
    assert result.execution_events
    assert adapter.calls == ["action"]


def test_partial_execution_is_preserved():
    execution = ExecutionResult(execution_id="e1", plan_id="plan-1", plan_version=1, status=ExecutionStatus.PARTIAL)
    integration = FakeIntegration(IntegrationResult(status=IntegrationStatus.EXECUTION_PARTIAL, plan_id="plan-1", plan_version=1, execution_result=execution))

    result = run_orchestrator(integration=integration).run(make_request())

    assert result.status == OrchestrationStatus.EXECUTION_PARTIAL
    assert result.integration_result.execution_result.status == ExecutionStatus.PARTIAL


def test_execution_failure_is_preserved():
    execution = ExecutionResult(execution_id="e1", plan_id="plan-1", plan_version=1, status=ExecutionStatus.FAILED, failure_reason="adapter failure")
    integration = FakeIntegration(IntegrationResult(status=IntegrationStatus.EXECUTION_FAILED, plan_id="plan-1", plan_version=1, execution_result=execution))

    result = run_orchestrator(integration=integration).run(make_request())

    assert result.status == OrchestrationStatus.EXECUTION_FAILED
    assert result.blocking_reason is None
    assert result.integration_result.execution_result.failure_reason == "adapter failure"


def test_response_generator_receives_final_structured_state():
    response = FakeResponse()
    integration, _ = make_actual_integration()

    result = run_orchestrator(integration=integration, response=response).run(make_request())

    assert result.response_result == {"headline": "COMPLETED"}
    assert response.inputs[0].service_name == "Aadhaar"


def test_session_state_remains_conversational_and_is_not_mutated():
    integration, _ = make_actual_integration()
    previous = None
    request = make_request(previous_session_state=previous)
    before = deepcopy(request.model_dump())

    result = run_orchestrator(integration=integration).run(request)

    assert result.session_state.intent_type == "update_request"
    assert request.model_dump() == before
    assert not hasattr(result.session_state, "application_id")


def test_no_agent_runs_after_missing_confirmed_context():
    integration, adapter = make_actual_integration()
    planner = FakePlanner(make_plan())
    request = make_request(confirmed_context=None)

    result = run_orchestrator(planner=planner, integration=integration).run(request)

    assert result.status == OrchestrationStatus.NEEDS_CLARIFICATION
    assert adapter.calls == []
