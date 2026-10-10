"""B.3.7 boundary tests: synthetic sessions and mocked external actions only."""
import asyncio
from unittest.mock import AsyncMock
import pytest
from agents.utility_based.execution_assistance.tests.test_authentication_session import fixture_session
from agents.utility_based.execution_assistance.tests.test_final_review import ready_session, approved
from agents.utility_based.execution_assistance.schema import ActionExecutionResult
from agents.utility_based.execution_assistance.interactive_session import PortalStage


def request(manager, session, identity="attempt", **extra):
    return manager.submit_step(session.session_id, True, request_id=identity,
        expected_stage=session.current_stage.value, expected_state_version=session.execution_version, **extra)


def outcome(status):
    return ActionExecutionResult(status=status, message="Synthetic outcome",
        verification_evidence="Synthetic authoritative evidence" if status == "VERIFIED_SUCCESS" else None)


def test_successful_request_replay_never_dispatches_next_stage():
    manager, session, _ = fixture_session()
    manager._execute_stage_action_on_portal = AsyncMock(return_value=outcome("VERIFIED_SUCCESS"))
    stage = session.current_stage.value
    async def scenario():
        first = await request(manager, session)
        assert first["execution_state_version"] == 1
        replay = await manager.submit_step(session.session_id, True, request_id="attempt", expected_stage=stage, expected_state_version=0)
        assert replay["execution_result"]["status"] == "BLOCKED"
        assert manager._execute_stage_action_on_portal.await_count == 1
        assert session.current_stage.value != stage
    asyncio.run(scenario())


@pytest.mark.parametrize("status", ["FAILED", "UNKNOWN", "NEEDS_USER", "BLOCKED"])
def test_dispatched_non_success_cannot_retry(status):
    manager, session, _ = fixture_session()
    manager._execute_stage_action_on_portal = AsyncMock(return_value=outcome(status))
    async def scenario():
        result = await request(manager, session)
        assert result["execution_uncertain"] is True
        assert result["attempt_outcome"] == "uncertain"
        await request(manager, session, "fresh", user_inputs={"pincode": "641025"})
        assert manager._execute_stage_action_on_portal.await_count == 1
    asyncio.run(scenario())


def test_proven_pre_dispatch_failure_allows_distinct_current_version_retry():
    manager, session, _ = fixture_session()
    manager._execute_stage_action_on_portal = AsyncMock(return_value=outcome("VERIFIED_SUCCESS"))
    async def scenario():
        result = await manager.submit_step(session.session_id, False, request_id="no-consent", expected_stage=session.current_stage.value, expected_state_version=0)
        assert result["retry_permitted"] is True
        assert not session.execution_uncertain
        assert (await request(manager, session, "no-consent"))["execution_result"]["status"] == "BLOCKED"
        await request(manager, session, "fresh")
        assert manager._execute_stage_action_on_portal.await_count == 1
    asyncio.run(scenario())


@pytest.mark.parametrize("stage,version", [("wrong", 0), ("stage_1b_login", 99)])
def test_stale_request_rejected_before_correction(stage, version):
    manager, session, _ = fixture_session()
    original = session.context.model_dump_json()
    async def scenario():
        result = await manager.submit_step(session.session_id, True, user_inputs={"pincode": "641025"}, request_id="stale", expected_stage=stage, expected_state_version=version)
        assert result["execution_result"]["status"] == "BLOCKED"
        assert session.context.model_dump_json() == original
        assert not session.attempts
    asyncio.run(scenario())


def test_atomic_reservation_concurrency_and_no_lock_across_await():
    manager, session, _ = fixture_session()
    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()
        async def action(*args):
            assert session.active_attempt == "first"
            assert session.attempts["first"]["state"] == "dispatch_may_have_occurred"
            assert not manager._attempt_lock._is_owned()
            assert not manager._lock.locked()
            started.set(); await release.wait()
            return outcome("VERIFIED_SUCCESS")
        manager._execute_stage_action_on_portal = AsyncMock(side_effect=action)
        task = asyncio.create_task(request(manager, session, "first"))
        await started.wait()
        assert (await request(manager, session, "second"))["execution_result"]["status"] == "BLOCKED"
        release.set(); await task
        assert manager._execute_stage_action_on_portal.await_count == 1
    asyncio.run(scenario())


@pytest.mark.parametrize("after_dispatch", [False, True])
def test_cancellation_of_reserved_attempt_is_uncertain(after_dispatch):
    manager, session, _ = fixture_session()
    async def scenario():
        entered = asyncio.Event()
        async def wait(*args):
            assert session.active_attempt == "attempt"
            assert session.attempts["attempt"]["state"] == ("dispatch_may_have_occurred" if after_dispatch else "reserved")
            entered.set(); await asyncio.Event().wait()
        if after_dispatch:
            manager._execute_stage_action_on_portal = AsyncMock(side_effect=wait)
        else:
            manager._submit_step_impl = wait
        task = asyncio.create_task(request(manager, session))
        await entered.wait(); task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert session.execution_uncertain
        assert session.active_attempt is None
        assert (await request(manager, session, "fresh"))["execution_result"]["status"] == "BLOCKED"
    asyncio.run(scenario())


def test_dispatch_exception_is_uncertain():
    manager, session, _ = fixture_session()
    manager._execute_stage_action_on_portal = AsyncMock(side_effect=RuntimeError("synthetic"))
    result = asyncio.run(request(manager, session))
    assert result["execution_uncertain"]


def test_capacity_fails_closed():
    manager, session, _ = fixture_session()
    session.attempts = {str(i): {} for i in range(128)}
    result = asyncio.run(request(manager, session))
    assert result["execution_result"]["status"] == "BLOCKED"
    assert len(session.attempts) == 128


def test_request_identity_does_not_create_final_approval():
    manager, session, page = ready_session()
    result = asyncio.run(request(manager, session))
    assert result["is_completed"] is False
    assert session.final_review.validate(__import__("agents.utility_based.execution_assistance.final_review", fromlist=["submission_package"]).submission_package(session))


def test_changed_package_cannot_reuse_approval_with_new_id():
    manager, session, page = ready_session()
    approved(session)
    session.context.facts["pincode"].value = "641025"
    result = asyncio.run(request(manager, session, "fresh"))
    assert result["is_completed"] is False
    assert session.current_stage == PortalStage.STAGE_5_REVIEW


def test_internal_final_approval_does_not_clear_uncertainty():
    manager, session, page = ready_session()
    package = approved(session)
    session.execution_uncertain = True
    manager._execute_stage_action_on_portal = AsyncMock()
    session.final_review.invalidate()
    review = asyncio.run(manager.review_submission(session.session_id))["final_review"]
    result = asyncio.run(manager.final_review_action(session.session_id, "Approve & Submit", review["binding"]))
    assert not result.get("is_completed", False)
    manager._execute_stage_action_on_portal.assert_not_awaited()


def test_duplicate_changed_payload_rejected_before_mutation():
    manager, session, _ = fixture_session()
    manager._execute_stage_action_on_portal = AsyncMock(return_value=outcome("VERIFIED_SUCCESS"))
    async def scenario():
        await request(manager, session)
        before = session.context.model_dump_json()
        response = await request(manager, session, user_inputs={"pincode": "641025"})
        assert response["execution_result"]["status"] == "BLOCKED"
        assert session.context.model_dump_json() == before
        manager._execute_stage_action_on_portal.assert_awaited_once()
    asyncio.run(scenario())


def test_uncertainty_survives_manager_replacement_and_correction(monkeypatch):
    from agents.utility_based.execution_assistance.tests.test_review_context import setup, confirmed
    from agents.utility_based.execution_assistance.review_context import ReviewError
    from agents.utility_based.execution_assistance.context_validator import apply_context_corrections
    registry, context_id, _, _ = setup(monkeypatch)
    context = confirmed(registry, context_id)
    manager, session, _ = fixture_session()
    session.context = context
    registry.reserve_launch(context); registry.finish_launch(context_id, True)
    manager._execute_stage_action_on_portal = AsyncMock(return_value=outcome("FAILED"))
    asyncio.run(request(manager, session))
    assert registry._records[context_id].execution_uncertain
    corrected = apply_context_corrections(session.context, {"pincode": "641025"})
    with pytest.raises(ReviewError): registry.begin_execution(corrected)


def test_missing_http_identity_rejected_before_manager(monkeypatch):
    monkeypatch.setenv("AADHAAR_RUNTIME_MODE", "demo")
    from fastapi.testclient import TestClient
    from unittest.mock import Mock, patch
    import api.app as ignored
    import importlib
    api = importlib.import_module("api.app")
    import agents.utility_based.execution_assistance.interactive_session as portal
    with patch.object(portal.interactive_manager, "submit_step", new_callable=AsyncMock) as submit:
        response = TestClient(api.create_app(document_service=Mock())).post("/api/browser/submit-step", json={"session_id":"synthetic", "user_consent":True})
        assert response.status_code == 422
        submit.assert_not_awaited()


def test_final_approval_concurrency_does_not_duplicate_dispatch():
    manager, session, _ = ready_session()
    review = asyncio.run(manager.review_submission(session.session_id))["final_review"]
    from agents.utility_based.execution_assistance.final_review import binding, submission_package
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def action(*args):
            entered.set(); await release.wait()
            return outcome("UNKNOWN")
        manager._execute_stage_action_on_portal = AsyncMock(side_effect=action)
        token = review["binding"]
        first = asyncio.create_task(manager.final_review_action(session.session_id, "Approve & Submit", token))
        await asyncio.wait_for(entered.wait(), 2)
        second = await manager.final_review_action(session.session_id, "Approve & Submit", token)
        assert second["execution_result"]["status"] == "BLOCKED"
        release.set(); await first
        manager._execute_stage_action_on_portal.assert_awaited_once()
    asyncio.run(scenario())


def test_invalid_correction_is_recorded_proven_rejection_before_reservation():
    manager, session, _ = fixture_session()
    manager._execute_stage_action_on_portal = AsyncMock(return_value=outcome("VERIFIED_SUCCESS"))
    async def scenario():
        response = await request(manager, session, "invalid", user_inputs={"pincode": "bad"})
        assert response["request_reserved"] is False and response["retry_permitted"] is True
        assert not session.attempts
        await request(manager, session, "fresh", user_inputs={"pincode": "641025"})
        assert session.context.facts["pincode"].value == "641025"
        manager._execute_stage_action_on_portal.assert_awaited_once()
    asyncio.run(scenario())


def test_verified_failure_evidence_never_automatically_authorizes_repeat():
    manager, session, _ = fixture_session()
    manager._execute_stage_action_on_portal = AsyncMock(return_value=ActionExecutionResult(status="FAILED", message="Observed failure", verification_evidence="Synthetic official rejection"))
    async def scenario():
        result = await request(manager, session)
        assert result["execution_result"]["verification_evidence"] == "Synthetic official rejection"
        assert result["execution_uncertain"]
        await request(manager, session, "fresh")
        manager._execute_stage_action_on_portal.assert_awaited_once()
    asyncio.run(scenario())


def test_correction_inside_final_request_invalidates_approval_before_dispatch():
    manager, session, _ = ready_session()
    approved(session)
    manager._execute_stage_action_on_portal = AsyncMock()
    result = asyncio.run(request(manager, session, "changed", user_inputs={"new_address": "Corrected synthetic address"}))
    assert result["execution_result"]["status"] == "BLOCKED"
    assert result["request_reserved"] is False
    assert session.execution_version == 1
    assert not session.attempts
    manager._execute_stage_action_on_portal.assert_not_awaited()
