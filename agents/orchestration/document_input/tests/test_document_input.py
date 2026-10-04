from agents.knowledge_based.information_retrieval.document_understanding.ocr_engine import MockOCREngine
from agents.orchestration.document_input import (
    AadhaarDocumentExtractor,
    AadhaarDocumentInput,
    AadhaarDocumentService,
    ExtractionStatus,
    FieldProvenance,
)


DOCUMENT_TEXT = """UIDAI Aadhaar
Name: Ramesh Kumar
DOB: 15/08/1985
Gender: MALE
1234 5678 9012
Address: 12 Main Street, Chennai 600001
"""


def service_with_text(text=DOCUMENT_TEXT):
    extractor = AadhaarDocumentExtractor(ocr_engine=MockOCREngine(text, 0.98))
    return AadhaarDocumentService(extractor)


def document(filename="aadhaar.png", content=b"image-bytes"):
    return AadhaarDocumentInput(filename=filename, content=content)


def test_valid_document_extraction():
    result = service_with_text().extract(document())

    assert result.status == ExtractionStatus.SUCCESS
    assert result.data is not None
    assert result.data.name is not None
    assert result.data.existing_address is not None
    assert result.data.name.provenance == FieldProvenance.EXTRACTED_FROM_DOCUMENT


def test_missing_field_is_reported_without_fabrication():
    result = service_with_text(DOCUMENT_TEXT.replace("Address: 12 Main Street, Chennai 600001", "")).extract(document())

    assert result.status == ExtractionStatus.MISSING_REQUIRED_FIELDS
    assert "existing_address" in result.missing_fields
    assert result.data.existing_address is None


def test_extraction_failure_when_ocr_is_unavailable():
    result = AadhaarDocumentService().extract(document())

    assert result.status == ExtractionStatus.EXTRACTION_FAILED
    assert result.data is None


def test_malformed_document():
    result = service_with_text().extract(document(filename="aadhaar.pdf", content=b"not-a-pdf"))

    assert result.status == ExtractionStatus.MALFORMED_DOCUMENT
    assert result.data is None


def test_aadhaar_number_is_masked():
    result = service_with_text().extract(document())

    assert result.data.masked_aadhaar.value == "XXXX-XXXX-9012"
    assert "1234 5678 9012" not in result.model_dump_json()
    assert "123456789012" not in result.model_dump_json()


def test_extracted_data_is_not_confirmed_automatically():
    result = service_with_text().extract(document())

    assert result.data.name.provenance == FieldProvenance.EXTRACTED_FROM_DOCUMENT
    assert result.data.name.provenance != FieldProvenance.USER_CONFIRMED


def test_explicit_confirmation_produces_confirmed_context():
    service = service_with_text()
    extracted = service.extract(document())

    confirmed = service.confirm(extracted)
    context = confirmed.to_execution_context("session-1")

    assert confirmed.name.provenance == FieldProvenance.USER_CONFIRMED
    assert context.facts["name"].status.value == "confirmed"
    assert context.facts["name"].allowed_for_execution is True
    assert context.facts["name"].provenance == "user_confirmed"


def test_user_correction_produces_corrected_provenance():
    service = service_with_text()
    extracted = service.extract(document())

    confirmed = service.confirm(extracted, {"existing_address": "99 Corrected Road"})

    assert confirmed.existing_address.value == "99 Corrected Road"
    assert confirmed.existing_address.provenance == FieldProvenance.USER_CORRECTED
    assert confirmed.name.provenance == FieldProvenance.USER_CONFIRMED


def test_downstream_context_contains_only_confirmed_facts():
    service = service_with_text()
    extracted = service.extract(document())
    confirmed = service.confirm(extracted)

    context = confirmed.to_execution_context("session-1")

    assert set(context.facts) == {"name", "date_of_birth", "gender", "masked_aadhaar", "existing_address"}
    assert all(fact.allowed_for_execution for fact in context.facts.values())
    assert all(fact.status.value == "confirmed" for fact in context.facts.values())
    assert all("1234 5678 9012" not in str(fact.value) for fact in context.facts.values())
