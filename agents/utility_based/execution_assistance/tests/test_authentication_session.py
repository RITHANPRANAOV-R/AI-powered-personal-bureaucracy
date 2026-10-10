import asyncio
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from agents.utility_based.execution_assistance.interactive_session import (
    ActiveBrowserSession, InteractivePortalManager, PortalStage, AUTHENTICATED_DASHBOARD_TEXT,
)
from agents.utility_based.execution_assistance.schema import (
    ActionExecutionResult, ConfirmedExecutionContext, ExecutionOutcome,
)


class FakePage:
    def __init__(self, text="", otp_visible=False):
        self.url = "https://myaadhaar.uidai.gov.in/"
        self.closed = False
        self.text = text
        self.otp_visible = otp_visible
        self.uid_visible = False
        self.visible_labels = set()
        self.wait_for_timeout = AsyncMock()
        self.browser = SimpleNamespace(is_connected=lambda: True)
        self.context = SimpleNamespace(pages=[self], browser=self.browser)

    def is_closed(self):
        return self.closed

    def locator(self, selector):
        if selector == "body":
            return SimpleNamespace(inner_text=AsyncMock(return_value=self.text))
        if selector.startswith('input[name="uid"]'):
            return SimpleNamespace(count=AsyncMock(return_value=int(self.uid_visible)), nth=lambda _: SimpleNamespace(is_visible=AsyncMock(return_value=self.uid_visible)))
        return SimpleNamespace(first=SimpleNamespace(is_visible=AsyncMock(return_value=self.otp_visible)))

    def get_by_text(self, pattern):
        matched = any(pattern.fullmatch(label) for label in self.visible_labels)
        item = SimpleNamespace(is_visible=AsyncMock(return_value=matched))
        return SimpleNamespace(first=item, count=AsyncMock(return_value=int(matched)), nth=lambda _: item)


def fixture_session(text="", otp_visible=False):
    page = FakePage(text, otp_visible)
    manager = InteractivePortalManager()
    session = ActiveBrowserSession(session_id="auth-fixture", context=ConfirmedExecutionContext(session_id="auth-fixture"),
        current_stage=PortalStage.STAGE_1B_LOGIN, page=page, browser=page.browser)
    manager._sessions[session.session_id] = session
    manager._smart_click_or_submit = AsyncMock(return_value=True)
    return manager, session, page


def submit(manager, session, **kwargs):
    return asyncio.run(manager.submit_step(session.session_id, True, **kwargs))


def state(response):
    return response["execution_result"]["status"]


def test_otp_click_without_authentication_evidence_is_unknown():
    manager, session, page = fixture_session()
    response = submit(manager, session)
    manager._smart_click_or_submit.assert_awaited_once()
    assert state(response) == "UNKNOWN"
    assert session.current_stage == PortalStage.STAGE_1B_LOGIN
    assert session.authentication_page is page
    assert session.authentication_context is page.context
    assert response["execution_result"]["verification_evidence"] is None


@pytest.mark.parametrize("text,expected", [
    ("Invalid OTP", "FAILED"), ("Incorrect OTP", "FAILED"), ("OTP is invalid", "FAILED"),
    ("Authentication failed", "FAILED"), ("Authentication failure", "FAILED"),
    ("Expired OTP", "NEEDS_USER"), ("OTP has expired", "NEEDS_USER"),
])
def test_explicit_visible_otp_failure_does_not_advance(text, expected):
    manager, session, _ = fixture_session(text)
    response = submit(manager, session)
    assert state(response) == expected
    assert session.current_stage == PortalStage.STAGE_1B_LOGIN


def test_visible_otp_checkpoint_needs_user():
    manager, session, _ = fixture_session(otp_visible=True)
    assert state(submit(manager, session)) == "NEEDS_USER"


@pytest.mark.parametrize("missing", ["page", "context", "browser"])
def test_missing_browser_objects_prevent_click_and_completion(missing):
    manager, session, page = fixture_session()
    if missing == "page": session.page = None
    elif missing == "context": page.context = None
    else: session.browser = None
    assert state(submit(manager, session)) in {"BLOCKED", "NEEDS_USER"}
    manager._smart_click_or_submit.assert_not_awaited()
    assert session.current_stage == PortalStage.STAGE_1B_LOGIN


def test_closed_page_needs_user():
    manager, session, page = fixture_session()
    page.closed = True
    assert state(submit(manager, session)) == "NEEDS_USER"


def test_unknown_inspection_or_exception_is_sanitized():
    manager, session, page = fixture_session()
    secret = "synthetic-sensitive-fixture"
    page.locator = Mock(side_effect=RuntimeError(secret))
    response = submit(manager, session)
    assert state(response) == "UNKNOWN"
    assert secret not in str(response)


@pytest.mark.parametrize("url", ["https://myaadhaar.uidai.gov.in/dashboard", "https://example.invalid/dashboard", "http://myaadhaar.uidai.gov.in/dashboard"])
def test_navigation_alone_cannot_prove_authentication(url):
    manager, session, page = fixture_session()
    page.url = url
    assert state(submit(manager, session)) == "UNKNOWN"


def test_missing_session_is_not_reconstructed():
    manager = InteractivePortalManager()
    response = asyncio.run(manager.submit_step("lost", True))
    assert state(response) == "NEEDS_USER"
    assert "lost" not in manager._sessions


@pytest.mark.parametrize("replacement", ["page", "context", "session"])
def test_session_replaced_during_otp_wait_does_not_advance(replacement):
    manager, session, page = fixture_session()
    async def replace(_):
        if replacement == "page": session.page = FakePage()
        elif replacement == "context": page.context = SimpleNamespace(pages=[page], browser=page.browser)
        else: manager._sessions[session.session_id] = ActiveBrowserSession(session.session_id, session.context)
    page.wait_for_timeout.side_effect = replace
    response = submit(manager, session)
    assert state(response) == "NEEDS_USER"
    assert session.current_stage == PortalStage.STAGE_1B_LOGIN


def verified_fixture():
    # Fixture represents a future established signal, not a production UIDAI selector.
    return ActionExecutionResult(status="VERIFIED_SUCCESS", message="Fixture authentication verified", verification_evidence="Mock verifier observed authenticated account state on the bound page")


def test_verified_verifier_result_preserves_session_for_next_stage():
    manager, session, page = fixture_session()
    manager._verify_authentication = AsyncMock(return_value=verified_fixture())
    response = submit(manager, session)
    assert state(response) == "VERIFIED_SUCCESS"
    assert session.current_stage == PortalStage.STAGE_2_SERVICE
    assert session.page is page and session.authentication_context is page.context
    action = AsyncMock(return_value=ActionExecutionResult(status="UNKNOWN", message="Service outcome unverified"))
    manager._execute_stage_action_on_portal = action
    response = submit(manager, session)
    action.assert_awaited_once_with(session, PortalStage.STAGE_2_SERVICE)
    assert session.page is page
    assert state(response) == "UNKNOWN"


def test_next_stage_rechecks_authentication_in_same_session():
    manager, session, _ = fixture_session()
    manager._verify_authentication = AsyncMock(return_value=verified_fixture())
    submit(manager, session)
    manager._verify_authentication.return_value = ActionExecutionResult(status="UNKNOWN", message="Authentication no longer verified")
    manager._execute_stage_action_on_portal = AsyncMock()
    assert state(submit(manager, session)) == "UNKNOWN"
    manager._execute_stage_action_on_portal.assert_not_awaited()


def test_verified_fixture_cannot_override_lost_session():
    manager, session, _ = fixture_session()
    async def verification(_):
        session.page = FakePage()
        return verified_fixture()
    manager._verify_authentication = verification
    assert state(submit(manager, session)) == "NEEDS_USER"
    assert session.current_stage == PortalStage.STAGE_1B_LOGIN


def test_otp_never_enters_response_history_or_logs(caplog):
    secret = "synthetic-sensitive-fixture"
    manager, session, _ = fixture_session("Invalid OTP " + secret)
    response = submit(manager, session, user_inputs={"otp": secret, "aadhaar_otp": secret}, notes=secret)
    assert secret not in str(response)
    assert secret not in str(manager.get_session_status(session.session_id))
    assert secret not in caplog.text
    assert "otp" not in session.context.facts
    assert "aadhaar_otp" not in session.context.facts


def test_http_200_preserves_unverified_authentication_result():
    with patch("agents.orchestration.pipeline.create_production_orchestrator", return_value=Mock()), patch("agents.orchestration.document_input.AadhaarDocumentService", return_value=Mock()):
        api = importlib.import_module("api.app")
    import agents.utility_based.execution_assistance.interactive_session as portal
    manager, session, _ = fixture_session()
    old_id = session.session_id
    session.context, headers = bind_context(session.context, active=True)
    session.session_id = session.context.session_id
    manager._sessions.pop(old_id, None)
    manager._sessions[session.session_id] = session
    with patch.object(portal, "interactive_manager", manager):
        response = TestClient(api.create_app(document_service=Mock())).post("/api/browser/submit-step", json={"request_id": "fixture-attempt", "expected_stage": session.current_stage.value, "expected_state_version": session.execution_version, "session_id": session.session_id, "user_consent": True}, headers=headers)
    assert response.status_code == 200
    assert state(response.json()) == "UNKNOWN"
    assert session.current_stage == PortalStage.STAGE_1B_LOGIN


def test_disconnected_browser_requires_human_authentication():
    manager, session, page = fixture_session()
    page.browser.is_connected = lambda: False
    assert state(submit(manager, session)) == "NEEDS_USER"
    manager._smart_click_or_submit.assert_not_awaited()


def test_replaced_post_login_context_prevents_next_stage_action():
    manager, session, page = fixture_session()
    manager._verify_authentication = AsyncMock(return_value=verified_fixture())
    submit(manager, session)
    page.context = SimpleNamespace(pages=[page], browser=page.browser)
    manager._execute_stage_action_on_portal = AsyncMock()
    assert state(submit(manager, session)) == "NEEDS_USER"
    manager._execute_stage_action_on_portal.assert_not_awaited()


def test_documented_visible_dashboard_verifies_authentication():
    manager, session, page = fixture_session()
    page.visible_labels = set(AUTHENTICATED_DASHBOARD_TEXT)
    response = submit(manager, session)
    assert state(response) == "VERIFIED_SUCCESS"
    assert response["execution_result"]["verification_evidence"]
    assert session.current_stage == PortalStage.STAGE_2_SERVICE
    assert session.authentication_page is page
    assert session.authentication_context is page.context


@pytest.mark.parametrize("missing", AUTHENTICATED_DASHBOARD_TEXT)
def test_incomplete_dashboard_never_verifies(missing):
    manager, session, page = fixture_session()
    page.visible_labels = set(AUTHENTICATED_DASHBOARD_TEXT) - {missing}
    assert state(submit(manager, session)) == "UNKNOWN"
    assert session.current_stage == PortalStage.STAGE_1B_LOGIN


@pytest.mark.parametrize("control", ["otp", "uid"])
def test_login_controls_override_dashboard_text(control):
    manager, session, page = fixture_session()
    page.visible_labels = set(AUTHENTICATED_DASHBOARD_TEXT)
    if control == "otp": page.otp_visible = True
    else: page.uid_visible = True
    assert state(submit(manager, session)) == "NEEDS_USER"


def test_documented_dashboard_on_wrong_origin_cannot_verify():
    manager, session, page = fixture_session()
    page.visible_labels = set(AUTHENTICATED_DASHBOARD_TEXT)
    page.url = "https://tathya.uidai.gov.in/access/login?role=resident"
    assert state(submit(manager, session)) == "UNKNOWN"


def test_verified_real_verifier_preserves_context_and_blocks_expired_next_stage():
    manager, session, page = fixture_session()
    page.visible_labels = set(AUTHENTICATED_DASHBOARD_TEXT)
    assert state(submit(manager, session)) == "VERIFIED_SUCCESS"
    page.otp_visible = True
    manager._execute_stage_action_on_portal = AsyncMock()
    assert state(submit(manager, session)) == "NEEDS_USER"
    manager._execute_stage_action_on_portal.assert_not_awaited()
    assert session.page is page


@pytest.mark.parametrize("change", ["origin", "login"])
def test_dashboard_changing_during_inspection_cannot_verify(change):
    manager, session, page = fixture_session()
    page.visible_labels = set(AUTHENTICATED_DASHBOARD_TEXT)
    original = page.get_by_text
    calls = 0
    def inspect(pattern):
        nonlocal calls
        calls += 1
        if calls == len(AUTHENTICATED_DASHBOARD_TEXT):
            if change == "origin": page.url = "https://example.invalid/dashboard"
            else: page.otp_visible = True
        return original(pattern)
    page.get_by_text = inspect
    assert state(submit(manager, session)) in {"UNKNOWN", "NEEDS_USER"}
    assert session.current_stage == PortalStage.STAGE_1B_LOGIN

from agents.utility_based.execution_assistance.tests.review_fixtures import enroll, resolve_review, confirm_review, bind_context
