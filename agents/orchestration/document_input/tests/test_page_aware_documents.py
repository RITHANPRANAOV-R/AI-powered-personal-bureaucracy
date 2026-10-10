import io
from types import SimpleNamespace
from unittest.mock import Mock, patch

import fitz
import pytest
from PIL import Image
from agents.knowledge_based.information_retrieval.document_understanding.ocr_engine import BaseOCREngine, OCRLine
from agents.knowledge_based.information_retrieval.ingestion.parser import DocumentParser
from agents.orchestration.document_input import AadhaarDocumentExtractor, AadhaarDocumentInput, AadhaarDocumentService, ExtractionStatus, FieldProvenance
from agents.utility_based.execution_assistance.schema import ConfirmedExecutionContext

IDENTITY = "UIDAI Aadhaar\nName: Arun Raman\nDOB: 15/08/1985\nGender: MALE\n1234 5678 9012"
ADDRESS = "Address: 12 Synthetic Street, Example City, Chennai 600001"
BOX = [[1, 2], [30, 2], [30, 10], [1, 10]]

class PageOCR(BaseOCREngine):
    def __init__(self, texts=None, fail_pages=()):
        self.texts, self.fail_pages, self.calls = texts or {}, fail_pages, []
    def extract_text_from_image(self, image_bytes):
        return "", 0.0
    def extract_lines_from_image(self, image_bytes, page_number=1):
        self.calls.append(page_number)
        assert image_bytes.startswith(b"\x89PNG")
        if page_number in self.fail_pages: raise RuntimeError("synthetic OCR failure")
        return [OCRLine(text=line, confidence=0.98, page_number=page_number, bbox=BOX)
                for line in self.texts.get(page_number, "").splitlines()]

def pdf_document(pages):
    with fitz.open() as pdf:
        for text in pages:
            page = pdf.new_page()
            if text is None:
                with Image.new("RGB", (200, 100), "white") as image:
                    buffer = io.BytesIO()
                    image.save(buffer, format="PNG")
                    page.insert_image(fitz.Rect(50, 50, 250, 150), stream=buffer.getvalue())
            else: page.insert_text((50, 50), text)
        return AadhaarDocumentInput(filename="synthetic.pdf", content=pdf.tobytes())

def extract(pages, engine=None):
    engine = engine or PageOCR()
    service = AadhaarDocumentService(AadhaarDocumentExtractor(ocr_engine=engine))
    return service.extract(pdf_document(pages)), engine, service

def test_text_only_two_pages_preserves_later_address_and_pin():
    result, engine, _ = extract([IDENTITY, ADDRESS])
    assert result.status == ExtractionStatus.SUCCESS
    assert engine.calls == []
    assert result.data.name.page_number == result.data.date_of_birth.page_number == 1
    assert result.data.existing_address.page_number == 2
    assert "600001" in result.data.existing_address.value
    assert result.data.pincode.value == "600001"
    assert result.data.pincode.page_number == 2
    assert result.data.pincode.source_document_id == result.document_id
    assert result.data.pincode.provenance == FieldProvenance.EXTRACTED_FROM_DOCUMENT
    assert result.data.pincode.provenance != FieldProvenance.USER_CORRECTED
    assert result.data.name.value == "Arun Raman"  # Earlier-page identity remains separate.
    assert len(result.pages) == 2

def test_mixed_pdf_does_not_skip_scanned_later_page():
    result, engine, _ = extract([IDENTITY, None], PageOCR({2: ADDRESS}))
    assert result.status == ExtractionStatus.SUCCESS
    assert engine.calls == [2]
    assert result.pages[0].extraction_method == "direct_text"
    assert result.pages[1].extraction_method == "ocr"
    assert result.data.existing_address.page_number == 2
    assert "600001" in result.data.existing_address.value
    assert result.pages[1].ocr_lines[0]["bbox"] == BOX

def test_image_only_multipage_pdf_ocr_processes_each_page():
    result, engine, _ = extract([None, None], PageOCR({1: IDENTITY, 2: ADDRESS}))
    assert result.status == ExtractionStatus.SUCCESS
    assert engine.calls == [1, 2]
    assert result.data.name.page_number == 1
    assert result.data.existing_address.page_number == 2

@pytest.mark.parametrize("bad", ["\ufffd" * 80, "(cid:123) " * 20, "!!!???" * 20, "x" * 100, "\x00" * 40])
def test_corrupted_direct_text_triggers_page_ocr(bad):
    document = pdf_document([IDENTITY, None])
    reader = SimpleNamespace(metadata=None, pages=[Mock(extract_text=Mock(return_value=IDENTITY)), Mock(extract_text=Mock(return_value=bad))])
    engine = PageOCR({2: ADDRESS})
    with patch("pypdf.PdfReader", return_value=reader):
        result = AadhaarDocumentExtractor(ocr_engine=engine).extract(document)
    assert engine.calls == [2]
    assert result.status == ExtractionStatus.SUCCESS
    assert result.data.existing_address.page_number == 2

def test_failed_page_preserves_successful_fields_without_fabricating_missing_values():
    result, _, _ = extract([IDENTITY, None], PageOCR(fail_pages={2}))
    assert result.status == ExtractionStatus.MISSING_REQUIRED_FIELDS
    assert result.data.name.value == "Arun Raman" and result.data.name.page_number == 1
    assert result.data.existing_address is result.data.new_address is result.data.pincode is None
    assert result.pages[1].extraction_method == "unreadable"
    assert any("Page 2" in warning for warning in result.warnings)

def test_failed_middle_page_does_not_skip_later_page():
    result, engine, _ = extract([IDENTITY, None, None], PageOCR({3: ADDRESS}, fail_pages={2}))
    assert engine.calls == [2, 3]
    assert result.data.existing_address.page_number == 3
    assert result.warnings and len(result.pages) == 3

def test_confirmation_and_json_context_preserve_page_and_box_evidence():
    result, _, service = extract([IDENTITY, None], PageOCR({2: ADDRESS}))
    confirmed = service.confirm(result)
    assert confirmed.name.page_number == 1 and confirmed.existing_address.page_number == 2
    ctx = ConfirmedExecutionContext.model_validate_json(confirmed.to_execution_context("synthetic-session").model_dump_json())
    evidence = ctx.facts["document_evidence"]
    assert not evidence.allowed_for_execution
    assert evidence.value["fields"]["existing_address"]["page_number"] == 2
    assert evidence.value["pages"][1]["ocr_lines"][0]["bbox"] == BOX
    confirmed.pages[1].ocr_lines[0]["bbox"][0][0] = 999
    assert result.pages[1].ocr_lines[0]["bbox"][0][0] == 1

def test_user_correction_does_not_claim_original_document_location():
    result, _, service = extract([IDENTITY, ADDRESS])
    confirmed = service.confirm(result, {"name": "Corrected Arun Raman"})
    assert confirmed.name.provenance == FieldProvenance.USER_CORRECTED
    assert confirmed.name.page_number is None
    assert confirmed.existing_address.page_number == 2
    assert confirmed.pages[0].raw_text

def test_pdfium_rendering_fallback_is_page_scoped():
    document = pdf_document([IDENTITY, None])
    engine = PageOCR({2: ADDRESS})
    with patch("fitz.open", side_effect=RuntimeError("synthetic unavailable renderer")):
        result = AadhaarDocumentExtractor(ocr_engine=engine).extract(document)
    assert engine.calls == [2]
    assert result.data.existing_address.page_number == 2

def test_sparse_readable_pin_page_survives_failed_ocr():
    result, engine, _ = extract([IDENTITY, "600001"])
    assert engine.calls == [2]
    assert result.pages[1].raw_text.strip() == "600001" and result.pages[1].warnings
    assert result.data.name.page_number == 1

def test_page_text_exception_affects_only_that_page():
    document = pdf_document([IDENTITY, None])
    reader = SimpleNamespace(metadata=None, pages=[Mock(extract_text=Mock(return_value=IDENTITY)), Mock(extract_text=Mock(side_effect=ValueError("synthetic text error")))])
    with patch("pypdf.PdfReader", return_value=reader):
        result = AadhaarDocumentExtractor(ocr_engine=PageOCR({2: ADDRESS})).extract(document)
    assert result.data.name.page_number == 1 and result.data.existing_address.page_number == 2

def test_parser_metadata_uses_individual_pages_not_total_text():
    parsed = DocumentParser().parse_pdf(pdf_document([IDENTITY, None]).content)
    assert parsed.is_ocr_required
    assert not parsed.pages[0].is_ocr_required and parsed.pages[1].is_ocr_required


@pytest.mark.parametrize("reference,full,masked,vid", [
    ("XXXX XXXX 9012", False, True, False),
    ("XXXX XXXX 9012\nVID: 9123 4567 8901 2345", False, True, True),
    ("VID: 9123 4567 8901 2345", False, False, True),
    ("1234 5678 9012", True, False, False),
])
def test_multipage_reference_types_remain_distinct(reference, full, masked, vid):
    identity = IDENTITY.replace("1234 5678 9012", reference)
    result, _, _ = extract([identity, ADDRESS])
    assert (result.data.aadhaar_number is not None) is full
    assert (result.data.masked_aadhaar is not None) is masked
    assert (result.data.vid is not None) is vid
    for field in (result.data.aadhaar_number, result.data.masked_aadhaar, result.data.vid):
        if field is not None: assert field.page_number == 1


def test_existing_source_region_survives_mapping_confirmation_and_context():
    from agents.knowledge_based.information_retrieval.schemas.user_document import ExtractedField as RawField
    result, _, service = extract([IDENTITY, ADDRESS])
    raw = RawField(field_name="name", value="Arun Raman", page_number=1, source_region="fixture-existing-region", confidence=0.95)
    result.data.name = service.extractor._map_field(raw, result.document_id, "name")
    confirmed = service.confirm(result)
    assert confirmed.name.source_region == "fixture-existing-region"
    metadata = confirmed.to_execution_context("synthetic").facts["document_evidence"].value
    assert metadata["fields"]["name"]["source_region"] == "fixture-existing-region"


def test_field_extraction_failure_preserves_other_page_fields():
    document = pdf_document([IDENTITY, ADDRESS])
    extractor = AadhaarDocumentExtractor(ocr_engine=PageOCR())
    original = extractor.field_extractor.extract_fields
    def page_fields(text, *args, **kwargs):
        if kwargs["page_number"] == 2: raise ValueError("synthetic field failure")
        return original(text, *args, **kwargs)
    with patch.object(extractor.field_extractor, "extract_fields", side_effect=page_fields):
        result = extractor.extract(document)
    assert result.data.name.page_number == 1
    assert result.data.existing_address is None
    assert result.status == ExtractionStatus.MISSING_REQUIRED_FIELDS
    assert result.pages[1].raw_text and result.warnings


def test_corrupted_ocr_text_does_not_fabricate_missing_fields():
    result, _, _ = extract([IDENTITY, None], PageOCR({2: "(cid:123) " * 30}))
    assert result.data.name.page_number == 1
    assert result.data.existing_address is None
    assert result.pages[1].extraction_method == "unreadable"



def test_default_ocr_page_number_is_corrected_without_mutating_engine_evidence():
    from agents.knowledge_based.information_retrieval.document_understanding.ocr_engine import MockOCREngine
    line = OCRLine(text=ADDRESS, confidence=0.98, page_number=1, bbox=BOX)
    result, _, _ = extract([IDENTITY, None], MockOCREngine(preset_lines=[line]))
    assert result.data.existing_address.page_number == 2
    assert result.pages[1].ocr_lines[0]["page_number"] == 2
    assert line.page_number == 1 and line.bbox == BOX
