"""Phase 5C-3 handoff tests; no live HTTP, OCR initialization, or browser launch."""
import asyncio
import importlib
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agents.knowledge_based.information_retrieval.live_retrieval.india_post_fetcher import (
    OGD_URL, PostalLookupResult, PostalLookupStatus, PostalRecord,
)
from agents.knowledge_based.information_retrieval.retrieval.address_resolver import PostalAddressResolver
from agents.knowledge_based.information_retrieval.schemas.address_resolution import (
    AddressResolutionResult, AddressResolutionStatus as ResolutionStatus,
)
from agents.knowledge_based.information_retrieval.schemas.source import Source, SourceType
from agents.orchestration.document_input.schema import (
    AadhaarConfirmedData, AadhaarExtractedData, ConfirmedField, ExtractedField,
    ExtractionResult, ExtractionStatus, FieldProvenance,
)
from agents.orchestration.document_input.service import AadhaarDocumentService
from agents.utility_based.execution_assistance.context_validator import validate_context
from agents.utility_based.execution_assistance.interactive_session import InteractivePortalManager
from agents.utility_based.execution_assistance.schema import ConfirmedExecutionContext, ConfirmedFact, FactStatus

PIN = "110001"
ADDRESS = "House 2, Alpha Office"
TIMESTAMP = "2026-10-08T00:00:00+00:00"


def resolution(context=None, multiple=False):
    records = [PostalRecord(pincode=PIN, state_name="Test State", district="Test District",
                           office_name="Alpha Office", taluka="Test Taluka",
                           source_record={"pincode": PIN, "officename": "Alpha Office"})]
    if multiple:
        records.append(records[0].model_copy(update={"office_name": "Beta Office", "source_record": {"pincode": PIN, "officename": "Beta Office"}}))
    lookup = PostalLookupResult(
        status=PostalLookupStatus.MULTIPLE_RECORDS if multiple else PostalLookupStatus.SUCCESS,
        queried_pin=PIN, records=records, retrieved_at=TIMESTAMP,
        source=Source(source_id="india-post-all-india-pincode-directory", url=OGD_URL,
                      authority="Department of Posts, Government of India", domain="india_post",
                      source_type=SourceType.GOVERNMENT_API, last_checked=TIMESTAMP),
    )
    return PostalAddressResolver().resolve(PIN, context or {}, lookup)


def field(value):
    return ConfirmedField(value=value, source_document_id="test-document",
                          provenance=FieldProvenance.USER_CONFIRMED, confirmed_at=TIMESTAMP)


def confirmed(result=None, **changes):
    data = dict(document_id="test-document", aadhaar_number=field("111122223333"),
                vid=field("1111222233334444"), masked_aadhaar=field("XXXX XXXX 3333"),
                existing_address=field("Old Address"), new_address=field(ADDRESS),
                pincode=field(PIN), address_resolution=result)
    data.update(changes)
    return AadhaarConfirmedData(**data)


def context(result=None):
    return confirmed(result).to_execution_context("handoff-session", "application-1")


def test_resolved_result_reaches_existing_context_as_one_structured_fact():
    result = resolution()
    ctx = context(result)
    assert ctx.address_resolution == result
    assert ctx.facts["address_resolution"].value == result
    assert isinstance(ctx.facts["address_resolution"].value, AddressResolutionResult)
    assert ctx.address_resolution.status == ResolutionStatus.RESOLVED
    assert not ctx.facts["address_resolution"].allowed_for_execution
    assert not any(k.startswith("authoritative_") for k in ctx.facts)


@pytest.mark.parametrize("component,expected", [("state", "Test State"), ("district", "Test District"), ("post_office", "Alpha Office")])
def test_resolved_postal_fields_reach_context(component, expected):
    ctx = context(resolution())
    resolved = getattr(ctx.address_resolution, component)
    assert resolved.value == expected
    assert resolved.value_origin == "authoritative_postal"
    assert resolved.evidence_ids


def test_ambiguity_preserves_every_candidate_without_first_choice():
    result = resolution(multiple=True)
    ctx = context(result)
    assert ctx.address_resolution.status == ResolutionStatus.AMBIGUOUS
    assert ctx.address_resolution.candidates == result.candidates
    assert ctx.address_resolution.plausible_candidate_indexes == [0, 1]
    assert ctx.address_resolution.post_office.value is None
    assert ctx.address_resolution.ambiguity_information == result.ambiguity_information
    assert ctx.facts["address_resolution"].status == FactStatus.AMBIGUOUS
    assert not ctx.facts["address_resolution"].allowed_for_execution
    assert "post_office" not in ctx.facts


def test_conflict_preserved_without_overwriting_user_address():
    result = resolution({"state": "Other State"})
    ctx = context(result)
    assert ctx.address_resolution.status == ResolutionStatus.CONFLICT
    assert ctx.address_resolution.conflicts == result.conflicts
    assert ctx.address_resolution.state.value is None
    assert ctx.facts["new_address"].value == ADDRESS
    assert ctx.facts["pincode"].value == PIN
    assert ctx.facts["address_resolution"].status == FactStatus.CONFLICTING
    assert not ctx.facts["address_resolution"].allowed_for_execution


@pytest.mark.parametrize("status", [ResolutionStatus.NO_RESULT, ResolutionStatus.UNAVAILABLE, ResolutionStatus.INVALID_PIN])
def test_failure_status_preserved_without_fabricated_location(status):
    result = AddressResolutionResult(status=status, queried_pin=PIN if status != ResolutionStatus.INVALID_PIN else None)
    ctx = context(result)
    assert ctx.address_resolution.status == status
    assert ctx.address_resolution.state.value is None
    assert ctx.address_resolution.district.value is None
    assert ctx.address_resolution.post_office.value is None
    assert ctx.address_resolution.vtc.value is None
    assert ctx.address_resolution.candidates == []
    assert ctx.facts["address_resolution"].status == FactStatus.UNCONFIRMED
    assert not ctx.facts["address_resolution"].allowed_for_execution


@pytest.mark.parametrize("result", [resolution({"taluka": "Test Taluka"}), resolution({"post_office": "Alpha Office"})])
def test_postal_taluka_and_office_never_become_vtc(result):
    ctx = context(result)
    assert ctx.address_resolution.vtc.value is None
    assert ctx.address_resolution.vtc_requires_uidai_resolution_or_user_confirmation
    assert "vtc" not in ctx.facts


def test_supplied_vtc_remains_unresolved_user_context():
    result = resolution({"vtc": "User Village"})
    ctx = context(result)
    assert ctx.address_resolution.vtc.value == "User Village"
    assert ctx.address_resolution.vtc.value_origin == "user_document_context"
    assert ctx.address_resolution.vtc.status.value == "unresolved"
    assert ctx.address_resolution.vtc_requires_uidai_resolution_or_user_confirmation
    assert "vtc" not in ctx.facts  # No silent promotion to a confirmed scalar.


@pytest.mark.parametrize("vtc_status,allowed", [(FactStatus.CONFIRMED, True), (FactStatus.UNCONFIRMED, False)])
def test_existing_vtc_and_other_component_facts_are_preserved(vtc_status, allowed):
    ctx = context(resolution({"vtc": "User Village"}))
    existing = {
        "vtc": ConfirmedFact(value="Existing User Village", provenance="user-document", status=vtc_status, allowed_for_execution=allowed),
        "house": ConfirmedFact(value="House 2", provenance="user-confirmed", status=FactStatus.CONFIRMED, allowed_for_execution=True),
        "street": ConfirmedFact(value="Test Road", provenance="user-confirmed", status=FactStatus.CONFIRMED, allowed_for_execution=True),
        "locality": ConfirmedFact(value="Test Area", provenance="user-confirmed", status=FactStatus.CONFIRMED, allowed_for_execution=True),
    }
    ctx.facts.update(existing)
    reconstructed = ConfirmedExecutionContext.model_validate_json(ctx.model_dump_json())
    for key, fact in existing.items():
        assert reconstructed.facts[key] == fact
    assert reconstructed.address_resolution.vtc.value == "User Village"


def test_all_provenance_and_evidence_survive_serialization():
    result = resolution({"new_address": ADDRESS})
    ctx = ConfirmedExecutionContext.model_validate_json(context(result).model_dump_json())
    assert ctx.address_resolution.model_dump_json() == result.model_dump_json()
    assert ctx.address_resolution.source.url == OGD_URL
    assert ctx.address_resolution.retrieved_at == TIMESTAMP
    assert ctx.address_resolution.source_resource_id == result.source_resource_id
    assert ctx.address_resolution.queried_pin == PIN
    assert ctx.address_resolution.evidence == result.evidence


def test_existing_aadhaar_vid_masked_and_address_handoff_unchanged():
    old = context()
    new = context(resolution())
    for key, fact in old.facts.items():
        assert new.facts[key] == fact
    assert new.facts["aadhaar_number"].value == "111122223333"
    assert new.facts["aadhaar"].value == new.facts["uid"].value == "111122223333"
    assert new.facts["vid"].value == "1111222233334444"
    assert new.facts["masked_aadhaar"].value == "XXXX XXXX 3333"
    assert new.facts["new_address"].value == new.facts["address"].value == ADDRESS
    assert new.facts["pincode"].value == PIN
    assert old.address_resolution is None and "address_resolution" not in old.facts
    assert set(new.facts) == set(old.facts) | {"address_resolution"}
    assert new.document_refs == old.document_refs and new.application_id == old.application_id


def test_masked_document_and_vid_do_not_create_a_full_aadhaar():
    ctx = confirmed(resolution(), aadhaar_number=None).to_execution_context("handoff-session")
    assert "aadhaar_number" not in ctx.facts and "aadhaar" not in ctx.facts and "uid" not in ctx.facts
    assert ctx.facts["vid"].value == "1111222233334444"
    assert ctx.facts["masked_aadhaar"].value == "XXXX XXXX 3333"


def test_legacy_context_validation_remains_unchanged():
    for ctx in (context(), context(resolution())):
        assert validate_context(ctx, ["aadhaar_number", "address", "pincode"], ["test-document"]) is None
    assert validate_context(context(resolution()), ["address_resolution"], []) is not None


@pytest.mark.parametrize("result", [resolution(), resolution(multiple=True), resolution({"state": "Other State"})])
def test_json_input_cannot_promote_resolution_envelope_to_executable(result):
    payload = context(result).model_dump(mode="json")
    payload["facts"]["address_resolution"].update(status="confirmed", allowed_for_execution=True)
    ctx = ConfirmedExecutionContext.model_validate(payload)
    assert not ctx.facts["address_resolution"].allowed_for_execution
    assert validate_context(ctx, ["address_resolution"], []) is not None
    assert ctx.address_resolution == result


def test_result_is_copied_without_mutating_confirmed_data():
    data = confirmed(resolution())
    before = data.model_dump_json()
    ctx = data.to_execution_context("handoff-session")
    ctx.address_resolution.candidates[0].office_name = "Changed Context Copy"
    assert data.model_dump_json() == before


def test_malformed_resolution_fact_fails_validation():
    with pytest.raises(ValidationError):
        ConfirmedExecutionContext(session_id="handoff-session", facts={
            "address_resolution": ConfirmedFact(value="unstructured resolution", provenance="test", status=FactStatus.CONFIRMED, allowed_for_execution=True),
        })


def test_resolved_pin_cannot_be_attached_to_different_confirmed_pin():
    with pytest.raises(ValidationError, match="postal PIN"):
        confirmed(resolution(), pincode=field("560001")).to_execution_context("handoff-session")


def test_resolved_new_address_cannot_survive_different_user_correction():
    with pytest.raises(ValidationError, match="confirmed new address"):
        confirmed(resolution({"new_address": ADDRESS}), new_address=field("Different Address")).to_execution_context("handoff-session")


def test_resolution_metadata_reaches_session_context_without_browser_behavior_change():
    async def run():
        manager = InteractivePortalManager()
        manager._launch_and_navigate_login = AsyncMock()
        ctx = ConfirmedExecutionContext.model_validate_json(context(resolution()).model_dump_json())
        await manager.start_session(ctx)
        session = manager._sessions[ctx.session_id]
        assert session.context.facts["address_resolution"].value == ctx.address_resolution
        assert session.context.address_resolution == ctx.address_resolution
        assert session.context.facts["new_address"].value == ADDRESS
    asyncio.run(run())


def extraction():
    def extracted(value):
        return ExtractedField(value=value, confidence=0.95, source_document_id="test-document")
    return ExtractionResult(document_id="test-document", status=ExtractionStatus.SUCCESS,
        data=AadhaarExtractedData(name=extracted("Test Name"), date_of_birth=extracted("01/01/1990"),
            existing_address=extracted("Old Address"), new_address=extracted(ADDRESS), pincode=extracted(PIN)))


def test_document_confirmation_service_accepts_optional_result_and_preserves_legacy_call():
    service = AadhaarDocumentService(extractor=Mock())
    result = resolution()
    legacy = service.confirm(extraction())
    attached = service.confirm(extraction(), address_resolution=result)
    assert legacy.address_resolution is None
    assert attached.address_resolution == result
    assert attached.to_execution_context("handoff-session").address_resolution == result


@pytest.fixture
def api_module():
    # api.app normally instantiates the production runtime/OCR at import.
    # Stub only those import-time factories; tests exercise the real route/model.
    with patch("agents.orchestration.pipeline.create_production_orchestrator", return_value=Mock()), \
         patch("agents.orchestration.document_input.AadhaarDocumentService", return_value=Mock()):
        return importlib.import_module("api.app")


def test_confirmation_api_carries_optional_resolution_and_session_launch_keeps_it(api_module):
    service = AadhaarDocumentService(extractor=Mock())
    app = api_module.create_app(document_service=service)
    client = TestClient(app)
    result = resolution()
    response = client.post("/api/documents/aadhaar/confirm", json={
        "confirmed": True, "session_id": "handoff-session", "extraction": extraction().model_dump(mode="json"),
        "address_resolution": result.model_dump(mode="json"),
    })
    assert response.status_code == 200
    raw_context = response.json()["confirmed_context"]
    assert raw_context["facts"]["address_resolution"]["value"] == result.model_dump(mode="json")
    ctx = ConfirmedExecutionContext.model_validate(raw_context)
    from agents.utility_based.execution_assistance.interactive_session import interactive_manager
    with patch.object(interactive_manager, "_launch_and_navigate_login", new=AsyncMock()):
        try:
            response = client.post("/api/browser/launch-uidai", json={"confirmed_context": raw_context})
            assert response.status_code == 200
            assert interactive_manager._sessions[ctx.session_id].context.address_resolution == result
        finally:
            interactive_manager._sessions.pop(ctx.session_id, None)


def test_confirmation_api_legacy_payload_still_has_no_resolution_fact(api_module):
    client = TestClient(api_module.create_app(document_service=AadhaarDocumentService(extractor=Mock())))
    response = client.post("/api/documents/aadhaar/confirm", json={"confirmed": True, "extraction": extraction().model_dump(mode="json")})
    assert response.status_code == 200
    assert "address_resolution" not in response.json()["confirmed_context"]["facts"]


def test_confirmation_api_rejects_stale_resolution_after_pin_correction(api_module):
    client = TestClient(api_module.create_app(document_service=AadhaarDocumentService(extractor=Mock())))
    response = client.post("/api/documents/aadhaar/confirm", json={
        "confirmed": True, "extraction": extraction().model_dump(mode="json"),
        "corrections": {"pincode": "560001"}, "address_resolution": resolution().model_dump(mode="json"),
    })
    assert response.status_code == 400
