"""Final review safety: synthetic data and mocked browser objects only."""
import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from agents.utility_based.execution_assistance.final_review import (
    FinalReviewGate, ReviewState, binding, blocking_reasons, submission_package,
)
from agents.utility_based.execution_assistance.interactive_session import PortalStage, AUTHENTICATED_DASHBOARD_TEXT
from agents.utility_based.execution_assistance.schema import ConfirmedFact, ActionExecutionResult
from agents.utility_based.execution_assistance.tests.test_authentication_session import fixture_session


def ready_session():
    manager, session, page = fixture_session()
    session.current_stage = PortalStage.STAGE_5_REVIEW
    session.authentication_page = page
    session.authentication_context = page.context
    session.authentication_browser = page.browser
    page.visible_labels = set(AUTHENTICATED_DASHBOARD_TEXT)
    page.query_selector_all = AsyncMock(return_value=[])
    values = {
        "name": "Synthetic Citizen", "existing_address": "Synthetic old address",
        "new_address": "Synthetic corrected address", "pincode": "110001",
        "document_type": "synthetic proof", "fees": {"amount": 0, "currency": "INR", "source": "synthetic fee evidence"},
        "requirements": [{"description": "Synthetic requirement", "grounding_status": "verified_grounded",
                          "evidence_ids": ["synthetic-evidence"], "source_url": "https://example.invalid/synthetic"}],
        "declarations": [{"statement": "Synthetic declaration", "agreed": True}],
        "warnings": ["Synthetic fixture only"],
        "document_evidence": {"page": 1, "text": "Synthetic extracted text", "source_document_id": "synthetic-document"},
    }
    session.context.facts = {key: ConfirmedFact(value=value, provenance="user_corrected" if key == "new_address" else "synthetic-confirmed",
                                status="confirmed", allowed_for_execution=True) for key, value in values.items()}
    session.context.document_refs = ["synthetic-document"]
    # No production signal is invented: these are explicitly synthetic prerequisites.
    session.supporting_document_result = ActionExecutionResult(status="VERIFIED_SUCCESS", message="Synthetic upload",
                                                               verification_evidence="Synthetic verified upload")
    session.submission_validation = {"status": "VERIFIED_SUCCESS", "verification_evidence": "Synthetic validated exact form"}
    return manager, session, page


def approved(session):
    package = submission_package(session)
    review = session.final_review.view(package)
    assert review["state"] == "REVIEW_READY"
    assert session.final_review.approve(package, review["binding"], "Approve & Submit") is None
    return package


def run(coro):
    return asyncio.run(coro)


def test_complete_review_represents_data_provenance_and_warnings_without_approval():
    manager, session, page = ready_session()
    review = run(manager.review_submission(session.session_id))["final_review"]
    package = review["package"]
    assert set(package) == {"service", "citizen_information", "extracted_document_information", "corrected_information",
        "current_values", "new_values", "address", "pincode", "supporting_documents", "document_type",
        "requirements", "fees", "declarations", "upload_validation", "submission_validation", "warnings"}
    assert package["citizen_information"]["name"]["value"] == "Synthetic Citizen"
    assert package["corrected_information"]["new_address"]["provenance"] == "user_corrected"
    assert package["extracted_document_information"]["source_document_id"] == "synthetic-document"
    assert package["warnings"] == ["Synthetic fixture only"]
    assert review["binding"] == binding(package)
    assert review["approved_binding"] is None
    manager._smart_click_or_submit.assert_not_awaited()
    assert run(manager._validate_final_submission(session)).status.value == "BLOCKED"


def test_explicit_approval_binds_exact_package_and_is_not_client_context_state():
    _, session, _ = ready_session()
    package = approved(session)
    assert session.final_review.state == ReviewState.APPROVED
    assert session.final_review.approved_binding == binding(package)
    assert session.final_review.validate(package) is None
    assert session.final_review.expires_at - session.final_review.approved_at == timedelta(minutes=15)


@pytest.mark.parametrize("action", ["Next", "Review", "success", "", "Approve"])
def test_implicit_actions_never_approve(action):
    _, session, _ = ready_session()
    package = submission_package(session)
    review = session.final_review.view(package)
    assert session.final_review.approve(package, review["binding"], action)
    assert session.final_review.approved_binding is None


@pytest.mark.parametrize("field", ["name", "new_address", "pincode", "document_type", "requirements", "declarations", "fees", "document_evidence", "existing_address"])
def test_each_submission_relevant_fact_change_invalidates(field):
    _, session, _ = ready_session()
    approved(session)
    session.context.facts[field].value = "Changed synthetic value"
    assert session.final_review.validate(submission_package(session))
    assert session.final_review.state == ReviewState.APPROVAL_INVALIDATED
    assert session.final_review.approved_binding is None


@pytest.mark.parametrize("change", ["document", "upload", "validation"])
def test_document_and_validation_changes_invalidate(change):
    _, session, _ = ready_session()
    approved(session)
    if change == "document": session.context.document_refs = ["different-document"]
    elif change == "upload": session.supporting_document_result = None
    else: session.submission_validation["status"] = "FAILED"
    assert session.final_review.validate(submission_package(session))
    assert session.final_review.state == ReviewState.APPROVAL_INVALIDATED


def test_changed_review_requires_review_again_and_explicit_reapproval():
    _, session, _ = ready_session()
    approved(session)
    session.context.facts["new_address"].value = "Different corrected address"
    package = submission_package(session)
    first = session.final_review.view(package)
    assert first["state"] == "APPROVAL_INVALIDATED"
    assert session.final_review.approve(package, first["binding"], "Approve & Submit")
    review = session.final_review.view(package)
    assert review["state"] == "REVIEW_READY"
    assert session.final_review.approve(package, review["binding"], "Approve & Submit") is None


@pytest.mark.parametrize("field", ["service", "address", "pincode", "supporting_documents", "document_type", "requirements", "fees", "declarations"])
def test_required_unknown_blocks_approval(field):
    _, session, _ = ready_session()
    package = submission_package(session)
    package[field] = "UNKNOWN"
    gate = FinalReviewGate()
    review = gate.view(package)
    assert review["state"] == "REVIEW_REQUIRED"
    assert review["package"][field] == "UNKNOWN"
    assert field in review["unknown_fields"]
    assert gate.approve(package, review["binding"], "Approve & Submit")


@pytest.mark.parametrize("field", ["upload_validation", "submission_validation"])
@pytest.mark.parametrize("status", ["UNKNOWN", "FAILED", "BLOCKED", "NEEDS_USER"])
def test_failed_or_unknown_validation_blocks(field, status):
    _, session, _ = ready_session()
    package = submission_package(session)
    package[field]["status"] = status
    assert blocking_reasons(package)
    assert FinalReviewGate().view(package)["state"] == "REVIEW_REQUIRED"


@pytest.mark.parametrize("field", ["requirements", "declarations"])
def test_arbitrary_strings_cannot_replace_grounding_or_agreement(field):
    _, session, _ = ready_session()
    package = submission_package(session)
    package[field] = "claimed verified"
    assert blocking_reasons(package)


def test_optional_unknown_stays_visible_without_blocking():
    _, session, _ = ready_session()
    package = submission_package(session)
    package["current_values"] = "UNKNOWN"
    package["warnings"] = "UNKNOWN"
    review = FinalReviewGate().view(package)
    assert review["state"] == "REVIEW_READY"
    assert {"current_values", "warnings"}.issubset(review["unknown_fields"])


def test_missing_review_stale_binding_and_expired_approval():
    _, session, _ = ready_session()
    package = submission_package(session)
    assert session.final_review.approve(package, binding(package), "Approve & Submit")
    assert session.final_review.validate(package)
    review = session.final_review.view(package)
    assert session.final_review.approve(package, "stale-binding", "Approve & Submit")
    assert session.final_review.state == ReviewState.APPROVAL_INVALIDATED
    session.final_review.view(package)
    assert session.final_review.approve(package, review["binding"], "Approve & Submit") is None
    assert session.final_review.validate(package, now=session.final_review.expires_at)
    assert session.final_review.state == ReviewState.APPROVAL_INVALIDATED


@pytest.mark.parametrize("case", ["missing-review", "missing-approval", "changed", "expired", "forged-context", "bad-binding", "wrong-stage", "lost-session", "lost-page", "login-returned"])
def test_real_final_action_independently_blocks_without_valid_approval_and_session(case):
    manager, session, page = ready_session()
    if case != "missing-review": session.final_review.view(submission_package(session))
    if case not in {"missing-review", "missing-approval", "forged-context"}: approved(session)
    if case == "changed": session.context.facts["pincode"].value = "560001"
    elif case == "expired": session.final_review.expires_at = session.final_review.approved_at
    elif case == "forged-context": session.context.facts["final_approval"] = ConfirmedFact(value=True, provenance="client", status="confirmed", allowed_for_execution=True)
    elif case == "bad-binding": session.final_review.approved_binding = "tampered"
    elif case == "wrong-stage": session.current_stage = PortalStage.STAGE_4_DOCUMENT
    elif case == "lost-session": manager._sessions.pop(session.session_id)
    elif case == "lost-page": session.authentication_page = None
    elif case == "login-returned": page.otp_visible = True
    result = run(manager._execute_stage_action_on_portal(session, PortalStage.STAGE_5_REVIEW))
    assert result.status.value in {"BLOCKED", "NEEDS_USER"}
    manager._smart_click_or_submit.assert_not_awaited()
    assert result.official_reference is None


def test_positive_real_action_permitted_once_but_click_never_fabricates_success():
    manager, session, page = ready_session()
    original_urn = session.urn
    review = run(manager.review_submission(session.session_id))["final_review"]
    response = run(manager.final_review_action(session.session_id, "Approve & Submit", review["binding"]))
    manager._smart_click_or_submit.assert_awaited_once()
    assert response["execution_result"]["status"] == "UNKNOWN"
    assert not response["is_completed"]
    assert session.current_stage == PortalStage.STAGE_5_REVIEW
    assert session.urn == original_urn
    assert session.final_review.state == ReviewState.APPROVAL_INVALIDATED
    response = run(manager.submit_step(session.session_id, True))
    assert response["execution_result"]["status"] == "BLOCKED"
    manager._smart_click_or_submit.assert_awaited_once()


@pytest.mark.parametrize("action", ["Edit / Correct", "Cancel"])
def test_edit_and_cancel_invalidate_without_submission(action):
    manager, session, _ = ready_session()
    approved(session)
    result = run(manager.final_review_action(session.session_id, action))
    assert result["execution_result"]["status"] == "NEEDS_USER"
    assert session.final_review.state == ReviewState.APPROVAL_INVALIDATED
    manager._smart_click_or_submit.assert_not_awaited()


def test_unchecked_declaration_never_silently_agreed_or_submitted():
    manager, session, page = ready_session()
    approved(session)
    checkbox = Mock(is_checked=AsyncMock(return_value=False), check=AsyncMock())
    page.query_selector_all.return_value = [checkbox]
    result = run(manager._execute_stage_action_on_portal(session, PortalStage.STAGE_5_REVIEW))
    assert result.status.value == "NEEDS_USER"
    checkbox.check.assert_not_awaited()
    manager._smart_click_or_submit.assert_not_awaited()
    assert session.final_review.state == ReviewState.APPROVAL_INVALIDATED


def test_changed_package_during_authentication_is_rechecked_before_click():
    manager, session, _ = ready_session()
    approved(session)
    original = manager._verify_authentication
    async def changed(bound_session):
        result = await original(bound_session)
        bound_session.context.facts["new_address"].value = "Changed during inspection"
        return result
    manager._verify_authentication = changed
    result = run(manager._execute_stage_action_on_portal(session, PortalStage.STAGE_5_REVIEW))
    assert result.status.value == "BLOCKED"
    manager._smart_click_or_submit.assert_not_awaited()


def test_phase6_unknown_remains_unknown_in_review_and_cannot_be_approved():
    manager, session, _ = ready_session()
    session.supporting_document_result = None
    session.submission_validation = None
    review = run(manager.review_submission(session.session_id))["final_review"]
    assert review["package"]["upload_validation"] == "UNKNOWN"
    assert review["package"]["submission_validation"] == "UNKNOWN"
    response = run(manager.final_review_action(session.session_id, "Approve & Submit", review["binding"]))
    assert response["execution_result"]["status"] == "BLOCKED"
    manager._smart_click_or_submit.assert_not_awaited()


def test_review_http_routes_are_separate_from_generic_consent_and_preserve_blocking():
    from fastapi.testclient import TestClient
    import agents.utility_based.execution_assistance.interactive_session as portal
    with patch("agents.orchestration.pipeline.create_production_orchestrator", return_value=Mock()), patch("agents.orchestration.document_input.AadhaarDocumentService", return_value=Mock()):
        api = __import__("api.app", fromlist=["create_app"])
    manager, session, _ = ready_session()
    old_id = session.session_id
    session.context, headers = bind_context(session.context, active=True)
    session.session_id = session.context.session_id
    manager._sessions.pop(old_id, None)
    manager._sessions[session.session_id] = session
    with patch.object(portal, "interactive_manager", manager):
        client = TestClient(api.create_app(document_service=Mock()))
        review = client.get(f"/api/browser/final-review/{session.session_id}", headers=headers).json()["final_review"]
        manager._smart_click_or_submit.assert_not_awaited()
        response = client.post("/api/browser/submit-step", json={"request_id": "fixture-attempt", "expected_stage": session.current_stage.value, "expected_state_version": session.execution_version, "session_id": session.session_id, "user_consent": True}, headers=headers)
        assert response.json()["execution_result"]["status"] == "BLOCKED"
        response = client.post(f"/api/browser/final-review/{session.session_id}", json={"action": "Next", "binding": review["binding"]}, headers=headers)
        assert response.status_code == 200
        assert response.json()["execution_result"]["status"] == "BLOCKED"
        manager._smart_click_or_submit.assert_not_awaited()
        response = client.post(f"/api/browser/final-review/{session.session_id}", json={"action": "Approve & Submit", "binding": review["binding"]}, headers=headers)
        assert response.json()["execution_result"]["status"] == "UNKNOWN"
        manager._smart_click_or_submit.assert_awaited_once()


def test_data_changing_during_declaration_inspection_blocks_before_click():
    manager, session, page = ready_session()
    approved(session)
    async def inspect():
        session.context.facts["new_address"].value = "Changed while checking portal declarations"
        return True
    page.query_selector_all.return_value = [Mock(is_checked=inspect)]
    result = run(manager._execute_stage_action_on_portal(session, PortalStage.STAGE_5_REVIEW))
    assert result.status.value == "BLOCKED"
    manager._smart_click_or_submit.assert_not_awaited()


def test_declaration_inspection_error_fails_closed():
    manager, session, page = ready_session()
    approved(session)
    page.query_selector_all.side_effect = RuntimeError("synthetic error")
    result = run(manager._execute_stage_action_on_portal(session, PortalStage.STAGE_5_REVIEW))
    assert result.status.value == "UNKNOWN"
    assert session.final_review.state == ReviewState.APPROVAL_INVALIDATED
    manager._smart_click_or_submit.assert_not_awaited()


def test_executable_citizen_information_cannot_silently_contain_unknown():
    _, session, _ = ready_session()
    session.context.facts["name"].value = "UNKNOWN"
    review = session.final_review.view(submission_package(session))
    assert review["state"] == "REVIEW_REQUIRED"
    assert any("name" in reason for reason in review["blocking_reasons"])


def test_concurrent_explicit_approvals_permit_only_one_attempt():
    manager, session, _ = ready_session()
    review = run(manager.review_submission(session.session_id))["final_review"]
    async def attempts():
        return await asyncio.gather(*[manager.final_review_action(session.session_id, "Approve & Submit", review["binding"]) for _ in range(2)])
    responses = run(attempts())
    assert {response["execution_result"]["status"] for response in responses} == {"UNKNOWN", "BLOCKED"}
    manager._smart_click_or_submit.assert_awaited_once()

from agents.utility_based.execution_assistance.tests.review_fixtures import enroll, resolve_review, confirm_review, bind_context
