import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from agents.orchestration.workflow_planning.schema import StepType
from agents.utility_based.execution_assistance.schema import (
    ActionExecutionResult, ExecutionOutcome, AdapterResult, AdapterStatus,
    ConfirmedExecutionContext, ExecutionStatus,
)
from agents.utility_based.execution_assistance.interactive_session import (
    InteractivePortalManager, ActiveBrowserSession, PortalStage,
)
from agents.utility_based.execution_assistance.executor import ExecutionCoordinator
from agents.utility_based.execution_assistance.tests.test_execution import make_request


def manager_at(stage=PortalStage.STAGE_1B_LOGIN, page=None):
    manager = InteractivePortalManager()
    session = ActiveBrowserSession(session_id="test", context=ConfirmedExecutionContext(session_id="test"), current_stage=stage, page=page)
    manager._sessions["test"] = session
    return manager, session


@pytest.mark.parametrize("state", list(ExecutionOutcome))
def test_only_verified_result_advances(state):
    manager, session = manager_at()
    result = ActionExecutionResult(status=state, message="Fixture outcome", verification_evidence="Fixture authenticated state" if state == ExecutionOutcome.VERIFIED_SUCCESS else None)
    manager._execute_stage_action_on_portal = AsyncMock(return_value=result)
    response = asyncio.run(manager.submit_step("test", True))
    assert (session.current_stage == PortalStage.STAGE_2_SERVICE) == (state == ExecutionOutcome.VERIFIED_SUCCESS)
    assert response["execution_result"]["status"] == state.value
    assert response["is_completed"] is False


def test_missing_page_blocks():
    manager, session = manager_at()
    response = asyncio.run(manager.submit_step("test", True))
    assert response["execution_result"]["status"] == "BLOCKED"
    assert session.current_stage == PortalStage.STAGE_1B_LOGIN


@pytest.mark.parametrize("value", [None, {}, True])
def test_invalid_action_result_keeps_stage(value):
    manager, session = manager_at()
    manager._execute_stage_action_on_portal = AsyncMock(return_value=value)
    response = asyncio.run(manager.submit_step("test", True))
    assert response["execution_result"]["status"] == "UNKNOWN"
    assert session.current_stage == PortalStage.STAGE_1B_LOGIN


def test_exception_does_not_advance_or_expose_details():
    manager, session = manager_at()
    manager._execute_stage_action_on_portal = AsyncMock(side_effect=RuntimeError("sensitive fixture"))
    response = asyncio.run(manager.submit_step("test", True))
    assert response["execution_result"]["status"] == "FAILED"
    assert "sensitive fixture" not in str(response)
    assert session.current_stage == PortalStage.STAGE_1B_LOGIN


def test_no_consent_does_not_execute():
    manager, _ = manager_at()
    manager._execute_stage_action_on_portal = AsyncMock()
    response = asyncio.run(manager.submit_step("test", False))
    manager._execute_stage_action_on_portal.assert_not_called()
    assert response["execution_result"]["status"] == "NEEDS_USER"


def test_click_return_is_not_login_verification():
    page = Mock()
    page.wait_for_timeout = AsyncMock()
    manager, session = manager_at(page=page)
    manager._smart_click_or_submit = AsyncMock(return_value=True)
    response = asyncio.run(manager.submit_step("test", True))
    assert response["execution_result"]["status"] == "UNKNOWN"
    assert session.current_stage == PortalStage.STAGE_1B_LOGIN


def test_final_submission_requires_verified_official_reference():
    from agents.utility_based.execution_assistance.tests.test_final_review import ready_session, approved
    manager, session, _ = ready_session()
    approved(session)
    manager._execute_stage_action_on_portal = AsyncMock(return_value=ActionExecutionResult(status="VERIFIED_SUCCESS", message="Observed", verification_evidence="Fixture receipt"))
    response = asyncio.run(manager.submit_step(session.session_id, True))
    assert not response["is_completed"]
    assert response["urn"] is None
    assert response["execution_uncertain"]
    assert session.current_stage == PortalStage.STAGE_5_REVIEW
    manager._execute_stage_action_on_portal.return_value = ActionExecutionResult(status="VERIFIED_SUCCESS", message="Observed", verification_evidence="Fixture receipt", official_reference="official-fixture-reference")
    response = asyncio.run(manager.submit_step(session.session_id, True))
    assert response["execution_result"]["status"] == "BLOCKED"
    manager._execute_stage_action_on_portal.assert_awaited_once()


def test_verified_result_requires_evidence():
    with pytest.raises(ValidationError):
        ActionExecutionResult(status="VERIFIED_SUCCESS", message="Returned")
    result = ActionExecutionResult(status="UNKNOWN", message="Unverified", official_reference="local-URN")
    assert result.official_reference is None


@pytest.mark.parametrize("state", ["VERIFIED_SUCCESS", "FAILED", "BLOCKED", "UNKNOWN"])
def test_coordinator_propagates_external_result(state):
    request, _ = make_request()
    request.workflow_plan.steps[1].step_type = StepType.USER_ACTION
    action = ActionExecutionResult(status=state, message="Fixture", verification_evidence="Observed fixture portal state" if state == "VERIFIED_SUCCESS" else None)
    adapter = Mock()
    adapter.execute_step.return_value = AdapterResult(status="completed", outcome="Returned", execution_result=action)
    response = ExecutionCoordinator(adapter).execute(request)
    assert (response.status == ExecutionStatus.COMPLETED) == (state == "VERIFIED_SUCCESS")
    assert response.step_results[0].execution_result.status.value == state
    assert any(event.event_type == "step_completed" for event in response.events) == (state == "VERIFIED_SUCCESS")


@pytest.mark.parametrize("bad", [None, AdapterResult(status="completed", outcome="Returned", portal_reference="local-URN")])
def test_coordinator_does_not_trust_return_or_local_reference(bad):
    request, _ = make_request()
    request.workflow_plan.steps[1].step_type = StepType.USER_ACTION
    adapter = Mock()
    adapter.execute_step.return_value = bad
    response = ExecutionCoordinator(adapter).execute(request)
    assert response.status != ExecutionStatus.COMPLETED
    assert response.step_results[0].portal_reference is None


def test_coordinator_exception_fails_closed():
    request, _ = make_request()
    adapter = Mock()
    adapter.execute_step.side_effect = RuntimeError("sensitive fixture")
    response = ExecutionCoordinator(adapter).execute(request)
    assert response.status == ExecutionStatus.FAILED
    assert "sensitive fixture" not in str(response)


def test_coordinator_explicit_needs_user_preserves_checkpoint():
    from agents.utility_based.execution_assistance.schema import HumanIntervention
    request, _ = make_request()
    request.workflow_plan.steps[1].step_type = StepType.USER_ACTION
    adapter = Mock()
    adapter.execute_step.return_value = AdapterResult(
        status="human_intervention_required", outcome="Human action needed",
        execution_result=ActionExecutionResult(status="NEEDS_USER", message="Human action needed"),
        human_intervention=HumanIntervention(reason="Human authentication", required_user_action="Complete checkpoint", checkpoint_reference="fixture-checkpoint"),
    )
    response = ExecutionCoordinator(adapter).execute(request)
    assert response.status == ExecutionStatus.HUMAN_INTERVENTION_REQUIRED
    assert response.human_intervention.checkpoint_reference == "fixture-checkpoint"
    assert response.step_results[0].execution_result.status == ExecutionOutcome.NEEDS_USER
    assert not any(event.event_type == "step_completed" for event in response.events)
