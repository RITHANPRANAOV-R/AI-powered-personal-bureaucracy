"""B.3.1: mocked confirmation and direct correction boundaries, no live I/O."""
from agents.utility_based.execution_assistance.tests.review_fixtures import enroll, resolve_review, confirm_review, bind_context
import asyncio
from unittest.mock import AsyncMock, Mock, patch
import pytest
from fastapi.testclient import TestClient
from agents.utility_based.execution_assistance.tests.test_address_projection import resolved_context, project, api_module, PIN
from agents.utility_based.execution_assistance.interactive_session import InteractivePortalManager, ActiveBrowserSession, PortalStage
from agents.utility_based.execution_assistance.schema import ActionExecutionResult, ExecutionOutcome
from agents.knowledge_based.information_retrieval.retrieval.address_resolver import PostalAddressResolver
from agents.knowledge_based.information_retrieval.schemas.address_resolution import AddressResolutionStatus


@pytest.mark.parametrize("key,value", [("pincode", "560001"), ("pin", "560001"),
    ("new_address", "Corrected address"), ("address", "Corrected address"),
    ("vtc", "Citizen VTC"), ("city", "Citizen city"), ("post_office", "Citizen PO"),
    ("po", "Citizen PO"), ("locality", "Citizen locality"), ("area", "Citizen area")])
def test_direct_manager_corrections_invalidate_before_action(key, value):
    _, _, _, ctx = resolved_context()
    manager = InteractivePortalManager()
    ctx, _ = bind_context(ctx, projected=True, active=True)
    session = ActiveBrowserSession(session_id=ctx.session_id, context=ctx)
    manager._sessions[ctx.session_id] = session
    before = session.context.model_dump_json()
    async def action(actual_session, stage):
        corrected = actual_session.context
        assert corrected.address_resolution is None
        assert not any(f.resolution_projection for f in corrected.facts.values())
        canonical = {"pin": "pincode", "address": "new_address"}.get(key, key)
        assert corrected.facts[canonical].value == value
        assert corrected.facts[canonical].provenance == "user_corrected"
        assert corrected.facts[canonical].allowed_for_execution
        if key not in {"post_office", "po"}:
            assert "post_office" not in corrected.facts
        return ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER, message="Synthetic checkpoint")
    manager._execute_stage_action_on_portal = AsyncMock(side_effect=action)
    with patch.object(PostalAddressResolver, "resolve") as resolve:
        result = asyncio.run(manager.submit_step(ctx.session_id, True, user_inputs={key: value}))
        resolve.assert_not_called()
    assert result["is_completed"] is False
    assert session.current_stage == PortalStage.STAGE_1A_OTP
    assert session.context.model_dump_json() != before
    manager._execute_stage_action_on_portal.assert_awaited_once()


def test_direct_non_address_correction_preserves_valid_projection():
    _, _, _, ctx = resolved_context()
    manager = InteractivePortalManager()
    ctx, _ = bind_context(ctx, projected=True, active=True)
    session = ActiveBrowserSession(session_id=ctx.session_id, context=ctx)
    manager._sessions[ctx.session_id] = session
    previous = session.context.facts["post_office"].model_copy(deep=True)
    manager._execute_stage_action_on_portal = AsyncMock()
    with patch.object(PostalAddressResolver, "resolve") as resolve:
        result = asyncio.run(manager.submit_step(ctx.session_id, False, user_inputs={"name": "Corrected citizen"}))
        resolve.assert_not_called()
    assert session.context.facts["name"].value == "Corrected citizen"
    assert session.context.facts["post_office"] == previous
    assert session.context.address_resolution is not None
    assert result["status"] == "waiting_for_consent"
    manager._execute_stage_action_on_portal.assert_not_awaited()


def test_direct_invalid_pin_blocks_without_mutation_or_action():
    _, _, _, ctx = resolved_context()
    manager = InteractivePortalManager()
    ctx, _ = bind_context(ctx, projected=True, active=True)
    session = ActiveBrowserSession(session_id=ctx.session_id, context=ctx)
    manager._sessions[ctx.session_id] = session
    before = session.context.model_dump_json()
    manager._execute_stage_action_on_portal = AsyncMock()
    result = asyncio.run(manager.submit_step(ctx.session_id, True, user_inputs={"pincode": "64102"}))
    assert result["execution_result"]["status"] == "BLOCKED"
    assert session.context.model_dump_json() == before
    manager._execute_stage_action_on_portal.assert_not_awaited()


def test_frontend_api_resolve_review_confirm_sequence(monkeypatch):
    monkeypatch.setenv("AADHAAR_RUNTIME_MODE", "demo")
    service, extraction, data, _ = resolved_context()
    service.address_resolver = Mock(spec=PostalAddressResolver)
    service.address_resolver.resolve.return_value = data.address_resolution
    client = TestClient(api_module().create_app(document_service=service))
    ordinary, headers = enroll(client, extraction)
    assert not ordinary["resolver_projection"]["eligible"]
    reviewed = resolve_review(client, ordinary, headers)
    result = reviewed.json()
    assert result["resolver_projection"]["eligible"] is True
    assert "post_office" not in result["confirmed_context"]["facts"]
    envelope = result["confirmed_data"]["address_resolution"]
    assert envelope["candidates"] and envelope["evidence"]
    confirmed = confirm_review(client, reviewed, headers)
    assert confirmed.status_code == 200, confirmed.text
    facts = confirmed.json()["confirmed_context"]["facts"]
    assert facts["post_office"]["value"] == "Alpha Office"
    assert facts["post_office"]["resolution_projection"]["explicitly_confirmed"] is True
    assert facts["pincode"]["value"] == PIN
    assert not facts["address_resolution"]["allowed_for_execution"]
    for key in ("state", "district", "vtc", "locality"):
        assert key not in facts
    service.address_resolver.resolve.assert_called_once()

@pytest.mark.parametrize("status", [AddressResolutionStatus.AMBIGUOUS, AddressResolutionStatus.UNAVAILABLE, AddressResolutionStatus.CONFLICT])
def test_ineligible_api_projection_returns_clear_error(monkeypatch, status):
    monkeypatch.setenv("AADHAAR_RUNTIME_MODE", "demo")
    service, extraction, data, _ = resolved_context(multiple=True)
    envelope = data.address_resolution.model_copy(deep=True)
    envelope.status = status
    service.address_resolver = Mock(spec=PostalAddressResolver)
    service.address_resolver.resolve.return_value = envelope
    client = TestClient(api_module().create_app(document_service=service))
    ordinary, headers = enroll(client, extraction)
    review = resolve_review(client, ordinary, headers)
    assert review.json()["resolver_projection"]["eligible"] is False
    response = confirm_review(client, review, headers)
    assert response.status_code == 409
    assert "ineligible" in response.json()["detail"]

def test_api_pin_correction_rejects_confirmation_of_old_result(monkeypatch):
    monkeypatch.setenv("AADHAAR_RUNTIME_MODE", "demo")
    service, extraction, data, _ = resolved_context()
    service.address_resolver = Mock(spec=PostalAddressResolver)
    service.address_resolver.resolve.return_value = data.address_resolution
    client = TestClient(api_module().create_app(document_service=service))
    created, headers = enroll(client, extraction)
    review = resolve_review(client, created, headers)
    service.address_resolver.resolve.reset_mock()
    base = "/api/review-contexts/" + created["confirmed_context"]["review_context"]["id"]
    corrected = client.post(base + "/action", headers=headers, json={"action": "correct", "corrections": {"pincode": "560001"}})
    assert corrected.status_code == 200
    assert "address_resolution" not in corrected.json()["confirmed_context"]["facts"]
    assert corrected.json()["confirmed_context"]["facts"]["pincode"]["value"] == "560001"
    assert confirm_review(client, review, headers).status_code == 409
    service.address_resolver.resolve.assert_not_called()

@pytest.mark.parametrize("corrections", [{"pincode": "560001"}, {"new_address": "Corrected street, Tamil Nadu 641025"}, {"existing_address": "Corrected current address"}])
def test_explicit_resolution_after_correction_can_be_reviewed_and_confirmed(monkeypatch, corrections):
    from agents.knowledge_based.information_retrieval.tests.test_address_resolver import lookup, postal_record
    monkeypatch.setenv("AADHAAR_RUNTIME_MODE", "demo")
    service, extraction, _, _ = resolved_context()
    corrected = service.confirm(extraction, corrections)
    pin = corrected.pincode.value
    result = PostalAddressResolver().resolve(pin, corrected, lookup([postal_record("Reviewed Office", pincode=pin)], queried_pin=pin))
    service.address_resolver = Mock(spec=PostalAddressResolver)
    service.address_resolver.resolve.return_value = result
    client = TestClient(api_module().create_app(document_service=service))
    payload = {"confirmed": True, "extraction": extraction.model_dump(mode="json"), "corrections": corrections}
    created, headers = enroll(client, extraction, corrections)
    review = resolve_review(client, created, headers)
    assert review.status_code == 200, review.text
    assert review.json()["resolver_projection"]["eligible"] is True
    response = confirm_review(client, review, headers)
    assert response.status_code == 200, response.text
    facts = response.json()["confirmed_context"]["facts"]
    assert facts["post_office"]["value"] == "Reviewed Office"
    for key, value in corrections.items():
        assert facts[key]["value"] == value
        assert facts[key]["provenance"] == "user_corrected"
    service.address_resolver.resolve.assert_called_once()
