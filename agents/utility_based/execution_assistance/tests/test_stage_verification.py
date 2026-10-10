"""Actual manager/handlers with immediate portal mocks; no Windows event loop or live actions."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from agents.utility_based.execution_assistance.tests.test_dashboard_verification import dashboard
from agents.utility_based.execution_assistance.tests.test_demo_recovery import immediate, request
from agents.utility_based.execution_assistance.interactive_session import PortalStage, ADDRESS_REVIEW_CONTROLS, DOCUMENT_PAGE_TEXT
from agents.utility_based.execution_assistance.schema import ConfirmedFact, ActionExecutionResult


def service(stage=PortalStage.STAGE_2_SERVICE):
    manager, session, page = dashboard(True)
    session.current_stage = stage
    session.authentication_page = page
    session.authentication_context = page.context
    session.authentication_browser = page.browser
    page.evaluate = AsyncMock(return_value=True)
    old_locator = page.locator
    values = {"pincode": "641025", "house": "123", "street": "Example Street", "care_of": "Citizen"}
    controls = {}
    for field, selector in ADDRESS_REVIEW_CONTROLS.items():
        hidden = SimpleNamespace(is_visible=AsyncMock(return_value=False))
        visible = SimpleNamespace(is_visible=AsyncMock(return_value=True), is_enabled=AsyncMock(return_value=True),
                                  input_value=AsyncMock(return_value=values.get(field, "")))
        items = [hidden, visible]
        controls[field] = items
    def locator(selector):
        for field, known in ADDRESS_REVIEW_CONTROLS.items():
            if selector == known:
                items = controls[field]
                return SimpleNamespace(count=AsyncMock(side_effect=lambda: len(items)), nth=lambda i: items[i])
        return old_locator(selector)
    page.locator = locator
    return manager, session, page, controls


def test_navigation_observed_form_advances_once_and_replay_is_blocked():
    manager, session, page, _ = service()
    result = immediate(request(manager, session))
    assert result["execution_result"]["status"] == "VERIFIED_SUCCESS"
    assert result["completed_stage"] == "stage_2_service"
    assert session.current_stage == PortalStage.STAGE_3_ADDRESS
    assert result["execution_diagnostic"]["stage_verifier"] == "stage_2_service"
    calls = page.evaluate.await_count
    assert immediate(request(manager, session, "attempt", "stage_2_service", 0))["execution_result"]["status"] == "BLOCKED"
    assert page.evaluate.await_count == calls


@pytest.mark.parametrize("missing", ["pincode", "house", "street", "vtc", "post_office"])
def test_click_without_complete_destination_remains_unknown_and_not_retryable(missing):
    manager, session, page, controls = service()
    controls[missing].clear()
    result = immediate(request(manager, session))
    assert result["execution_result"]["status"] == "UNKNOWN"
    assert missing in result["execution_result"]["message"]
    assert result["execution_uncertain"]
    assert session.current_stage == PortalStage.STAGE_2_SERVICE
    assert immediate(request(manager, session, "new"))["execution_result"]["status"] == "BLOCKED"


@pytest.mark.parametrize("change", ["origin", "login", "context", "duplicate"])
def test_destination_controls_cannot_override_security_or_ambiguity(change):
    manager, session, page, controls = service()
    if change == "origin": page.url = "https://unrelated.example/"
    elif change == "login": page.otp_visible = True
    elif change == "context": page.context = SimpleNamespace(pages=[page], browser=page.browser)
    else: controls["pincode"].append(controls["pincode"][-1])
    assert immediate(manager._verify_address_destination(session)).status.value != "VERIFIED_SUCCESS"


def address():
    manager, session, page, controls = service(PortalStage.STAGE_3_ADDRESS)
    values = {"pincode": "641025", "house": "123", "street": "Example Street", "care_of": "Citizen"}
    session.context.facts = {key: ConfirmedFact(value=value, provenance="citizen", status="confirmed", allowed_for_execution=True)
                             for key, value in values.items()}
    manager._smart_fill = AsyncMock()
    manager._select_dropdown_option = AsyncMock(return_value={"status": "selected"})
    manager._validate_address_stage = AsyncMock(return_value={"pin_valid": True, "vtc_selected": True, "po_selected": True})
    page.visible_labels.update(DOCUMENT_PAGE_TEXT)
    return manager, session, page, controls


def test_address_readback_and_document_arrival_advance_with_exact_pin():
    manager, session, _, _ = address()
    result = immediate(request(manager, session))
    assert result["execution_result"]["status"] == "VERIFIED_SUCCESS"
    assert session.current_stage == PortalStage.STAGE_4_DOCUMENT
    calls = [call for call in manager._smart_fill.await_args_list if 'input[name*="pincode" i]' in call.args[1]]
    assert len(calls) == 1 and calls[0].args[2] == "641025"


def test_observed_pin_mismatch_reports_failure_without_next():
    manager, session, _, controls = address()
    controls["pincode"][-1].input_value.return_value = "638106"
    result = immediate(request(manager, session))
    assert result["execution_result"]["status"] == "FAILED"
    assert result["execution_result"]["verification_evidence"]
    manager._smart_click_or_submit.assert_not_awaited()
    assert session.current_stage == PortalStage.STAGE_3_ADDRESS
    assert result["execution_uncertain"]


def test_incomplete_address_is_pending_not_success():
    manager, session, _, _ = address()
    manager._validate_address_stage.return_value = {"pin_valid": False}
    result = immediate(request(manager, session))
    assert result["execution_result"]["status"] == "NEEDS_USER"
    manager._smart_click_or_submit.assert_not_awaited()


def test_next_click_without_document_destination_does_not_complete_address():
    manager, session, page, _ = address()
    page.visible_labels.clear()
    result = immediate(request(manager, session))
    assert result["execution_result"]["status"] == "UNKNOWN"
    assert result["execution_uncertain"]
    assert session.current_stage == PortalStage.STAGE_3_ADDRESS


@pytest.mark.parametrize("text,status", [("Upload failed", "FAILED"), ("Required document missing", "NEEDS_USER"),
                                         ("Upload successful", "UNKNOWN"), ("Document accepted", "UNKNOWN"), ("", "UNKNOWN")])
def test_document_stage_does_not_invent_acceptance(text, status):
    manager, session, page, _ = service(PortalStage.STAGE_4_DOCUMENT)
    page.text = text
    page.locator("body").inner_text.return_value = text
    # Only authentication prerequisite is substituted; actual upload handler remains unchanged.
    manager._verify_authentication = AsyncMock(return_value=ActionExecutionResult(status="VERIFIED_SUCCESS", message="Fixture", verification_evidence="Fixture"))
    result = immediate(request(manager, session))
    assert result["execution_result"]["status"] == status
    assert session.current_stage == PortalStage.STAGE_4_DOCUMENT
    manager._smart_click_or_submit.assert_not_awaited()


def test_retained_result_identifies_producing_stage_not_current_stage():
    manager, session, _, _ = service()
    immediate(request(manager, session))
    retained = manager.get_session_status(session.session_id)
    assert retained["current_stage"] == "stage_3_address"
    assert retained["execution_diagnostic"]["result_origin"] == "retained"
    assert retained["execution_diagnostic"]["stage_verifier"] == "stage_2_service"


def test_exception_is_unknown_not_an_observed_portal_failure():
    manager, session, _, _ = service()
    manager._execute_stage_action_on_portal = AsyncMock(side_effect=RuntimeError("synthetic"))
    result = immediate(request(manager, session))
    assert result["execution_result"]["status"] == "UNKNOWN"
    assert result["execution_uncertain"]
    assert immediate(request(manager, session, "retry"))["execution_result"]["status"] == "BLOCKED"


@pytest.mark.parametrize("text,status", [("", "UNKNOWN"), ("Processing", "UNKNOWN"),
    ("Upload successful", "UNKNOWN"), ("Document accepted", "UNKNOWN"),
    ("Upload failed", "FAILED"), ("Required document missing", "NEEDS_USER")])
def test_actual_document_page_replaces_dashboard_but_never_proves_acceptance(text, status):
    manager, session, page, _ = service(PortalStage.STAGE_4_DOCUMENT)
    page.visible_labels = set(DOCUMENT_PAGE_TEXT)
    page.text = text
    result = immediate(request(manager, session))
    assert result["execution_result"]["status"] == status
    assert session.current_stage == PortalStage.STAGE_4_DOCUMENT
    assert session.supporting_document_result is None
    manager._smart_click_or_submit.assert_not_awaited()
    if status == "UNKNOWN":
        assert "acceptance is UNKNOWN" in result["execution_result"]["message"]
        assert result["execution_uncertain"]
        assert immediate(request(manager, session, "retry"))["execution_result"]["status"] == "BLOCKED"


def test_upload_status_read_failure_stays_unknown():
    manager, session, page, _ = service(PortalStage.STAGE_4_DOCUMENT)
    manager._verify_authentication = AsyncMock(return_value=ActionExecutionResult(
        status="VERIFIED_SUCCESS", message="Fixture", verification_evidence="Fixture"))
    old_locator = page.locator
    page.locator = lambda selector: SimpleNamespace(inner_text=AsyncMock(side_effect=TimeoutError())) if selector == "body" else old_locator(selector)
    result = immediate(request(manager, session))
    assert result["execution_result"]["status"] == "UNKNOWN"
    assert "timed out or failed" in result["execution_result"]["message"]
    assert session.supporting_document_result is None
    manager._smart_click_or_submit.assert_not_awaited()


OBSERVED_ADDRESS_LABELS = {"Update Aadhaar Online", "Current Details", "Details to be Updated"}


def test_observed_destination_advances_without_house_readiness_and_blocks_replay():
    manager, session, page, controls = service()
    # Navigation handler remains the real handler; model its final URL transition.
    async def navigate(*args):
        page.url = "https://myaadhaar.uidai.gov.in/ssup/demoUpdate/update/en_IN"
        page.visible_labels.update(OBSERVED_ADDRESS_LABELS)
        return True
    page.evaluate.side_effect = navigate
    controls["house"].clear()
    result = immediate(request(manager, session))
    assert result["execution_result"]["status"] == "VERIFIED_SUCCESS"
    assert result["completed_stage"] == "stage_2_service"
    assert session.current_stage == PortalStage.STAGE_3_ADDRESS
    calls = page.evaluate.await_count
    assert immediate(request(manager, session, "attempt", "stage_2_service", 0))["execution_result"]["status"] == "BLOCKED"
    assert page.evaluate.await_count == calls
    assert immediate(manager._verify_address_form_ready(session)).status.value == "UNKNOWN"


@pytest.mark.parametrize("missing", sorted(OBSERVED_ADDRESS_LABELS))
def test_observed_path_with_incomplete_destination_stays_unknown(missing):
    manager, session, page, _ = service()
    page.url = "https://myaadhaar.uidai.gov.in/ssup/demoUpdate/update/en_IN"
    page.visible_labels.update(OBSERVED_ADDRESS_LABELS - {missing})
    assert immediate(manager._verify_address_destination(session)).status.value == "UNKNOWN"


@pytest.mark.parametrize("change", ["origin", "login", "context"])
def test_observed_destination_cannot_override_authentication_guards(change):
    manager, session, page, _ = service()
    page.url = "https://myaadhaar.uidai.gov.in/ssup/demoUpdate/update/en_IN"
    page.visible_labels.update(OBSERVED_ADDRESS_LABELS)
    if change == "origin": page.url = "https://unrelated.example/ssup/demoUpdate/update/en_IN"
    elif change == "login": page.otp_visible = True
    else: page.context = SimpleNamespace(pages=[page], browser=page.browser)
    assert immediate(manager._verify_address_destination(session)).status.value != "VERIFIED_SUCCESS"


def test_not_ready_address_stage_performs_no_fill_or_navigation():
    manager, session, page, controls = address()
    controls["house"].clear()
    result = immediate(request(manager, session))
    assert result["execution_result"]["status"] == "UNKNOWN"
    assert session.current_stage == PortalStage.STAGE_3_ADDRESS
    page.evaluate.assert_not_awaited()
    manager._smart_fill.assert_not_awaited()
    manager._smart_click_or_submit.assert_not_awaited()


def test_navigation_without_destination_or_controls_is_unverified():
    manager, session, page, controls = service()
    page.url = "https://myaadhaar.uidai.gov.in/dashboard"
    controls["pincode"].clear()
    result = immediate(request(manager, session))
    assert result["execution_result"]["status"] == "UNKNOWN"
    assert session.current_stage == PortalStage.STAGE_2_SERVICE
    assert result["execution_uncertain"]


def test_disabled_dependent_dropdowns_do_not_block_pin_filling_readiness():
    manager, session, page, controls = address()
    controls["vtc"][-1].is_enabled.return_value = False
    controls["post_office"].clear()
    assert immediate(manager._verify_address_form_ready(session)).status.value == "VERIFIED_SUCCESS"
    result = immediate(request(manager, session))
    assert result["execution_result"]["status"] == "VERIFIED_SUCCESS"
    assert any(call.args[2] == "641025" for call in manager._smart_fill.await_args_list)


def test_readiness_rejection_proves_no_dispatch_and_allows_safe_retry():
    manager, session, page, controls = address()
    control = controls["house"].pop()
    result = immediate(request(manager, session))
    assert result["execution_result"]["status"] == "UNKNOWN"
    assert result["retry_permitted"] and not result["execution_uncertain"]
    assert session.attempts["attempt"]["state"] == "not_dispatched"
    page.evaluate.assert_not_awaited()
    controls["house"].append(control)
    retried = immediate(request(manager, session, "explicit-fresh-retry"))
    assert retried["execution_result"]["status"] == "VERIFIED_SUCCESS"


def test_combined_address_requires_structured_confirmation_before_dispatch():
    manager, session, page, _ = address()
    session.context.facts.pop("house")
    result = immediate(request(manager, session))
    assert result["execution_result"]["status"] == "NEEDS_USER"
    assert result["retry_permitted"] and not result["execution_uncertain"]
    page.evaluate.assert_not_awaited()
    manager._smart_fill.assert_not_awaited()


def test_labelled_pin_contamination_is_removed_without_inventing_locality():
    manager, _, _, _ = service()
    parsed = manager._parse_address_components({"new_address": "no.910, race course, coimbatorepincode:641018", "pincode": "641018", "existing_address": "Old place 638106", "house_no": "no.910", "street": "race course"})
    assert parsed["new_address"] == "no.910, race course, coimbatore"
    assert parsed["house"] == "no.910" and parsed["street"] == "race course"
    assert parsed["pincode"] == "641018" and parsed["area"] == ""
    with pytest.raises(ValueError, match="conflicts"):
        manager._parse_address_components({"new_address": "new street pincode:641018", "pincode": "641025"})


def test_manual_form_readback_matches_approved_values_without_browser_action():
    manager, session, page, _ = address()
    result = immediate(manager._verify_address_values(session,
        {"pincode": "641025", "house": "123", "street": "Example Street"},
        {"pin_valid": True, "vtc_selected": True, "po_selected": True}))
    assert result is None
    page.evaluate.assert_not_awaited()
    manager._smart_fill.assert_not_awaited()
    manager._smart_click_or_submit.assert_not_awaited()
    # Matching form values alone do not clear uncertainty or prove Next/upload-page arrival.
    session.execution_uncertain = True
    blocked = immediate(request(manager, session, "manual-retry"))
    assert blocked["execution_result"]["status"] == "BLOCKED"
    assert session.execution_uncertain


def test_destination_wait_observes_delayed_label_without_repeating_navigation():
    manager, session, page, _ = service()
    page.url = "https://myaadhaar.uidai.gov.in/ssup/demoUpdate/update/en_IN"
    page.visible_labels.update(OBSERVED_ADDRESS_LABELS - {"Current Details"})
    async def render(*args):
        page.visible_labels.add("Current Details")
    page.wait_for_timeout.side_effect = render
    assert immediate(manager._verify_address_destination(session)).status.value == "VERIFIED_SUCCESS"
    page.wait_for_timeout.assert_awaited_once_with(250)
    page.evaluate.assert_not_awaited()


def test_observed_structural_controls_match_existing_selectors_without_values():
    import re
    manager, session, page, _ = service()
    # Sanitized captured metadata; no values or invented portal attributes.
    metadata = [
        ("input", "house", True), ("input", "street", True),
        ("input", "locality", True), ("input", "pincode", True),
        ("select", "state", False), ("select", "district", False), ("select", "vtc", False),
    ]
    def locator(selector):
        if selector in ADDRESS_REVIEW_CONTROLS.values():
            found = []
            for tag, name, enabled in metadata:
                if any(re.search(r'^' + tag + r'\[name\*="([^"]+)" i\]', fragment.strip()) and
                       re.search(r'^' + tag + r'\[name\*="([^"]+)" i\]', fragment.strip()).group(1).lower() in name.lower()
                       for fragment in selector.split(',')):
                    found.append(SimpleNamespace(is_visible=AsyncMock(return_value=True), is_enabled=AsyncMock(return_value=enabled)))
            return SimpleNamespace(count=AsyncMock(return_value=len(found)), nth=lambda i: found[i])
        return original(selector)
    original = page.locator
    page.locator = locator
    for field in ("house", "street", "area", "pincode"):
        assert immediate(manager._visible_control(page, ADDRESS_REVIEW_CONTROLS[field])) is not None
    assert immediate(manager._verify_address_form_ready(session)).status.value == "VERIFIED_SUCCESS"


@pytest.mark.parametrize("field", ["house", "street", "area", "pincode"])
def test_disabled_visible_copy_does_not_make_editable_control_ambiguous(field):
    manager, session, page, controls = service()
    editable = controls[field][-1]
    controls[field].append(SimpleNamespace(is_visible=AsyncMock(return_value=True), is_enabled=AsyncMock(return_value=False)))
    assert immediate(manager._visible_control(page, ADDRESS_REVIEW_CONTROLS[field])) is editable
    controls[field].append(editable)
    assert immediate(manager._visible_control(page, ADDRESS_REVIEW_CONTROLS[field])) is None


def test_disabled_house_copy_allows_confirmed_fill_and_exact_readback():
    manager, session, page, controls = address()
    controls["house"].append(SimpleNamespace(is_visible=AsyncMock(return_value=True), is_enabled=AsyncMock(return_value=False)))
    result = immediate(request(manager, session))
    assert result["execution_result"]["status"] == "VERIFIED_SUCCESS"
    assert session.current_stage == PortalStage.STAGE_4_DOCUMENT
    assert any(call.args[2] == "123" for call in manager._smart_fill.await_args_list)
    assert controls["house"][1].input_value.await_count == 1
    binding = result["execution_diagnostic"]
    assert binding["state_version"] == result["execution_state_version"]
    assert binding["attempt_reference"] == session.attempts["attempt"]["observation_reference"]
    assert session.last_observation == binding


def test_readiness_failure_reports_actual_check_and_stable_page_binding():
    from agents.utility_based.execution_assistance.interactive_session import page_observation_reference
    manager, session, page, controls = address()
    controls["house"].append(controls["house"][-1])
    result = immediate(request(manager, session))
    diagnostic = result["execution_diagnostic"]
    assert diagnostic["verifier_invoked"] is True
    assert diagnostic["verification_check"] == "address_form_readiness"
    assert diagnostic["page_reference"] == page_observation_reference(session)
    assert diagnostic["state_version"] == session.execution_version
    assert result["retry_permitted"] and not result["execution_uncertain"]
    page.evaluate.assert_not_awaited()
    old_reference = diagnostic["page_reference"]
    session.page = SimpleNamespace()
    assert page_observation_reference(session) != old_reference
