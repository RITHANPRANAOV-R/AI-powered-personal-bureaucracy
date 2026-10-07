"""Phase 5C-1 only: every HTTP request uses an in-memory MockTransport."""
import logging

import httpx
import pytest

from agents.knowledge_based.information_retrieval.config import RetrievalConfig
from agents.knowledge_based.information_retrieval.live_retrieval.india_post_fetcher import (
    IndiaPostLocationFetcher, OGD_URL, PostalLookupStatus,
)
from agents.knowledge_based.information_retrieval.sources.source_registry import SourceRegistry

PIN = "110001"
# Explicitly synthetic, nonfunctional test credential, never a real API key.
TEST_CREDENTIAL = "synthetic-unit-test-credential"


def record(office="Synthetic Office A", **extra):
    return {"Pincode": PIN, "StateName": "Synthetic State", "District": "Synthetic District",
            "OfficeName": office, "Taluka": "Synthetic Taluka", "Circle": "Synthetic Circle",
            "Division": "Synthetic Division", "Region": "Synthetic Region", **extra}


def fetcher(handler, key=TEST_CREDENTIAL, registry=None):
    return IndiaPostLocationFetcher(
        config=RetrievalConfig(data_gov_in_api_key=key),
        source_registry=registry,
        transport=httpx.MockTransport(handler),
    )


def response_handler(records, **extra):
    def handle(request):
        assert str(request.url.copy_with(query=None)) == OGD_URL
        assert request.url.params["filters[pincode]"] == PIN
        assert request.url.params["format"] == "json"
        return httpx.Response(200, json={"records": records, "total": len(records), **extra})
    return handle


def test_one_record_and_provenance():
    raw = record(source_record_id="synthetic-record-id")
    registry = SourceRegistry(include_defaults=False)
    result = fetcher(response_handler([raw]), registry=registry).lookup(PIN)
    assert result.status == PostalLookupStatus.SUCCESS
    assert result.queried_pin == PIN
    assert result.source.url == OGD_URL
    assert result.source.authority == "Department of Posts, Government of India"
    assert result.source.source_type == "government_api"
    assert result.retrieved_at and result.source.last_checked == result.retrieved_at
    assert registry.get_source(result.source.source_id) is not None
    candidate = result.records[0]
    assert candidate.source_record == raw
    assert candidate.pincode == PIN
    assert candidate.state_name == "Synthetic State"
    assert candidate.district == "Synthetic District"
    assert candidate.office_name == "Synthetic Office A"
    assert candidate.taluka == "Synthetic Taluka"
    assert candidate.circle == "Synthetic Circle"
    assert candidate.division == "Synthetic Division"
    assert candidate.region == "Synthetic Region"
    assert "vtc" not in candidate.model_dump()


def test_multiple_offices_preserved_without_selection():
    result = fetcher(response_handler([record(), record("Synthetic Office B")])).lookup(PIN)
    assert result.status == PostalLookupStatus.MULTIPLE_RECORDS
    assert [r.office_name for r in result.records] == ["Synthetic Office A", "Synthetic Office B"]
    assert "selected_record" not in result.model_dump()


@pytest.mark.parametrize("invalid", ["12345", "1234567", "000001", " 110001", "110001 ", "abcdef", "١١٠٠٠١", 110001, None])
def test_invalid_pin_never_requests(invalid):
    def unexpected(request):
        pytest.fail("Invalid PIN must not make an HTTP request")
    result = fetcher(unexpected).lookup(invalid)
    assert result.status == PostalLookupStatus.INVALID_PIN
    assert result.records == [] and result.retrieved_at is None


def test_empty_api_result():
    assert fetcher(response_handler([])).lookup(PIN).status == PostalLookupStatus.EMPTY_RESULT


@pytest.mark.parametrize("code", [401, 403, 429, 500, 503, 302])
def test_http_error_and_redirect_not_followed(code):
    result = fetcher(lambda r: httpx.Response(code, headers={"location": "https://untrusted.invalid"})).lookup(PIN)
    assert result.status == PostalLookupStatus.HTTP_ERROR
    assert result.http_status_code == code
    assert result.records == []


def test_timeout():
    def timeout(request):
        raise httpx.ReadTimeout(f"Private request {request.url}", request=request)
    result = fetcher(timeout).lookup(PIN)
    assert result.status == PostalLookupStatus.TIMEOUT
    assert TEST_CREDENTIAL not in result.model_dump_json()


def test_unavailable_api():
    def unavailable(request):
        raise httpx.ConnectError(f"Private request {request.url}", request=request)
    result = fetcher(unavailable).lookup(PIN)
    assert result.status == PostalLookupStatus.SOURCE_UNAVAILABLE
    assert result.records == []


@pytest.mark.parametrize("payload", [None, [], {}, {"records": {} , "total": 1},
    {"records": [record()], "total": True}, {"records": [record()], "total": -1},
    {"records": [record()], "total": 1, "status": "error"},
    {"records": [{"pincode": "999999"}], "total": 1},
    {"records": [record(Region=123)], "total": 1},
    {"records": [], "total": 1}, {"records": [record()], "total": 0}])
def test_malformed_envelope_or_records(payload):
    result = fetcher(lambda r: httpx.Response(200, json=payload)).lookup(PIN)
    assert result.status == PostalLookupStatus.MALFORMED_RESPONSE
    assert result.records == []


def test_malformed_json():
    result = fetcher(lambda r: httpx.Response(200, content=b"{broken")).lookup(PIN)
    assert result.status == PostalLookupStatus.MALFORMED_RESPONSE


def test_missing_optional_fields_are_not_fabricated():
    raw = {"pincode": int(PIN), "officename": "Synthetic Office", "taluka": None}
    result = fetcher(response_handler([raw])).lookup(PIN)
    assert result.status == PostalLookupStatus.SUCCESS
    assert result.records[0].state_name is None
    assert result.records[0].district is None
    assert result.records[0].taluka is None
    assert result.records[0].source_record == raw


def test_lowercase_directory_field_aliases():
    raw = {"pincode": PIN, "statename": "Synthetic State", "districtname": "Synthetic District",
           "officename": "Synthetic Office", "circlename": "Synthetic Circle",
           "divisionname": "Synthetic Division", "regionname": "Synthetic Region"}
    result = fetcher(response_handler([raw])).lookup(PIN)
    assert result.records[0].district == "Synthetic District"
    assert result.records[0].circle == "Synthetic Circle"
    assert result.records[0].division == "Synthetic Division"
    assert result.records[0].region == "Synthetic Region"


def test_pagination_preserves_every_record():
    offsets = []
    def pages(request):
        offset = int(request.url.params["offset"])
        offsets.append(offset)
        return httpx.Response(200, json={"records": [record(f"Synthetic Office {offset}")], "total": "2"})
    result = fetcher(pages).lookup(PIN)
    assert result.status == PostalLookupStatus.MULTIPLE_RECORDS
    assert len(result.records) == 2 and offsets == [0, 1]


def test_second_page_failure_is_not_partial_success():
    def pages(request):
        if request.url.params["offset"] == "0":
            return httpx.Response(200, json={"records": [record()], "total": 2})
        return httpx.Response(503)
    result = fetcher(pages).lookup(PIN)
    assert result.status == PostalLookupStatus.HTTP_ERROR
    assert result.records == []


def test_missing_credential_never_requests():
    def unexpected(request):
        pytest.fail("Missing credentials must not make an HTTP request")
    result = fetcher(unexpected, key=None).lookup(PIN)
    assert result.status == PostalLookupStatus.NOT_CONFIGURED


def test_environment_credential_is_secret_and_excluded(monkeypatch):
    monkeypatch.setenv("DATA_GOV_IN_API_KEY", TEST_CREDENTIAL)
    config = RetrievalConfig()
    assert config.data_gov_in_api_key.get_secret_value() == TEST_CREDENTIAL
    assert TEST_CREDENTIAL not in repr(config)
    assert "data_gov_in_api_key" not in config.model_dump()
    assert TEST_CREDENTIAL not in config.model_dump_json()


def test_api_key_not_exposed_in_httpx_logs_or_result(caplog):
    caplog.set_level(logging.DEBUG)
    result = fetcher(response_handler([record()])).lookup(PIN)
    assert "HTTP Request" in caplog.text  # Exercise real httpx request logging.
    assert TEST_CREDENTIAL not in caplog.text
    assert TEST_CREDENTIAL not in result.model_dump_json()
    assert "[REDACTED]" in caplog.text


def test_error_response_does_not_expose_credential(caplog):
    caplog.set_level(logging.DEBUG)
    result = fetcher(lambda r: httpx.Response(200, json={
        "records": [record()], "total": 1, "error": TEST_CREDENTIAL,
    })).lookup(PIN)
    assert result.status == PostalLookupStatus.MALFORMED_RESPONSE
    assert TEST_CREDENTIAL not in caplog.text + result.model_dump_json()


def test_source_authority_is_scoped_to_postal_domain():
    registry = SourceRegistry(include_defaults=False)
    assert registry.is_authoritative(OGD_URL, "india_post")
    assert not registry.is_authoritative(OGD_URL, "aadhaar")
    assert not registry.is_authoritative("https://api.postalpincode.in/pincode/110001", "india_post")
