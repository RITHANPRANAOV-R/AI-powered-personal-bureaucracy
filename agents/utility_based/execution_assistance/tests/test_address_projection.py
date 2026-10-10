from agents.utility_based.execution_assistance.schema import ActionExecutionResult
"""B.1 projection tests: official-shaped synthetic evidence, no live browser/HTTP."""
from agents.utility_based.execution_assistance.tests.review_fixtures import enroll, resolve_review, confirm_review, bind_context
import asyncio
import importlib
from unittest.mock import AsyncMock, Mock, patch
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from agents.knowledge_based.information_retrieval.retrieval.address_resolver import PostalAddressResolver
from agents.knowledge_based.information_retrieval.schemas.address_resolution import AddressFieldStatus, AddressResolutionResult, AddressResolutionStatus
from agents.knowledge_based.information_retrieval.tests.test_address_resolver import lookup, postal_record
from agents.orchestration.document_input.service import AadhaarDocumentService
from agents.orchestration.document_input.tests.test_canonical_contracts import extract
from agents.utility_based.execution_assistance.address_projection import project_confirmed_resolution, PROJECTION_PROVENANCE
from agents.utility_based.execution_assistance.context_validator import apply_context_corrections, reconstruct_execution_context
from agents.utility_based.execution_assistance.schema import ConfirmedExecutionContext, ConfirmedFact, FactStatus
from agents.utility_based.execution_assistance.interactive_session import InteractivePortalManager, ActiveBrowserSession, PortalStage, interactive_manager

PIN = "641025"
NEW_ADDRESS = "12 ABC Street, Tamil Nadu 641025"


def resolved_context(pin=PIN, office="Alpha Office", multiple=False):
    service, extraction = extract(pin, {"pincode": pin, "new_address": NEW_ADDRESS.replace(PIN, pin)})
    data = service.confirm(extraction)
    records = [postal_record(office, pincode=pin)]
    if multiple:
        records.append(postal_record("Beta Office", pincode=pin))
    result = PostalAddressResolver().resolve(pin, data, lookup(records, queried_pin=pin))
    data.address_resolution = result
    return service, extraction, data, data.to_execution_context("projection", "application")


def project(context):
    return project_confirmed_resolution(context, explicitly_confirmed=True)


def test_unique_confirmed_post_office_has_bound_provenance():
    _, _, _, ctx = resolved_context()
    before = ctx.model_dump_json()
    projected = project(ctx)
    fact = projected.facts["post_office"]
    assert fact.value == "Alpha Office"
    assert fact.status == FactStatus.CONFIRMED and fact.allowed_for_execution
    assert fact.provenance == PROJECTION_PROVENANCE
    assert fact.resolution_projection["explicitly_confirmed"] is True
    assert fact.resolution_projection["eligible"] is True
    assert fact.resolution_projection["evidence_ids"] == ctx.address_resolution.post_office.evidence_ids
    assert len(fact.resolution_projection["binding"]) == 64
    assert projected.address_resolution == ctx.address_resolution
    assert not projected.facts["address_resolution"].allowed_for_execution
    assert ctx.model_dump_json() == before


def test_pin_and_all_address_facts_preserved_exactly():
    _, _, _, ctx = resolved_context()
    projected = project(ctx)
    for key in ("pincode", "new_address", "existing_address", "address"):
        assert projected.facts[key] == ctx.facts[key]
    assert projected.facts["pincode"].value == PIN
    assert projected.facts["new_address"].value == NEW_ADDRESS
    assert projected.application_id == ctx.application_id


def test_pin_conflict_keeps_canonical_pin_and_conflict_envelope():
    _, _, data, ctx = resolved_context()
    data.address_resolution = PostalAddressResolver().resolve(PIN, data, lookup([postal_record(pincode="560001")], queried_pin="560001"))
    ctx = data.to_execution_context("projection")
    assert ctx.address_resolution.status == AddressResolutionStatus.CONFLICT
    projected = project(ctx)
    assert projected.facts["pincode"].value == PIN
    assert projected.address_resolution == ctx.address_resolution
    assert projected.address_resolution.conflicts
    assert "post_office" not in projected.facts


def test_multiple_post_offices_never_pick_first():
    _, _, _, ctx = resolved_context(multiple=True)
    projected = project(ctx)
    assert "post_office" not in projected.facts
    assert projected.address_resolution.candidates == ctx.address_resolution.candidates
    assert len(projected.address_resolution.candidates) == 2


@pytest.mark.parametrize("confirmation", [False, None, "true", 1])
def test_no_explicit_boolean_confirmation_no_projection(confirmation):
    _, _, _, ctx = resolved_context()
    assert "post_office" not in project_confirmed_resolution(ctx, explicitly_confirmed=confirmation).facts


@pytest.mark.parametrize("status", [AddressFieldStatus.UNRESOLVED, AddressFieldStatus.AMBIGUOUS])
def test_vtc_is_never_guessed(status):
    _, _, _, ctx = resolved_context()
    result = ctx.address_resolution.model_copy(deep=True)
    result.vtc.status = status
    result.vtc.value = None
    result.vtc.options = ["Town A", "Town B"] if status == AddressFieldStatus.AMBIGUOUS else []
    ctx.facts["address_resolution"].value = result
    projected = project(ctx)
    assert "vtc" not in projected.facts
    assert projected.address_resolution.vtc.options == result.vtc.options
    assert projected.address_resolution.vtc_requires_uidai_resolution_or_user_confirmation


def test_state_and_district_only_in_evidence():
    _, _, _, ctx = resolved_context()
    projected = project(ctx)
    assert projected.address_resolution.state.value == "Test State"
    assert projected.address_resolution.district.value == "Test District"
    assert "state" not in projected.facts and "district" not in projected.facts


@pytest.mark.parametrize("key", ["post_office", "po"])
def test_confirmed_citizen_post_office_conflict_not_overwritten(key):
    _, _, _, ctx = resolved_context()
    ctx.facts[key] = ConfirmedFact(value="Citizen PO", provenance="user_corrected", status="confirmed", allowed_for_execution=True)
    projected = project(ctx)
    assert projected.facts[key] == ctx.facts[key]
    assert not any(fact.resolution_projection for fact in projected.facts.values())


def test_agreeing_citizen_value_retains_ownership():
    _, _, _, ctx = resolved_context()
    ctx.facts["post_office"] = ConfirmedFact(value="Alpha Office", provenance="user_corrected", status="confirmed", allowed_for_execution=True)
    assert project(ctx).facts["post_office"] == ctx.facts["post_office"]


@pytest.mark.parametrize("key,value", [("pincode", "560001"), ("new_address", "Corrected address"), ("address", "Corrected address"), ("vtc", "Citizen town"), ("post_office", "Citizen PO"), ("locality", "Corrected locality"), ("state", "Citizen state"), ("district", "Citizen district")])
def test_corrections_drop_projection_and_envelope_without_resolution(key, value):
    _, _, _, ctx = resolved_context()
    projected = project(ctx)
    with patch.object(PostalAddressResolver, "resolve") as resolve:
        corrected = apply_context_corrections(projected, {key: value})
        resolve.assert_not_called()
    assert corrected.address_resolution is None
    assert not any(fact.resolution_projection for fact in corrected.facts.values())
    assert corrected.facts["new_address" if key == "address" else key].value == value
    if key != "post_office":
        assert "post_office" not in corrected.facts
    else:
        assert corrected.facts["post_office"].provenance == "user_corrected"
    assert projected.address_resolution is not None


def test_no_change_preserves_projection():
    _, _, _, ctx = resolved_context()
    projected = project(ctx)
    assert apply_context_corrections(projected, {"pincode": PIN}).facts["post_office"] == projected.facts["post_office"]


def test_fresh_explicit_resolution_and_confirmation_only_new_projection():
    _, _, _, ctx = resolved_context()
    cleaned = apply_context_corrections(project(ctx), {"pincode": "560001", "new_address": "New citizen address 560001"})
    assert "post_office" not in project(cleaned).facts
    component_context = {key: fact.value for key, fact in cleaned.facts.items()}
    fresh = PostalAddressResolver().resolve("560001", component_context, lookup([postal_record("Fresh Office", pincode="560001")], queried_pin="560001"))
    cleaned.facts["address_resolution"] = ConfirmedFact(value=fresh, provenance="postal_address_resolution_metadata", status="unconfirmed", allowed_for_execution=False)
    assert "post_office" not in project_confirmed_resolution(cleaned).facts
    new_context = project(cleaned)
    assert new_context.facts["post_office"].value == "Fresh Office"
    assert new_context.facts["pincode"].value == "560001"
    assert new_context.address_resolution == fresh


@pytest.mark.parametrize("change", ["drop_envelope", "pin", "new_address", "locality", "envelope", "unconfirmed", "value"])
def test_serialized_stale_or_tampered_projection_rejected(change):
    _, _, _, ctx = resolved_context()
    raw = project(ctx).model_dump(mode="json")
    facts = raw["facts"]
    if change == "drop_envelope": facts.pop("address_resolution")
    elif change == "pin": facts["pincode"]["value"] = "560001"
    elif change == "new_address": facts["new_address"]["value"] = "Changed address"
    elif change == "locality": facts["locality"] = {"value": "Changed area", "provenance": "user_corrected", "status": "confirmed", "allowed_for_execution": True}
    elif change == "envelope": facts["address_resolution"]["value"]["retrieved_at"] = "changed"
    elif change == "unconfirmed": facts["post_office"]["resolution_projection"]["explicitly_confirmed"] = False
    elif change == "value": facts["post_office"]["value"] = "Wrong PO"
    with pytest.raises(ValidationError):
        ConfirmedExecutionContext.model_validate(raw)


@pytest.mark.parametrize("change", ["evidence", "origin", "candidate", "options", "indexes", "context", "source"])
def test_ineligible_or_unsubstantiated_result_not_projected(change):
    _, _, _, ctx = resolved_context()
    result = ctx.address_resolution.model_copy(deep=True)
    if change == "evidence": result.evidence = []
    elif change == "origin": result.post_office.value_origin = "user_document_context"
    elif change == "candidate": result.candidates[0].office_name = "Wrong PO"
    elif change == "options": result.post_office.options.append("Another PO")
    elif change == "indexes": result.plausible_candidate_indexes = [999]
    elif change == "context": result.context.pop("new_address")
    elif change == "source": result.source.url = "https://example.invalid"
    ctx.facts["address_resolution"].value = result
    assert "post_office" not in project(ctx).facts


def test_no_resolver_path_is_identical():
    service, extraction = extract(user={"pincode": PIN, "new_address": NEW_ADDRESS})
    data = service.confirm(extraction)
    baseline = data.to_execution_context("baseline")
    assert baseline == data.to_execution_context("baseline", confirm_resolver_projection=True)
    assert baseline == project_confirmed_resolution(baseline)


def api_module():
    return importlib.import_module("api.app")


def test_api_requires_distinct_projection_confirmation(monkeypatch):
    monkeypatch.setenv("AADHAAR_RUNTIME_MODE", "demo")
    service, extraction, data, _ = resolved_context()
    service.address_resolver = Mock(spec=PostalAddressResolver)
    service.address_resolver.resolve.return_value = data.address_resolution
    client = TestClient(api_module().create_app(document_service=service))
    ordinary, headers = enroll(client, extraction)
    review = resolve_review(client, ordinary, headers)
    assert "post_office" not in review.json()["confirmed_context"]["facts"]
    projected = confirm_review(client, review, headers)
    assert projected.status_code == 200, projected.text
    assert projected.json()["confirmed_context"]["facts"]["post_office"]["value"] == "Alpha Office"
    assert not projected.json()["confirmed_context"]["facts"]["address_resolution"]["allowed_for_execution"]

def test_exact_pin_and_projected_po_reach_existing_helpers_after_launch(monkeypatch):
    monkeypatch.setenv("AADHAAR_RUNTIME_MODE", "demo")
    service, _, data, _ = resolved_context()
    ctx, headers = bind_context(data.to_execution_context("pin-projection"), projected=True)
    captured = []
    async def start(actual, urn=None):
        captured.append(actual)
        return {"session_id": actual.session_id}
    with patch.object(interactive_manager, "start_session", side_effect=start):
        response = TestClient(api_module().create_app(document_service=service)).post("/api/browser/launch-uidai", json={"confirmed_context": ctx.model_dump(mode="json")}, headers=headers)
    assert response.status_code == 200, response.text
    rebuilt = captured[0]
    assert rebuilt.facts["pincode"].value == PIN
    assert rebuilt.facts["post_office"] == ctx.facts["post_office"]
    assert reconstruct_execution_context(ctx.model_dump(mode="json"), capability=headers["Authorization"][7:]) == rebuilt
    manager = InteractivePortalManager()
    page = Mock()
    page.evaluate = AsyncMock(return_value=None)
    page.wait_for_timeout = AsyncMock()
    manager._smart_fill = AsyncMock(return_value=True)
    manager._select_dropdown_option = AsyncMock(return_value={"status": "selected"})
    manager._smart_click_or_submit = AsyncMock(return_value=False)
    manager._validate_address_stage = AsyncMock(return_value={"pin_valid": False})
    session = ActiveBrowserSession(session_id=rebuilt.session_id, context=rebuilt, page=page)
    asyncio.run(manager._execute_stage_action_on_portal(session, PortalStage.STAGE_3_ADDRESS))
    calls = [call for call in manager._smart_fill.call_args_list if 'input[name*="pincode" i]' in call.args[1]]
    assert len(calls) == 1 and calls[0].args[2] == PIN
    po_calls = [call for call in manager._select_dropdown_option.call_args_list if call.args[3] == "Post Office"]
    assert len(po_calls) == 1 and po_calls[0].args[2] == "Alpha Office"
    assert manager._select_dropdown_option.call_args_list[0].args[2] == ""


def test_api_quick_correction_removes_projection_before_execution(monkeypatch):
    monkeypatch.setenv("AADHAAR_RUNTIME_MODE", "demo")
    _, _, _, ctx = resolved_context()
    ctx, headers = bind_context(ctx, projected=True, active=True)
    session = ActiveBrowserSession(session_id=ctx.session_id, context=ctx)
    async def submit(active_session, stage):
        assert active_session is session
        assert session.context.address_resolution is None
        assert "post_office" not in session.context.facts
        assert session.context.facts["pincode"].value == "560001"
        return ActionExecutionResult(status="NEEDS_USER", message="Synthetic checkpoint")
    with patch.dict(interactive_manager._sessions, {ctx.session_id: session}), patch.object(interactive_manager, "_execute_stage_action_on_portal", side_effect=submit):
        response = TestClient(api_module().create_app()).post("/api/browser/submit-step", json={"request_id": "fixture-attempt", "expected_stage": session.current_stage.value, "expected_state_version": session.execution_version, "session_id": ctx.session_id, "user_consent": True, "user_inputs": {"pincode": "560001"}}, headers=headers)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("change", ["passage", "raw_record", "citizen_state", "citizen_district", "not_configured", "unavailable"])
def test_incoherent_evidence_or_location_not_projected(change):
    _, _, _, ctx = resolved_context()
    result = ctx.address_resolution.model_copy(deep=True)
    if change == "passage":
        next(item for item in result.evidence if item.evidence_id.startswith("postal-")).passage = '{}'
    elif change == "raw_record":
        result.candidates[0].source_record["office_name"] = "Another office"
    elif change in {"citizen_state", "citizen_district"}:
        ctx.facts[change.removeprefix("citizen_")] = ConfirmedFact(value="Conflicting location", provenance="user_corrected", status="confirmed", allowed_for_execution=True)
    elif change == "not_configured":
        result.status = AddressResolutionStatus.UNAVAILABLE
        result.post_office.value = None
    elif change == "unavailable":
        result.status = AddressResolutionStatus.UNAVAILABLE
    ctx.facts["address_resolution"].value = result
    assert "post_office" not in project(ctx).facts


def test_ambiguous_result_cannot_project_even_common_po():
    _, _, _, ctx = resolved_context()
    result = ctx.address_resolution.model_copy(deep=True)
    result.status = AddressResolutionStatus.AMBIGUOUS
    ctx.facts["address_resolution"].value = result
    assert "post_office" not in project(ctx).facts


def test_duplicate_records_same_normalized_office_can_project():
    service, extraction, data, _ = resolved_context()
    records = [postal_record("Alpha Office", pincode=PIN), postal_record(" ALPHA  OFFICE ", pincode=PIN)]
    result = PostalAddressResolver().resolve(PIN, data, lookup(records, queried_pin=PIN))
    data.address_resolution = result
    projected = project(data.to_execution_context("projection"))
    assert projected.facts["post_office"].value == result.post_office.value
    assert len(projected.address_resolution.candidates) == 2


def test_context_mutation_cannot_reuse_old_projection():
    _, _, _, ctx = resolved_context()
    projected = project(ctx)
    projected.facts.pop("address_resolution")
    with pytest.raises(ValidationError, match="resolver projection"):
        project_confirmed_resolution(projected)


def test_resolution_and_projection_confirmation_are_separate_api_steps(monkeypatch):
    monkeypatch.setenv("AADHAAR_RUNTIME_MODE", "demo")
    service, extraction, _, _ = resolved_context()
    service.address_resolver = Mock(spec=PostalAddressResolver)
    response = TestClient(api_module().create_app(document_service=service)).post("/api/documents/aadhaar/confirm", json={
        "confirmed": True, "extraction": extraction.model_dump(mode="json"),
        "resolve_address": True, "confirm_resolver_projection": True,
    })
    assert response.status_code == 400
    service.address_resolver.resolve.assert_not_called()


def test_api_projection_confirmation_requires_real_boolean(monkeypatch):
    monkeypatch.setenv("AADHAAR_RUNTIME_MODE", "demo")
    service, extraction, data, _ = resolved_context()
    response = TestClient(api_module().create_app(document_service=service)).post("/api/documents/aadhaar/confirm", json={
        "confirmed": True, "extraction": extraction.model_dump(mode="json"),
        "address_resolution": data.address_resolution.model_dump(mode="json"), "confirm_resolver_projection": "true",
    })
    assert response.status_code == 422


def test_vtc_claim_not_supported_by_current_resolver_contract_stays_unprojected():
    _, _, _, ctx = resolved_context()
    result = ctx.address_resolution.model_copy(deep=True)
    result.vtc.status = AddressFieldStatus.RESOLVED
    result.vtc.value = "Unsupported town"
    result.vtc_requires_uidai_resolution_or_user_confirmation = False
    ctx.facts["address_resolution"].value = result
    assert "vtc" not in project(ctx).facts



def test_explicit_citizen_po_retained_when_same_value_and_pin_changes():
    _, _, _, ctx = resolved_context()
    corrected = apply_context_corrections(project(ctx), {"pincode": "560001", "post_office": "Alpha Office"})
    assert corrected.address_resolution is None
    assert corrected.facts["post_office"].value == "Alpha Office"
    assert corrected.facts["post_office"].provenance == "user_corrected"
    assert corrected.facts["post_office"].resolution_projection is None


def test_stale_projection_launch_rejected_before_browser_start(monkeypatch):
    monkeypatch.setenv("AADHAAR_RUNTIME_MODE", "demo")
    _, _, _, ctx = resolved_context()
    raw = project(ctx).model_dump(mode="json")
    raw["facts"].pop("address_resolution")
    with patch.object(interactive_manager, "start_session", new_callable=AsyncMock) as start:
        response = TestClient(api_module().create_app()).post("/api/browser/launch-uidai", json={"confirmed_context": raw})
        start.assert_not_called()
    assert response.status_code == 400
