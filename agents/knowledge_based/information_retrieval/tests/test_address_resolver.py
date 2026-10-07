"""Phase 5C-2 contract tests; no live API, LLM, browser, or execution calls."""
from copy import deepcopy
from unittest.mock import Mock

import httpx
import pytest

from agents.knowledge_based.information_retrieval.config import RetrievalConfig
from agents.knowledge_based.information_retrieval.live_retrieval.india_post_fetcher import (
    IndiaPostLocationFetcher, OGD_RESOURCE_ID, OGD_URL, PostalLookupResult,
    PostalLookupStatus, PostalRecord,
)
from agents.knowledge_based.information_retrieval.retrieval.address_resolver import PostalAddressResolver
from agents.knowledge_based.information_retrieval.schemas.address_resolution import (
    AddressFieldStatus as FieldStatus, AddressResolutionResult,
    AddressResolutionStatus as Status,
)
from agents.knowledge_based.information_retrieval.schemas.source import Source, SourceType
from agents.knowledge_based.information_retrieval.schemas.user_document import ExtractedField, UserDocument
from agents.orchestration.document_input.schema import (
    AadhaarConfirmedData, AadhaarExtractedData, ConfirmedField,
    ExtractedField as AadhaarExtractedField, FieldProvenance,
)

PIN = "110001"
TIMESTAMP = "2026-10-08T00:00:00+00:00"


def postal_record(office="Alpha Office", **changes):
    data = dict(pincode=PIN, state_name="Test State", district="Test District",
                office_name=office, taluka="Test Taluka", circle="Test Circle",
                division="Test Division", region="Test Region")
    data.update(changes)
    return PostalRecord(**data, source_record={"synthetic_record_id": office, **data})


def lookup(records=None, status=None, **changes):
    records = [postal_record()] if records is None else records
    data = dict(
        status=status or (PostalLookupStatus.MULTIPLE_RECORDS if len(records) > 1 else PostalLookupStatus.SUCCESS),
        queried_pin=PIN, records=records, retrieved_at=TIMESTAMP,
        source=Source(source_id="india-post-all-india-pincode-directory", domain="india_post",
                      authority="Department of Posts, Government of India", url=OGD_URL,
                      source_type=SourceType.GOVERNMENT_API, last_checked=TIMESTAMP),
    )
    data.update(changes)
    return PostalLookupResult(**data)


def resolve(context=None, records=None, **changes):
    return PostalAddressResolver().resolve(PIN, context, lookup(records, **changes))


def test_single_postal_record_resolves_postal_fields():
    result = resolve()
    assert result.status == Status.RESOLVED
    assert result.state.value == "Test State"
    assert result.district.value == "Test District"
    assert result.post_office.value == "Alpha Office"
    assert result.plausible_candidate_indexes == [0]


def test_locality_narrows_to_second_office_without_discarding_records():
    records = [postal_record(), postal_record("Beta Office")]
    result = resolve({"locality": "Beta Office"}, records)
    assert result.status == Status.RESOLVED
    assert result.post_office.value == "Beta Office"
    assert result.plausible_candidate_indexes == [1]
    assert result.candidates == records
    assert "context-locality" in result.narrowing_evidence_ids
    assert "context-locality" in result.post_office.evidence_ids


def test_matching_office_can_narrow_when_taluka_is_absent():
    result = resolve({"locality": "Beta Office"}, [postal_record(taluka=None), postal_record("Beta Office", taluka=None)])
    assert result.post_office.value == "Beta Office"
    assert result.status == Status.RESOLVED


def test_multiple_offices_without_context_are_ambiguous_but_common_fields_resolve():
    records = [postal_record(), postal_record("Beta Office")]
    result = resolve(records=records)
    assert result.status == Status.AMBIGUOUS
    assert result.state.status == result.district.status == FieldStatus.RESOLVED
    assert result.post_office.status == FieldStatus.AMBIGUOUS
    assert result.post_office.value is None
    assert result.candidates == records and result.plausible_candidate_indexes == [0, 1]


@pytest.mark.parametrize("topic,context", [("state", {"state": "Other State"}),
                                           ("district", {"district": "Other District"}),
                                           ("post_office", {"post_office": "Other Office"})])
def test_explicit_component_conflicts_are_not_overwritten(topic, context):
    before = deepcopy(context)
    result = resolve(context)
    assert result.status == Status.CONFLICT
    assert any(c.topic == topic for c in result.conflicts)
    assert getattr(result, topic).status == FieldStatus.CONFLICT
    assert getattr(result, topic).value is None
    assert context == before and result.context == before
    assert result.candidates[0].office_name == "Alpha Office"


def test_explicit_taluka_conflict():
    result = resolve({"taluka": "Other Taluka"})
    assert result.status == Status.CONFLICT
    assert result.conflicts[0].topic == "taluka"


@pytest.mark.parametrize("pin", ["", "12345", "000001", "1234567", "abcdef", "١١٠٠٠١", 110001, None])
def test_invalid_pin_does_not_call_fetcher(pin):
    fetcher = Mock()
    result = PostalAddressResolver(fetcher).resolve(pin)
    assert result.status == Status.INVALID_PIN
    assert result.candidates == []
    fetcher.lookup.assert_not_called()


def test_empty_postal_result_is_no_result():
    result = resolve(records=[], status=PostalLookupStatus.EMPTY_RESULT)
    assert result.status == Status.NO_RESULT
    assert result.post_office.value is None


@pytest.mark.parametrize("lookup_status", [PostalLookupStatus.NOT_CONFIGURED, PostalLookupStatus.HTTP_ERROR,
    PostalLookupStatus.TIMEOUT, PostalLookupStatus.MALFORMED_RESPONSE, PostalLookupStatus.SOURCE_UNAVAILABLE])
def test_failed_source_is_unavailable_without_resolving_fields(lookup_status):
    result = resolve(records=[], status=lookup_status)
    assert result.status == Status.UNAVAILABLE
    assert result.lookup_status == lookup_status
    assert result.state.value is None and result.post_office.value is None


def test_candidate_order_does_not_choose_an_office():
    records = [postal_record(), postal_record("Beta Office")]
    for ordered in (records, list(reversed(records))):
        result = resolve(records=ordered)
        assert result.status == Status.AMBIGUOUS
        assert result.post_office.value is None
        assert result.post_office.options == ["Alpha Office", "Beta Office"]


def test_taluka_is_never_converted_to_vtc():
    result = resolve({"taluka": "Test Taluka"})
    assert result.status == Status.RESOLVED
    assert result.vtc.value is None and result.vtc.status == FieldStatus.UNRESOLVED
    assert result.vtc_requires_uidai_resolution_or_user_confirmation
    assert result.candidates[0].taluka == "Test Taluka"


def test_missing_vtc_stays_unresolved_and_has_no_authoritative_evidence():
    result = resolve()
    assert result.vtc.value is None and result.vtc.evidence_ids == []
    assert any("VTC" in message for message in result.ambiguity_information)


def test_supplied_vtc_preserved_as_context_not_postal_resolution():
    result = resolve({"vtc": "Test Taluka"})
    assert result.vtc.value == "Test Taluka"
    assert result.vtc.value_origin == "user_document_context"
    assert result.vtc.status == FieldStatus.UNRESOLVED
    assert result.vtc.evidence_ids == ["context-vtc"]
    evidence = next(e for e in result.evidence if e.evidence_id == "context-vtc")
    assert evidence.grounding_status == "unverified"
    assert evidence.source.source_type != "government_api"


def test_unpublished_vtc_is_not_inferred_or_overwritten():
    result = resolve({"vtc": "Unpublished Village"})
    assert result.vtc.value == "Unpublished Village"
    assert result.vtc.status == FieldStatus.UNRESOLVED
    assert result.vtc_requires_uidai_resolution_or_user_confirmation


def test_source_record_provenance_and_serialization():
    returned = lookup()
    result = PostalAddressResolver().resolve(PIN, postal_lookup=returned)
    assert result.source == returned.source
    assert result.source_resource_id == OGD_RESOURCE_ID
    assert result.retrieved_at == TIMESTAMP and result.queried_pin == PIN
    for field in (result.state, result.district, result.post_office):
        assert field.value_origin == "authoritative_postal"
        assert field.supporting_candidate_indexes == [0]
        evidence = next(e for e in result.evidence if e.evidence_id == field.evidence_ids[0])
        assert evidence.source.url == OGD_URL
        assert evidence.retrieved_at == TIMESTAMP
        assert evidence.metadata["resource_id"] == OGD_RESOURCE_ID
        assert evidence.metadata["queried_pin"] == PIN
        assert "synthetic_record_id" in evidence.passage
    assert AddressResolutionResult.model_validate_json(result.model_dump_json()) == result


def test_context_and_lookup_are_not_mutated():
    context = {"district": {"value": "TEST DISTRICT", "confidence": 0.8,
                          "source_document_id": "test-doc", "provenance": "extracted_from_document"}}
    returned = lookup()
    before_context, before_lookup = deepcopy(context), returned.model_dump_json()
    result = PostalAddressResolver().resolve(PIN, context, returned)
    assert context == before_context and returned.model_dump_json() == before_lookup
    assert result.context == before_context
    assert result.district.value == "Test District"


def test_case_whitespace_and_punctuation_normalization():
    result = resolve({"state": "  TEST---STATE ", "district": "test, DISTRICT",
                      "post_office": "alpha.  OFFICE"})
    assert result.status == Status.RESOLVED
    assert result.post_office.value == "Alpha Office"


def test_normalization_does_not_fuzzy_match():
    result = resolve({"post_office": "Alfa Office"})
    assert result.status == Status.CONFLICT


def test_repeated_input_produces_identical_serialized_result():
    resolver = PostalAddressResolver()
    returned = lookup([postal_record(), postal_record("Beta Office")])
    context = {"new_address": "House 2, Beta Office, Test State, 110001"}
    assert resolver.resolve(PIN, context, returned).model_dump_json() == resolver.resolve(PIN, context, returned).model_dump_json()


def test_existing_user_document_fields_reused_with_provenance():
    doc = UserDocument(document_id="test-doc", filename="proof.pdf", mime_type="application/pdf",
        processing_timestamp=TIMESTAMP,
        extracted_fields={"address": ExtractedField(field_name="address", value="House 2, Beta Office", confidence=0.87, page_number=2)})
    original = doc.model_dump_json()
    result = resolve(doc, [postal_record(), postal_record("Beta Office")])
    assert result.post_office.value == "Beta Office"
    evidence = next(e for e in result.evidence if e.evidence_id == "context-address")
    assert evidence.source.source_id == "test-doc"
    assert evidence.confidence == 0.87 and evidence.page_number == 2
    assert evidence.retrieved_at == TIMESTAMP
    assert doc.model_dump_json() == original


def test_existing_aadhaar_extracted_model_reused_without_schema_change():
    field = AadhaarExtractedField(value="House 2, Beta Office", confidence=0.9, source_document_id="test-doc", page_number=1)
    data = AadhaarExtractedData(existing_address=field)
    result = resolve(data, [postal_record(), postal_record("Beta Office")])
    assert result.post_office.value == "Beta Office"
    assert result.context["existing_address"]["source_document_id"] == "test-doc"


def test_existing_aadhaar_confirmed_model_reused_without_execution_handoff():
    field = ConfirmedField(value="House 2, Beta Office", source_document_id="test-doc",
                           provenance=FieldProvenance.USER_CONFIRMED, confirmed_at=TIMESTAMP)
    data = AadhaarConfirmedData(document_id="test-doc", new_address=field)
    before = data.model_dump_json()
    result = resolve(data, [postal_record(), postal_record("Beta Office")])
    assert result.post_office.value == "Beta Office"
    assert data.model_dump_json() == before
    assert "facts" not in result.model_dump()


def test_new_address_takes_precedence_over_old_address_for_context_hints():
    result = resolve({"existing_address": "Alpha Office", "new_address": "Beta Office"},
                     [postal_record(), postal_record("Beta Office")])
    assert result.post_office.value == "Beta Office"
    assert result.context["existing_address"] == "Alpha Office"


def test_explicit_state_can_narrow_consistent_candidate():
    result = resolve({"state": "Second State"}, [postal_record(), postal_record("Beta Office", state_name="Second State")])
    assert result.status == Status.RESOLVED
    assert result.state.value == "Second State" and result.post_office.value == "Beta Office"


def test_combined_context_conflict_is_reported():
    result = resolve({"state": "Test State", "district": "Second District"},
                     [postal_record(), postal_record("Beta Office", state_name="Second State", district="Second District")])
    assert result.status == Status.CONFLICT
    assert result.conflicts[0].topic == "address_context"
    assert result.state.value is None and result.district.value is None


def test_missing_published_field_is_not_treated_as_conflicting_or_resolved():
    result = resolve({"district": "Test District"}, [postal_record(district=None)])
    assert result.status == Status.AMBIGUOUS
    assert result.district.status == FieldStatus.UNRESOLVED
    assert result.district.value is None and result.conflicts == []


def test_unpublished_locality_does_not_create_a_false_conflict():
    result = resolve({"locality": "Unpublished Locality"}, [postal_record(), postal_record("Beta Office")])
    assert result.status == Status.AMBIGUOUS and result.conflicts == []
    assert result.plausible_candidate_indexes == [0, 1]


def test_unknown_location_candidate_remains_plausible():
    result = resolve({"locality": "Beta Office"},
                     [postal_record(office_name=None, taluka=None), postal_record("Beta Office")])
    assert result.status == Status.AMBIGUOUS
    assert result.plausible_candidate_indexes == [0, 1] and result.post_office.value is None


def test_raw_address_match_uses_whole_words_not_substrings():
    result = resolve({"address": "House 2, SuperAlpha Office"}, [postal_record(), postal_record("Beta Office")])
    assert result.status == Status.AMBIGUOUS
    assert result.plausible_candidate_indexes == [0, 1]


def test_lookup_pin_mismatch_does_not_reattribute_evidence():
    result = resolve(queried_pin="560001")
    assert result.status == Status.CONFLICT
    assert result.state.value is None
    assert not any(e.metadata.get("value_origin") == "authoritative_postal" for e in result.evidence)


def test_context_pin_conflict_is_explicit():
    result = resolve({"pincode": "560001"})
    assert result.status == Status.CONFLICT
    assert result.conflicts[0].topic == "pincode"
    assert result.state.value is None


@pytest.mark.parametrize("changes", [{"retrieved_at": None}, {"source_resource_id": "untrusted-resource"}])
def test_missing_or_inconsistent_source_provenance_is_unavailable(changes):
    result = resolve(**changes)
    assert result.status == Status.UNAVAILABLE and result.state.value is None


def test_resolver_uses_phase5c1_fetcher_once_when_lookup_not_supplied():
    fetcher = Mock()
    fetcher.lookup.return_value = lookup()
    result = PostalAddressResolver(fetcher).resolve(PIN)
    fetcher.lookup.assert_called_once_with(PIN)
    assert result.status == Status.RESOLVED


def test_existing_lookup_never_calls_fetcher():
    fetcher = Mock()
    result = PostalAddressResolver(fetcher).resolve(PIN, postal_lookup=lookup())
    fetcher.lookup.assert_not_called()
    assert result.status == Status.RESOLVED


def test_phase5c1_http_contract_integrates_with_resolver_without_network():
    def handle(request):
        assert request.url.params["filters[pincode]"] == PIN
        return httpx.Response(200, json={"total": 2, "records": [
            {"pincode": PIN, "statename": "Test State", "districtname": "Test District", "officename": "Alpha Office"},
            {"pincode": PIN, "statename": "Test State", "districtname": "Test District", "officename": "Beta Office"},
        ]})
    fetcher = IndiaPostLocationFetcher(config=RetrievalConfig(data_gov_in_api_key="synthetic-test-only"), transport=httpx.MockTransport(handle))
    result = PostalAddressResolver(fetcher).resolve(PIN, {"post_office": "Beta Office"})
    assert result.status == Status.RESOLVED and result.post_office.value == "Beta Office"
    assert len(result.candidates) == 2 and result.vtc.value is None
