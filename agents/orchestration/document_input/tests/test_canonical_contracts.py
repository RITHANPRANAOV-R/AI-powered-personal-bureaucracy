"""Canonical extraction/confirmation boundaries; synthetic OCR only."""
import pytest
from agents.orchestration.document_input.tests.test_document_input import service_with_text, document, DOCUMENT_TEXT
from agents.orchestration.document_input.schema import FieldProvenance


def extract(pin="641025", user=None):
    text = DOCUMENT_TEXT.replace("600001", pin)
    service = service_with_text(text)
    return service, service.extract(document(), user_context=user)


def test_document_pin_promoted_with_evidence():
    service, result = extract()
    assert result.data.pincode.value == "641025"
    assert result.data.pincode.provenance == FieldProvenance.EXTRACTED_FROM_DOCUMENT
    assert result.data.pincode.page_number == 1
    assert result.data.pincode.source_document_id == result.document_id
    context = service.confirm(result).to_execution_context("canonical")
    assert context.facts["pincode"].value == "641025"
    assert context.facts["document_evidence"].allowed_for_execution is False


@pytest.mark.parametrize("document_pin", ["641025", ""])
def test_explicit_user_pin_priority(document_pin):
    _, result = extract(document_pin, {"pincode": "641025", "new_address": "New Street 641025"})
    assert result.data.pincode.value == "641025"
    assert result.data.pincode.provenance == FieldProvenance.USER_CONTEXT


def test_conflicting_document_and_user_pin_requires_correction():
    service, result = extract(user={"pincode": "560001"})
    assert result.data.pincode is None
    assert {candidate.value for candidate in result.conflicts["pincode"]} == {"641025", "560001"}
    with pytest.raises(ValueError, match="Explicit correction"):
        service.confirm(result)
    confirmed = service.confirm(result, {"pincode": "560001"})
    assert confirmed.pincode.value == "560001"
    assert confirmed.pincode.provenance == FieldProvenance.USER_CORRECTED


@pytest.mark.parametrize("pin", ["12345", "1234567", "012345", "abcdef", 641025])
def test_invalid_explicit_pin_not_canonical(pin):
    service, result = extract(user={"pincode": pin})
    assert result.data.pincode is None
    assert "pincode" in result.validation_errors
    with pytest.raises(ValueError):
        service.confirm(result)


def test_missing_pin_remains_missing():
    _, result = extract("")
    assert result.data.pincode is None


def test_same_priority_pin_conflict():
    _, result = extract("", {"pincode": "641025", "pin": "560001"})
    assert result.data.pincode is None
    assert "pincode" in result.conflicts


def test_new_address_distinct_and_correction_overrides():
    service, result = extract(user={"new_address": "12 ABC Street, Tamil Nadu 641025"})
    old_address = result.data.existing_address.value
    confirmed = service.confirm(result, {"new_address": "14 Corrected Street, Tamil Nadu 641025"})
    context = confirmed.to_execution_context("canonical")
    assert context.facts["existing_address"].value == old_address
    assert context.facts["new_address"].value == context.facts["address"].value == "14 Corrected Street, Tamil Nadu 641025"
    assert context.facts["new_address"].provenance == "user_corrected"


def test_conflicting_address_aliases_require_correction():
    service, result = extract(user={"new_address": "New A", "address": "New B"})
    assert "new_address" in result.conflicts
    with pytest.raises(ValueError):
        service.confirm(result)


def test_multiple_document_pins_not_guessed():
    _, result = extract("641025 or 560001")
    assert result.data.pincode is None
    assert "pincode" in result.conflicts


def test_derived_request_pin_only_when_document_pin_missing():
    _, result = extract("", {"new_address": "12 ABC Street 641025"})
    assert result.data.pincode.value == "641025"
