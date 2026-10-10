"""Document-stage safety until actual UIDAI upload signals are documented."""
import asyncio
from unittest.mock import AsyncMock, Mock, patch
import pytest
from agents.utility_based.execution_assistance.interactive_session import InteractivePortalManager, PortalStage
from agents.utility_based.execution_assistance.schema import ActionExecutionResult, ExecutionOutcome
from agents.utility_based.execution_assistance.tests.test_authentication_session import fixture_session


def manager_for_document():
    manager, session, page = fixture_session()
    session.current_stage = PortalStage.STAGE_4_DOCUMENT
    session.authentication_page = page
    session.authentication_context = page.context
    session.authentication_browser = page.browser
    return manager, session, page


def submit(manager, session):
    return asyncio.run(manager.submit_step(session.session_id, user_consent=True))


def test_real_document_handler_has_no_guessed_acceptance_or_progression_click():
    manager, session, page = manager_for_document()
    # Only prerequisite authentication is stubbed; the document handler is real.
    manager._verify_authentication = AsyncMock(return_value=ActionExecutionResult(
        status="VERIFIED_SUCCESS", message="Synthetic authenticated session", verification_evidence="Synthetic prerequisite"))
    manager._smart_click_or_submit = AsyncMock()
    result = submit(manager, session)
    assert result["execution_result"]["status"] == "UNKNOWN"
    assert result["execution_result"]["official_reference"] is None
    assert result["execution_result"]["verification_evidence"] is None
    assert session.current_stage == PortalStage.STAGE_4_DOCUMENT
    manager._smart_click_or_submit.assert_not_awaited()


@pytest.mark.parametrize("state", ["UNKNOWN", "FAILED", "NEEDS_USER", "BLOCKED"])
def test_authentication_non_success_never_advances_document_stage(state):
    manager, session, _ = manager_for_document()
    manager._verify_authentication = AsyncMock(return_value=ActionExecutionResult(status=state, message="Synthetic prerequisite result"))
    result = submit(manager, session)
    assert result["execution_result"]["status"] == state
    assert session.current_stage == PortalStage.STAGE_4_DOCUMENT


def test_missing_page_is_blocked():
    manager, session, _ = manager_for_document()
    session.page = None
    assert submit(manager, session)["execution_result"]["status"] == "BLOCKED"
    assert session.current_stage == PortalStage.STAGE_4_DOCUMENT


def test_lost_session_does_not_reconstruct_browser():
    manager, session, _ = manager_for_document()
    manager._sessions.clear()
    manager._launch_and_navigate_login = AsyncMock()
    result = submit(manager, session)
    assert result["execution_result"]["status"] == "NEEDS_USER"
    manager._launch_and_navigate_login.assert_not_awaited()


def test_actual_authentication_check_rejects_unverified_page():
    manager, session, _ = manager_for_document()
    result = submit(manager, session)
    assert result["execution_result"]["status"] != "VERIFIED_SUCCESS"
    assert session.current_stage == PortalStage.STAGE_4_DOCUMENT


def test_local_reference_and_claimed_acceptance_cannot_verify_upload():
    manager, session, _ = manager_for_document()
    session.context.document_refs = ["synthetic-local-reference"]
    manager._verify_authentication = AsyncMock(return_value=ActionExecutionResult(
        status="VERIFIED_SUCCESS", message="Synthetic prerequisite", verification_evidence="Synthetic authentication"))
    result = asyncio.run(manager.submit_step(session.session_id, user_consent=True,
        user_inputs={"document_accepted": "true", "requirement_status": "accepted"}))
    assert result["execution_result"]["status"] == "UNKNOWN"
    assert session.current_stage == PortalStage.STAGE_4_DOCUMENT


@pytest.mark.parametrize("text,expected", [("Unsupported file type", "FAILED"),
    ("Invalid document", "FAILED"), ("Upload failed", "FAILED"),
    ("Validation error", "FAILED"), ("File rejected", "FAILED"),
    ("Required document missing", "NEEDS_USER"),
    ("Upload successful", "UNKNOWN"), ("Document accepted", "UNKNOWN")])
def test_visible_errors_are_distinct_from_unestablished_positive_signals(text, expected):
    manager, session, page = manager_for_document()
    page.text = text
    manager._verify_authentication = AsyncMock(return_value=ActionExecutionResult(
        status="VERIFIED_SUCCESS", message="Synthetic prerequisite", verification_evidence="Synthetic authentication"))
    result = submit(manager, session)
    assert result["execution_result"]["status"] == expected
    assert session.current_stage == PortalStage.STAGE_4_DOCUMENT
    assert result["execution_result"]["official_reference"] is None


def test_document_stage_requires_prior_authentication_binding():
    manager, session, _ = manager_for_document()
    session.authentication_page = None
    result = submit(manager, session)
    assert result["execution_result"]["status"] == "NEEDS_USER"
    assert session.current_stage == PortalStage.STAGE_4_DOCUMENT


def test_http_200_preserves_unverified_document_result():
    import agents.utility_based.execution_assistance.interactive_session as portal
    from fastapi.testclient import TestClient
    manager, session, _ = manager_for_document()
    old_id = session.session_id
    session.context, headers = bind_context(session.context, active=True)
    session.session_id = session.context.session_id
    manager._sessions.pop(old_id, None)
    manager._sessions[session.session_id] = session
    manager._verify_authentication = AsyncMock(return_value=ActionExecutionResult(
        status="VERIFIED_SUCCESS", message="Synthetic prerequisite", verification_evidence="Synthetic authentication"))
    with patch("agents.orchestration.pipeline.create_production_orchestrator", return_value=Mock()), patch("agents.orchestration.document_input.AadhaarDocumentService", return_value=Mock()):
        api = __import__("api.app", fromlist=["create_app"])
    with patch.object(portal, "interactive_manager", manager):
        response = TestClient(api.create_app(document_service=Mock())).post("/api/browser/submit-step", json={"request_id": "fixture-attempt", "expected_stage": session.current_stage.value, "expected_state_version": session.execution_version, "session_id": session.session_id, "user_consent": True}, headers=headers)
    assert response.status_code == 200
    assert response.json()["execution_result"]["status"] == "UNKNOWN"
    assert session.current_stage == PortalStage.STAGE_4_DOCUMENT

from agents.utility_based.execution_assistance.tests.review_fixtures import enroll, resolve_review, confirm_review, bind_context
