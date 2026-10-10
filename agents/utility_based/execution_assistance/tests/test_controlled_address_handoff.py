from agents.utility_based.execution_assistance.tests.review_fixtures import enroll, resolve_review, confirm_review, bind_context
"""Phase 5 controlled metadata handoff; local postal fixtures and mocked pages only."""
import asyncio
import importlib
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from agents.knowledge_based.information_retrieval.live_retrieval.india_post_fetcher import (
    IndiaPostLocationFetcher, OGD_RESOURCE_ID, OGD_URL, PostalLookupResult, PostalRecord)
from agents.knowledge_based.information_retrieval.retrieval.address_resolver import PostalAddressResolver
from agents.knowledge_based.information_retrieval.schemas.address_resolution import AddressResolutionResult
from agents.knowledge_based.information_retrieval.schemas.source import Source
from agents.orchestration.document_input.schema import AadhaarExtractedData, ExtractedField, ExtractionResult
from agents.orchestration.document_input.service import AadhaarDocumentService
from agents.utility_based.execution_assistance.schema import ConfirmedExecutionContext, FactStatus
from agents.utility_based.execution_assistance.interactive_session import (
    ActiveBrowserSession, InteractivePortalManager, PortalStage)

PIN = "110001"
ADDRESS = "  House 2, Test Road, Test Area, 110001  "
STAMP = "2026-01-01T00:00:00+00:00"  # Synthetic fixture date, not a source freshness claim.


def extraction():
    def field(value):
        return ExtractedField(value=value, confidence=.9, source_document_id="synthetic-document", page_number=1)
    return ExtractionResult(document_id="synthetic-document", status="success",
        data=AadhaarExtractedData(name=field("Synthetic Citizen"), date_of_birth=field("01/01/1990"),
             existing_address=field("Original document address"), new_address=field(ADDRESS), pincode=field(PIN)))


def lookup(status="success", records=None, queried_pin=PIN):
    return PostalLookupResult(status=status, queried_pin=queried_pin, retrieved_at=STAMP,
        source=Source(source_id="india-post-all-india-pincode-directory", domain="india_post",
            authority="Department of Posts, Government of India", url=OGD_URL, last_checked=STAMP),
        records=records if records is not None else [PostalRecord(pincode=PIN, state_name="Test State",
             district="Test District", office_name="Alpha Office", taluka="Test Taluka",
             source_record={"pincode": PIN, "officename": "Alpha Office"})])


def service_for(status):
    fetcher = Mock(spec=IndiaPostLocationFetcher)
    result = lookup()
    if status == "ambiguous":
        result = lookup("multiple_records", records=[*result.records,
            result.records[0].model_copy(update={"office_name": "Beta Office"})])
    elif status == "conflict":
        result = lookup(queried_pin="560001")
    elif status == "no_result":
        result = lookup("empty_result", records=[])
    elif status == "unavailable":
        result = lookup("http_error", records=[])
    elif status == "invalid_pin":
        # Lookup-result status, not malformed citizen input.
        result = lookup("invalid_pin", records=[])
    fetcher.lookup.return_value = result
    return AadhaarDocumentService(extractor=Mock(), address_resolver=PostalAddressResolver(fetcher)), fetcher


def test_opt_in_uses_existing_confirmed_pin_and_address_without_overwriting_extraction():
    service, fetcher = service_for("resolved")
    original = extraction()
    before = original.model_dump_json()
    confirmed = service.confirm(original, resolve_address=True)
    fetcher.lookup.assert_called_once_with(PIN)
    context = ConfirmedExecutionContext.model_validate_json(confirmed.to_execution_context("session").model_dump_json())
    assert context.facts["pincode"].value == PIN
    assert context.facts["new_address"].value == context.facts["address"].value == ADDRESS
    assert context.facts["existing_address"].value == "Original document address"
    assert context.address_resolution.context["new_address"]["value"] == ADDRESS
    assert context.address_resolution.context["new_address"]["source_document_id"] == "synthetic-document"
    assert original.model_dump_json() == before
    assert "postal_code" not in context.facts and "authoritative_pincode" not in context.facts


@pytest.mark.parametrize("status", ["resolved", "ambiguous", "conflict", "no_result", "unavailable", "invalid_pin"])
def test_all_resolver_contract_states_survive_confirmation_and_json_handoff(status):
    service, fetcher = service_for(status)
    corrections = {"pincode": PIN} if status == "invalid_pin" else None
    confirmed = service.confirm(extraction(), corrections, resolve_address=True)
    original = confirmed.address_resolution.model_dump(mode="json")
    context = ConfirmedExecutionContext.model_validate_json(confirmed.to_execution_context("session").model_dump_json())
    assert context.address_resolution.status.value == status
    assert context.address_resolution.model_dump(mode="json") == original
    assert not context.facts["address_resolution"].allowed_for_execution
    assert context.facts["pincode"].value == PIN
    assert context.facts["new_address"].value == ADDRESS
    assert context.facts["address"].value == ADDRESS
    assert context.address_resolution.vtc.value is None
    assert context.address_resolution.vtc_requires_uidai_resolution_or_user_confirmation
    if status == "ambiguous":
        assert len(context.address_resolution.candidates) == 2
        assert context.facts["address_resolution"].status == FactStatus.AMBIGUOUS
    if status == "conflict":
        assert context.address_resolution.conflicts
        assert context.facts["address_resolution"].status == FactStatus.CONFLICTING
    if status == "invalid_pin":
        fetcher.lookup.assert_called_once_with(PIN)
        assert context.address_resolution.lookup_status.value == "invalid_pin"
        assert context.address_resolution.state.value is None
        assert context.address_resolution.district.value is None
        assert context.address_resolution.post_office.value is None


def test_malformed_citizen_pin_rejected_before_resolver_lookup():
    service, fetcher = service_for("invalid_pin")
    with pytest.raises(ValueError, match="Corrected PIN must be exactly six digits"):
        service.confirm(extraction(), {"pincode": "11000"}, resolve_address=True)
    fetcher.lookup.assert_not_called()


def test_resolved_result_preserves_official_resource_candidates_and_evidence():
    service, _ = service_for("resolved")
    result = service.confirm(extraction(), resolve_address=True).to_execution_context("session").address_resolution
    assert result.source.url == OGD_URL
    assert result.source_resource_id == OGD_RESOURCE_ID
    assert result.retrieved_at == STAMP
    assert result.candidates[0].source_record == {"pincode": PIN, "officename": "Alpha Office"}
    assert result.state.value == "Test State" and result.district.value == "Test District"
    assert result.post_office.value == "Alpha Office"
    assert result.evidence and result.state.evidence_ids
    assert result.vtc.value is None  # Taluka and PO never substitute for VTC.


def test_legacy_confirmation_does_not_fetch_or_attach_metadata():
    resolver = Mock(spec=PostalAddressResolver)
    service = AadhaarDocumentService(extractor=Mock(), address_resolver=resolver)
    data = service.confirm(extraction())
    resolver.resolve.assert_not_called()
    assert data.address_resolution is None
    assert "address_resolution" not in data.to_execution_context("session").facts


def test_corrections_are_applied_before_resolution_with_no_pin_substitution():
    service, fetcher = service_for("resolved")
    fetcher.lookup.return_value = lookup(records=[], status="empty_result", queried_pin="560001")
    confirmed = service.confirm(extraction(), {"new_address": "Corrected citizen address", "pincode": "560001"}, resolve_address=True)
    fetcher.lookup.assert_called_once_with("560001")
    context = confirmed.to_execution_context("session")
    assert context.facts["pincode"].value == "560001"
    assert context.facts["new_address"].value == "Corrected citizen address"
    assert context.address_resolution.context["new_address"]["value"] == "Corrected citizen address"


def test_missing_pin_is_preserved_and_resolved_as_invalid_without_fetch():
    service, fetcher = service_for("resolved")
    original = extraction()
    original.data.pincode = None
    context = service.confirm(original, resolve_address=True).to_execution_context("session")
    assert context.address_resolution.status.value == "invalid_pin"
    assert "pincode" not in context.facts
    fetcher.lookup.assert_not_called()


def test_existing_metadata_and_requested_resolution_are_mutually_exclusive():
    service, fetcher = service_for("resolved")
    with pytest.raises(ValueError, match="not both"):
        service.confirm(extraction(), resolve_address=True,
            address_resolution=AddressResolutionResult(status="unavailable"))
    fetcher.lookup.assert_not_called()


def api_for(service):
    with patch("agents.orchestration.pipeline.create_production_orchestrator", return_value=Mock()), \
         patch("agents.orchestration.document_input.AadhaarDocumentService", return_value=Mock()):
        api = importlib.import_module("api.app")
    return TestClient(api.create_app(document_service=service))


@pytest.mark.parametrize("status", ["resolved", "ambiguous", "conflict", "no_result", "unavailable", "invalid_pin"])
def test_confirmation_api_opt_in_preserves_pin_and_structured_resolution(status):
    service, fetcher = service_for(status)
    client = api_for(service)
    created, headers = enroll(client, extraction(), {"pincode": PIN} if status == "invalid_pin" else {})
    response = resolve_review(client, created, headers)
    assert response.status_code == 200
    fetcher.lookup.assert_called_once_with(PIN)
    context = ConfirmedExecutionContext.model_validate(response.json()["confirmed_context"])
    assert context.address_resolution.status.value == status
    assert not context.facts["address_resolution"].allowed_for_execution
    assert context.facts["pincode"].value == PIN
    assert context.facts["address"].value == ADDRESS


@pytest.mark.parametrize("status", ["resolved", "ambiguous", "conflict", "no_result", "unavailable", "invalid_pin"])
def test_valid_pin_plus_metadata_does_not_cause_postal_code_missing_or_change_autofill(status):
    service, _ = service_for(status)
    legacy = service.confirm(extraction()).to_execution_context("session")
    if status == "invalid_pin":
        # A previously attached invalid-PIN envelope must never clear today's valid citizen PIN.
        data = service.confirm(extraction(), address_resolution=AddressResolutionResult(status="invalid_pin"))
    else:
        data = service.confirm(extraction(), resolve_address=True)
    enriched = ConfirmedExecutionContext.model_validate_json(data.to_execution_context("session").model_dump_json())
    manager = InteractivePortalManager()
    def facts(ctx): return {key: fact.value for key, fact in ctx.facts.items()}
    baseline = manager._parse_address_components(facts(legacy))
    with_metadata = manager._parse_address_components(facts(enriched))
    assert baseline == with_metadata
    assert with_metadata["pincode"] == PIN  # Regression: the existing postal-code input is never missing.
    async def run(ctx):
        page = Mock()
        page.evaluate = AsyncMock(return_value=False)
        page.wait_for_timeout = AsyncMock()
        manager._smart_fill = AsyncMock(return_value=True)
        manager._select_dropdown_option = AsyncMock(return_value={"status": "needs_user"})
        manager._validate_address_stage = AsyncMock(return_value={"pin_valid": True, "vtc_selected": False, "po_selected": False})
        manager._smart_click_or_submit = AsyncMock()
        session = ActiveBrowserSession(session_id="session", context=ctx, page=page)
        await manager._execute_stage_action_on_portal(session, PortalStage.STAGE_3_ADDRESS)
        calls = manager._smart_fill.await_args_list
        assert any(call.args[2] == PIN and 'input[name*="pincode" i]' in call.args[1] for call in calls)
        manager._smart_click_or_submit.assert_not_awaited()
        return [(call.args[1], call.args[2]) for call in calls], [call.args[1:] for call in manager._select_dropdown_option.await_args_list]
    assert asyncio.run(run(legacy)) == asyncio.run(run(enriched))


def test_resolved_confirmation_metadata_reaches_existing_session_handoff():
    service, _ = service_for("resolved")
    confirmed = service.confirm(extraction(), resolve_address=True)
    context = ConfirmedExecutionContext.model_validate_json(confirmed.to_execution_context("session").model_dump_json())
    async def run():
        manager = InteractivePortalManager()
        manager._launch_and_navigate_login = AsyncMock()
        await manager.start_session(context)
        session = manager._sessions["session"]
        assert session.context.address_resolution == confirmed.address_resolution
        assert session.context.facts["pincode"].value == PIN
        assert session.context.facts["address"].value == ADDRESS
    asyncio.run(run())
