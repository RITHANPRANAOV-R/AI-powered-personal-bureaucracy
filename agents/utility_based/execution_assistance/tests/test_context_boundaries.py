from agents.utility_based.execution_assistance.schema import ActionExecutionResult
"""Upstream corrections, reference integrity, JSON and protected fill contract."""
from agents.utility_based.execution_assistance.tests.review_fixtures import enroll, resolve_review, confirm_review, bind_context
import asyncio
import json
import os
from unittest.mock import AsyncMock, Mock, patch
import pytest
from agents.utility_based.execution_assistance.context_validator import apply_context_corrections, reconstruct_execution_context, validate_context
from agents.utility_based.execution_assistance.schema import ConfirmedExecutionContext
from agents.utility_based.execution_assistance.tests.test_address_resolution_handoff import context, resolution
from agents.orchestration.document_input.tests.test_canonical_contracts import extract
from agents.utility_based.execution_assistance.interactive_session import InteractivePortalManager, ActiveBrowserSession, PortalStage


@pytest.mark.parametrize("key,value", [("address", "Changed address"), ("new_address", "Changed address"), ("pincode", "641025"), ("vtc", "Changed town"), ("post_office", "Changed PO"), ("state", "Changed state"), ("district", "Changed district"), ("locality", "Changed locality")])
def test_relevant_edits_remove_stale_envelope(key, value):
    original = context(resolution())
    updated = apply_context_corrections(original, {key: value})
    assert updated.address_resolution is None
    assert original.address_resolution is not None
    assert updated.facts["new_address" if key == "address" else key].provenance == "user_corrected"
    assert updated.application_id == original.application_id


def test_no_relevant_change_preserves_resolution():
    original = context(resolution())
    for edits in ({}, {"pincode": "110001"}, {"name": "Citizen"}):
        updated = apply_context_corrections(original, edits)
        assert updated.address_resolution == original.address_resolution
        assert not updated.facts["address_resolution"].allowed_for_execution


def test_address_projection_updated_without_existing_address_mutation():
    original = context(resolution())
    updated = apply_context_corrections(original, {"address": "New corrected address"})
    assert updated.facts["new_address"].value == updated.facts["address"].value == "New corrected address"
    assert updated.facts["existing_address"] == original.facts["existing_address"]


@pytest.mark.parametrize("edits", [{"pincode": "bad"}, {"pincode": 641025}, {"address": "A", "new_address": "B"}, {"pin": "110001", "pincode": "641025"}])
def test_invalid_or_conflicting_edits_fail_without_mutation(edits):
    original = context(resolution())
    before = original.model_dump_json()
    with pytest.raises(ValueError):
        apply_context_corrections(original, edits)
    assert original.model_dump_json() == before


def test_otp_not_recorded_as_correction():
    assert "otp" not in apply_context_corrections(context(), {"otp": "synthetic"}).facts


def test_known_document_reference_passes():
    assert validate_context(context(), [], ["test-document"]) is None


def test_unknown_reference_fails():
    data = context().model_dump(mode="json")
    data["document_refs"] = ["unknown"]
    assert "Unresolved" in validate_context(ConfirmedExecutionContext.model_validate(data), [], [])
    with pytest.raises(ValueError, match="Unresolved"):
        reconstruct_execution_context(data)


def test_empty_refs_optional_but_required_fails():
    ctx = ConfirmedExecutionContext(session_id="empty")
    assert validate_context(ctx, [], []) is None
    assert "missing" in validate_context(ctx, [], ["required"])


def test_duplicate_refs_fail():
    ctx = context()
    ctx.document_refs.append("test-document")
    assert "Duplicate" in validate_context(ctx, [], [])


def test_replaced_document_invalidates_old_ref():
    data = context().model_dump(mode="json")
    for fact in data["facts"].values():
        if fact.get("source_document_id"):
            fact["source_document_id"] = "replacement"
    data["facts"]["document_evidence"]["value"]["document_id"] = "replacement"
    assert "Unresolved" in validate_context(ConfirmedExecutionContext.model_validate(data), [], [])
    data["document_refs"] = ["replacement"]
    assert validate_context(ConfirmedExecutionContext.model_validate(data), [], []) is None


def test_reconstruction_does_not_grant_missing_permission():
    ctx = reconstruct_execution_context({"session_id": "test", "facts": {"pincode": "641025"}})
    assert not ctx.facts["pincode"].allowed_for_execution


def test_pin_exact_through_confirmation_json_launch_and_existing_fill(monkeypatch):
    monkeypatch.setenv("AADHAAR_RUNTIME_MODE", "demo")
    from api.app import create_app
    from fastapi.testclient import TestClient
    from agents.utility_based.execution_assistance.interactive_session import interactive_manager
    service, extraction = extract(user={"pincode": "641025", "new_address": "12 ABC Street, Tamil Nadu 641025"})
    ctx, headers = bind_context(service.confirm(extraction).to_execution_context("canonical-pin", "application"))
    captured = []
    async def start(actual, urn=None):
        captured.append(actual)
        return {"session_id": actual.session_id}
    with patch.object(interactive_manager, "start_session", side_effect=start):
        response = TestClient(create_app(document_service=service)).post("/api/browser/launch-uidai", json={"confirmed_context": json.loads(ctx.model_dump_json())}, headers=headers)
    assert response.status_code == 200, response.text
    rebuilt = captured[0]
    assert rebuilt.application_id == "application"
    assert rebuilt.facts["pincode"].value == "641025"
    assert rebuilt.facts["new_address"].value == rebuilt.facts["address"].value
    manager = InteractivePortalManager()
    page = Mock()
    page.evaluate = AsyncMock(return_value=None)
    page.wait_for_timeout = AsyncMock()
    manager._smart_fill = AsyncMock(return_value=True)
    manager._select_dropdown_option = AsyncMock(return_value=True)
    manager._smart_click_or_submit = AsyncMock(return_value=False)
    manager._validate_address_stage = AsyncMock(return_value={"valid": False})
    session = ActiveBrowserSession(session_id=rebuilt.session_id, context=rebuilt, page=page, current_stage=PortalStage.STAGE_3_ADDRESS)
    asyncio.run(manager._execute_stage_action_on_portal(session, PortalStage.STAGE_3_ADDRESS))
    pin_calls = [call for call in manager._smart_fill.call_args_list if 'input[name*="pincode" i]' in call.args[1]]
    assert len(pin_calls) == 1
    assert pin_calls[0].args[2] == "641025"


def test_submit_api_applies_correction_before_protected_manager(monkeypatch):
    monkeypatch.setenv("AADHAAR_RUNTIME_MODE", "demo")
    from api.app import create_app
    from fastapi.testclient import TestClient
    from agents.utility_based.execution_assistance.interactive_session import interactive_manager
    ctx, headers = bind_context(context(), active=True)
    from agents.utility_based.execution_assistance.review_context import review_registry
    context_id = ctx.review_context["id"]
    reservation, _ = review_registry.begin_lookup(context_id)
    review_registry.finish_lookup(context_id, reservation, resolution())
    ctx = review_registry.snapshot(context_id)
    session = ActiveBrowserSession(session_id=ctx.session_id, context=ctx)
    async def submit(active_session, stage):
        assert active_session is session
        assert session.context.address_resolution is None
        assert session.context.facts["pincode"].value == "641025"
        assert session.context.facts["pincode"].provenance == "user_corrected"
        return ActionExecutionResult(status="NEEDS_USER", message="Synthetic checkpoint")
    with patch.dict(interactive_manager._sessions, {ctx.session_id: session}), patch.object(interactive_manager, "_execute_stage_action_on_portal", side_effect=submit):
        response = TestClient(create_app()).post("/api/browser/submit-step", json={"request_id": "fixture-attempt", "expected_stage": session.current_stage.value, "expected_state_version": session.execution_version, "session_id": ctx.session_id, "user_consent": True, "user_inputs": {"pincode": "641025"}}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["execution_result"]["status"] == "NEEDS_USER"


def test_invalid_submit_correction_never_reaches_manager(monkeypatch):
    monkeypatch.setenv("AADHAAR_RUNTIME_MODE", "demo")
    from api.app import create_app
    from fastapi.testclient import TestClient
    from agents.utility_based.execution_assistance.interactive_session import interactive_manager
    ctx, headers = bind_context(context(), active=True)
    from agents.utility_based.execution_assistance.review_context import review_registry
    context_id = ctx.review_context["id"]
    reservation, _ = review_registry.begin_lookup(context_id)
    review_registry.finish_lookup(context_id, reservation, resolution())
    ctx = review_registry.snapshot(context_id)
    before = ctx.model_dump_json()
    session = ActiveBrowserSession(session_id=ctx.session_id, context=ctx)
    with patch.dict(interactive_manager._sessions, {ctx.session_id: session}), patch.object(interactive_manager, "_execute_stage_action_on_portal", new_callable=AsyncMock) as submit:
        response = TestClient(create_app()).post("/api/browser/submit-step", json={"request_id": "fixture-attempt", "expected_stage": session.current_stage.value, "expected_state_version": session.execution_version, "session_id": ctx.session_id, "user_consent": True, "user_inputs": {"pincode": "bad"}}, headers=headers)
        submit.assert_not_called()
    assert response.status_code == 200
    assert response.json()["execution_result"]["status"] == "BLOCKED"
    assert session.context.model_dump_json() == before


@pytest.mark.parametrize("alias", ["pin", "pincode", "postal_code", "postalCode"])
def test_postal_alias_correction_preserves_canonical_pin_and_invalidates_resolution(alias):
    original = context(resolution())
    corrected = apply_context_corrections(original, {alias: "641025", "new_address": "12 ABC Street, Tamil Nadu 641025"})
    assert corrected.facts["pincode"].value == "641025"
    assert corrected.address_resolution is None
    assert corrected.facts["existing_address"] == original.facts["existing_address"]
    assert not ({"pin", "postal_code", "postalCode"} & corrected.facts.keys())
    rebuilt = reconstruct_execution_context(json.loads(corrected.model_dump_json()))
    mapped = InteractivePortalManager()._parse_address_components({k: f.value for k, f in rebuilt.facts.items()})
    assert mapped["pincode"] == "641025"
    assert mapped["new_address"] == "12 ABC Street, Tamil Nadu 641025"


@pytest.mark.parametrize("edits", [{"postal_code": "641025", "pincode": "560001"},
                                  {"postalCode": "641025", "pin": "560001"},
                                  {"postal_code": "000000"}, {"postal_code": "64102"}])
def test_postal_alias_conflicts_and_invalid_values_are_rejected(edits):
    original = context()
    before = original.model_dump_json()
    with pytest.raises(ValueError): apply_context_corrections(original, edits)
    assert original.model_dump_json() == before


def _complete_immediate_mock(coroutine):
    """No event-loop policy workaround: all mocked awaits must complete immediately."""
    try:
        coroutine.send(None)
    except StopIteration as finished:
        return finished.value
    finally:
        coroutine.close()
    raise AssertionError("Mocked path unexpectedly suspended; runtime test is required.")


@pytest.mark.parametrize("status", ["resolved", "ambiguous", "conflict", "no_result", "unavailable", "invalid_pin"])
def test_confirm_reconstruct_and_existing_fill_preserve_pin_without_optional_projection(monkeypatch, status):
    monkeypatch.setenv("AADHAAR_RUNTIME_MODE", "demo")
    from api.app import create_app
    from api.app import ConfirmationRequest
    from agents.utility_based.execution_assistance import review_context
    from agents.utility_based.execution_assistance.tests.test_controlled_address_handoff import service_for, extraction
    from agents.utility_based.execution_assistance.tests.test_review_context import setup
    registry, _, _, _ = setup(monkeypatch)
    service, fetcher = service_for(status)
    postal = fetcher.lookup.return_value
    postal.queried_pin = "560001" if status == "conflict" else "641025"
    for record in postal.records:
        record.pincode = "641025"
        record.source_record["pincode"] = "641025"
    app = create_app(document_service=service)
    endpoint = next(r.endpoint for r in app.routes if getattr(r, "path", "") == "/api/documents/aadhaar/confirm")
    response = _complete_immediate_mock(endpoint(ConfirmationRequest(confirmed=True, extraction=extraction(),
        corrections={"postal_code": "641025", "new_address": "12 ABC Street, Tamil Nadu 641025"}, session_id="synthetic")))
    raw = response.confirmed_context
    rebuilt = reconstruct_execution_context(raw, capability=response.review_capability)
    cid = rebuilt.review_context["id"]
    reservation, inputs = registry.begin_lookup(cid)
    # Existing synthetic service fixtures exercise resolver outcomes without network I/O.
    result = service.address_resolver.resolve("641025", {k:f.value for k,f in inputs.facts.items()})
    assert result.status.value == status
    fetcher.lookup.assert_called_once_with("641025")
    registry.finish_lookup(cid, reservation, result)
    registry.publish(cid)
    clean = registry.without_projection(cid)
    rebuilt = reconstruct_execution_context(clean.model_dump(mode="json"), capability=response.review_capability)
    assert rebuilt.facts["pincode"].value == "641025"
    assert rebuilt.facts["new_address"].value == "12 ABC Street, Tamil Nadu 641025"
    assert "post_office" not in rebuilt.facts
    manager = InteractivePortalManager()
    page = Mock(evaluate=AsyncMock(return_value=False), wait_for_timeout=AsyncMock())
    manager._smart_fill = AsyncMock(return_value=True)
    manager._select_dropdown_option = AsyncMock(return_value={"status": "needs_user"})
    manager._validate_address_stage = AsyncMock(return_value={"pin_valid": True, "vtc_selected": False, "po_selected": False})
    manager._smart_click_or_submit = AsyncMock()
    session = ActiveBrowserSession(rebuilt.session_id, rebuilt, page=page)
    _complete_immediate_mock(manager._execute_stage_action_on_portal(session, PortalStage.STAGE_3_ADDRESS))
    assert any(call.args[2] == "641025" and 'input[name*="pincode" i]' in call.args[1]
        for call in manager._smart_fill.await_args_list)
    manager._smart_click_or_submit.assert_not_awaited()


@pytest.mark.parametrize("facts,expected", [({"new_address": "12 Street, 641025"}, "641025"),
    ({"new_address": "12 Street"}, ""),
    ({"new_address": "12 Street, 641025", "pincode": "641025"}, "641025")])
def test_address_mapping_unique_pin_or_genuine_missing(facts, expected):
    assert InteractivePortalManager()._parse_address_components(facts)["pincode"] == expected


@pytest.mark.parametrize("facts", [{"new_address": "12 Street, 641025 or 560001"},
    {"new_address": "12 Street", "pincode": "000000"}, {"pincode": "64102"}])
def test_address_mapping_rejects_ambiguous_or_invalid_pin(facts):
    with pytest.raises(ValueError): InteractivePortalManager()._parse_address_components(facts)
