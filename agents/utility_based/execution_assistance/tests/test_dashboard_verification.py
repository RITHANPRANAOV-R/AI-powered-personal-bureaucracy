"""Read-only portal mocks; immediately completing awaits without Windows loop creation."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from agents.utility_based.execution_assistance.tests.test_authentication_session import fixture_session
from agents.utility_based.execution_assistance.tests.test_demo_recovery import immediate, request
from agents.utility_based.execution_assistance.interactive_session import AUTHENTICATED_DASHBOARD_TEXT, PortalStage


def dashboard(hidden_first=False, missing=None):
    manager,session,page=fixture_session()
    page.visible_labels=set(AUTHENTICATED_DASHBOARD_TEXT)-({missing} if missing else set())
    if hidden_first:
        def matches(pattern):
            items=[SimpleNamespace(is_visible=AsyncMock(return_value=False))]
            if any(pattern.fullmatch(label) for label in page.visible_labels):
                items.append(SimpleNamespace(is_visible=AsyncMock(return_value=True)))
            return SimpleNamespace(first=items[0],count=AsyncMock(return_value=len(items)),nth=lambda i:items[i])
        page.get_by_text=matches
    return manager,session,page


@pytest.mark.parametrize('hidden_first',[False,True])
def test_complete_dashboard_with_visible_matches_advances_once(hidden_first):
    manager,session,page=dashboard(hidden_first)
    result=immediate(request(manager,session))
    assert result['execution_result']['status']=='VERIFIED_SUCCESS'
    assert session.current_stage==PortalStage.STAGE_2_SERVICE
    assert session.authentication_page is page
    assert session.authentication_context is page.context
    assert immediate(request(manager,session,'attempt',PortalStage.STAGE_1B_LOGIN.value,0))['execution_result']['status']=='BLOCKED'
    assert manager._smart_click_or_submit.await_count==1


@pytest.mark.parametrize('label',['Lock / Unlock biometrics','Lock / Unlock\nbiometrics','Lock/Unlock biometrics','Lock  /  Unlock biometrics'])
def test_captured_dashboard_slash_spacing_is_recognized(label):
    manager,session,page=dashboard(True)
    page.visible_labels.remove('Lock/Unlock biometrics')
    page.visible_labels.add(label)
    result=immediate(request(manager,session))
    assert result['execution_result']['status']=='VERIFIED_SUCCESS'
    assert session.current_stage==PortalStage.STAGE_2_SERVICE


@pytest.mark.parametrize('label',['Lock biometrics','Unlock biometrics','Lock / Unlock account'])
def test_separator_normalization_does_not_accept_different_labels(label):
    manager,session,page=dashboard(True)
    page.visible_labels.remove('Lock/Unlock biometrics')
    page.visible_labels.add(label)
    result=immediate(request(manager,session))
    assert result['execution_result']['status']=='UNKNOWN'
    assert session.current_stage==PortalStage.STAGE_1B_LOGIN


@pytest.mark.parametrize('missing',AUTHENTICATED_DASHBOARD_TEXT)
def test_missing_or_hidden_evidence_identifies_exact_required_label(missing):
    manager,session,_=dashboard(True,missing)
    result=immediate(request(manager,session))
    assert result['execution_result']['status']=='UNKNOWN'
    assert missing in result['execution_result']['message']
    assert session.current_stage==PortalStage.STAGE_1B_LOGIN
    assert result['execution_uncertain']
    assert immediate(request(manager,session,'fresh'))['execution_result']['status']=='BLOCKED'


def test_otp_click_without_dashboard_remains_uncertain():
    manager,session,_=fixture_session()
    result=immediate(request(manager,session))
    assert result['execution_result']['status']=='UNKNOWN'
    assert session.current_stage==PortalStage.STAGE_1B_LOGIN
    assert result['execution_uncertain']


@pytest.mark.parametrize('text,status',[('Invalid OTP','FAILED'),('Authentication failed','FAILED'),('OTP has expired','NEEDS_USER')])
def test_portal_authentication_failure_remains_truthful_and_not_retryable(text,status):
    manager,session,_=fixture_session(text)
    result=immediate(request(manager,session))
    assert result['execution_result']['status']==status
    assert session.current_stage==PortalStage.STAGE_1B_LOGIN
    assert result['execution_uncertain']
    assert immediate(request(manager,session,'fresh'))['execution_result']['status']=='BLOCKED'


@pytest.mark.parametrize('change',['otp','origin','context'])
def test_positive_labels_cannot_override_checkpoint_or_session_loss(change):
    manager,session,page=dashboard(True)
    if change=='otp':page.otp_visible=True
    elif change=='origin':page.url='https://unrelated.example/'
    else:
        session.authentication_page=page
        session.authentication_context=page.context
        session.authentication_browser=page.browser
        page.context=SimpleNamespace(pages=[page],browser=page.browser)
    assert immediate(request(manager,session))['execution_result']['status']!='VERIFIED_SUCCESS'
    assert session.current_stage==PortalStage.STAGE_1B_LOGIN


@pytest.mark.parametrize("history", [False, True])
def test_documented_services_layout_does_not_require_transaction_history(history):
    manager, session, page = dashboard(True)
    # Independent documented fixture: do not derive this layout from the production checklist.
    page.visible_labels = {"myAadhaar", "Services", "Address update", "Download Aadhaar",
                           "Document update", "Bank seeding status", "Lock / Unlock biometrics"}
    if history:
        page.visible_labels.add("My transaction history")
    result = immediate(request(manager, session))
    assert result["execution_result"]["status"] == "VERIFIED_SUCCESS"
    assert session.current_stage == PortalStage.STAGE_2_SERVICE


def test_documented_services_layout_with_line_breaks_and_hidden_duplicates():
    manager, session, page = dashboard(True)
    page.visible_labels = {" myAadhaar ", " Services ", "Address\nupdate", "Download  Aadhaar",
                           "Document\nupdate", "Bank seeding\nstatus", "Lock / Unlock\nbiometrics"}
    assert immediate(request(manager, session))["execution_result"]["status"] == "VERIFIED_SUCCESS"


@pytest.mark.parametrize("labels", [{"myAadhaar"}, {"Services", "Document update"},
                                   {"My transaction history", "Payment history"}])
def test_generic_or_partial_dashboard_words_do_not_authorize_access(labels):
    manager, session, page = dashboard(True)
    page.visible_labels = labels
    result = immediate(request(manager, session))
    assert result["execution_result"]["status"] == "UNKNOWN"
    assert session.current_stage == PortalStage.STAGE_1B_LOGIN
    assert result["execution_uncertain"]


def test_services_layout_with_resident_login_checkpoint_is_not_authenticated():
    manager, session, page = dashboard(True)
    page.uid_visible = True
    assert immediate(request(manager, session))["execution_result"]["status"] == "NEEDS_USER"
    assert session.current_stage == PortalStage.STAGE_1B_LOGIN


def test_otp_active_path_marks_new_verification_and_status_read_is_retained(caplog):
    manager, session, page = dashboard(True)
    original = manager._verify_authentication
    manager._verify_authentication = AsyncMock(side_effect=original)
    with caplog.at_level("INFO"):
        result = immediate(request(manager, session))
    manager._verify_authentication.assert_awaited_once_with(session)
    assert result["execution_diagnostic"] == {
        "verifier_version": "services-dashboard-v2", "stage_verifier": "stage_1b_login", "result_origin": "new_attempt",
        "result_category": "VERIFIED_SUCCESS", "verifier_invoked": True,
        "page_reference": session._page_observation_reference,
        "attempt_reference": session.attempts["attempt"]["observation_reference"],
        "input_state_version": 0, "state_version": session.execution_version, "verification_check": None}
    retained = manager.get_session_status(session.session_id)
    assert retained["execution_diagnostic"]["result_origin"] == "retained"
    assert retained["execution_diagnostic"]["verifier_invoked"] is False
    assert "verifier=services-dashboard-v2 category=VERIFIED_SUCCESS origin=new_verification" in caplog.text
    assert session.session_id not in caplog.text
    assert page.url not in caplog.text


def test_new_unknown_diagnostic_does_not_remove_uncertainty_or_allow_retry():
    manager, session, page = dashboard(True, "Services")
    result = immediate(request(manager, session))
    assert result["execution_diagnostic"]["result_category"] == "UNKNOWN"
    assert result["execution_diagnostic"]["verifier_invoked"] is True
    assert result["execution_uncertain"] is True
    assert "My transaction history" not in result["execution_result"]["message"]
    assert immediate(request(manager, session, "another"))["execution_result"]["status"] == "BLOCKED"
    assert manager._smart_click_or_submit.await_count == 1
