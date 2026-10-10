"""Local synthetic PDF/security regressions; never a UIDAI upload test."""
import io
import os
from pathlib import Path
from unittest.mock import Mock
import pypdf
import pytest
from agents.orchestration.document_input import AadhaarDocumentExtractor, AadhaarDocumentInput, ExtractionStatus
from agents.orchestration.document_input.extractor import MAX_DOCUMENT_SIZE_BYTES
from agents.orchestration.document_input.tests.test_page_aware_documents import pdf_document, PageOCR, IDENTITY, ADDRESS
from agents.knowledge_based.information_retrieval.ingestion.parser import DocumentParser, ParseStatus
from agents.knowledge_based.information_retrieval.document_understanding.pipeline import UserDocumentPipeline
from agents.knowledge_based.information_retrieval.retrieval.linker import RequirementDocumentLinker
from agents.knowledge_based.information_retrieval.tests.test_supporting_requirements import result as requirements


def test_text_pdf_keeps_fields_and_document_confirmation():
    from agents.orchestration.document_input import AadhaarDocumentService
    service=AadhaarDocumentService(AadhaarDocumentExtractor(ocr_engine=PageOCR()))
    result=service.extract(pdf_document([IDENTITY, ADDRESS]))
    assert result.status == ExtractionStatus.SUCCESS
    context=service.confirm(result).to_execution_context('synthetic')
    assert context.facts['document_evidence'].value['fields']['existing_address']['page_number'] == 2
    assert context.facts['pincode'].value == '600001'


def test_scanned_pdf_reaches_existing_page_ocr():
    engine=PageOCR({1:IDENTITY,2:ADDRESS})
    result=AadhaarDocumentExtractor(ocr_engine=engine).extract(pdf_document([None,None]))
    assert result.status == ExtractionStatus.SUCCESS
    assert engine.calls == [1,2]
    assert result.data.existing_address.page_number == 2


def test_corrupt_pdf_never_reaches_ocr_or_fabricates_evidence(tmp_path):
    engine=PageOCR({1:IDENTITY})
    path=tmp_path/'corrupt.pdf'; path.write_bytes(b'not a PDF stream')
    parsed=UserDocumentPipeline(ocr_engine=engine).process_file(str(path))
    assert parsed.ocr_status == 'failed'
    assert parsed.document_type == 'unknown'
    assert parsed.extracted_fields == {} and parsed.overall_confidence == 0
    assert engine.calls == []
    result=AadhaarDocumentExtractor(ocr_engine=engine).extract(AadhaarDocumentInput(filename='corrupt.pdf',content=path.read_bytes()))
    assert result.status == ExtractionStatus.MALFORMED_DOCUMENT


def test_password_protected_pdf_is_distinct_from_corruption(tmp_path):
    writer=pypdf.PdfWriter(); writer.add_blank_page(width=100,height=100); writer.encrypt('synthetic-password')
    output=io.BytesIO(); writer.write(output); blob=output.getvalue()
    parser=DocumentParser()
    assert parser.parse_pdf(blob).status == ParseStatus.ENCRYPTED_PDF
    engine=PageOCR({1:IDENTITY})
    result=AadhaarDocumentExtractor(ocr_engine=engine).extract(AadhaarDocumentInput(filename='locked.pdf',content=blob))
    assert result.status == ExtractionStatus.ENCRYPTED_DOCUMENT
    assert 'password' in result.error.lower()
    path=tmp_path/'locked.pdf';path.write_bytes(blob)
    parsed=UserDocumentPipeline(ocr_engine=engine).process_file(str(path))
    assert parsed.ocr_status == 'failed' and not parsed.extracted_fields
    assert engine.calls == []


def test_empty_and_unreadable_pdf_do_not_become_supported_evidence():
    writer=pypdf.PdfWriter(); output=io.BytesIO();writer.write(output)
    result=AadhaarDocumentExtractor(ocr_engine=PageOCR()).extract(AadhaarDocumentInput(filename='empty.pdf',content=output.getvalue()))
    assert result.status == ExtractionStatus.EXTRACTION_FAILED
    assert 'pages' in result.error
    unreadable=AadhaarDocumentExtractor(ocr_engine=PageOCR()).extract(pdf_document([None]))
    assert unreadable.status == ExtractionStatus.EXTRACTION_FAILED and unreadable.data is None


@pytest.mark.parametrize('mime', [None,'','application/pdf','APPLICATION/PDF; charset=binary','application/octet-stream'])
def test_valid_pdf_mime_boundary(mime):
    document=pdf_document([IDENTITY,ADDRESS]);document.mime_type=mime
    assert AadhaarDocumentExtractor(ocr_engine=PageOCR()).extract(document).status == ExtractionStatus.SUCCESS


@pytest.mark.parametrize('mime',['text/plain','image/png','application/zip'])
def test_mismatched_pdf_mime_rejected_before_parsing(mime):
    parser=Mock();document=pdf_document([IDENTITY]);document.mime_type=mime
    result=AadhaarDocumentExtractor(parser=parser,ocr_engine=PageOCR()).extract(document)
    assert result.status == ExtractionStatus.UNSUPPORTED_DOCUMENT
    parser.extract_pdf_pages.assert_not_called()


def test_unsupported_type_and_size_boundary(monkeypatch):
    extractor=AadhaarDocumentExtractor(ocr_engine=PageOCR())
    assert extractor.extract(AadhaarDocumentInput(filename='file.docx',content=b'synthetic')).status == ExtractionStatus.UNSUPPORTED_DOCUMENT
    document=pdf_document([IDENTITY,ADDRESS])
    import agents.orchestration.document_input.extractor as module
    monkeypatch.setattr(module,'MAX_DOCUMENT_SIZE_BYTES',len(document.content))
    assert extractor.extract(document).status == ExtractionStatus.SUCCESS
    monkeypatch.setattr(module,'MAX_DOCUMENT_SIZE_BYTES',len(document.content)-1)
    assert extractor.extract(document).status == ExtractionStatus.EXTRACTION_FAILED


def test_supporting_mixed_pdf_keeps_later_field_evidence_and_unknown_eligibility(tmp_path):
    # Readable content is not authoritative proof of government acceptance.
    engine=PageOCR({2:'Address: 12 Synthetic Street, Example City 600001'})
    document=pdf_document(['Electricity bill\nName: Synthetic Citizen\nAccount statement',None])
    path=tmp_path/'utility.pdf';path.write_bytes(document.content)
    parsed=UserDocumentPipeline(ocr_engine=engine).process_file(str(path))
    assert parsed.document_type == 'address_proof'
    assert engine.calls == [2]
    assert parsed.extracted_fields['address'].page_number == 2
    assert len(parsed.pages) == 2 and parsed.pages[1]['extraction_method'] == 'ocr'
    from agents.knowledge_based.information_retrieval.schemas.retrieval_result import RetrievalResult
    content_requirement=RetrievalResult(result_id='synthetic',request_id='synthetic',service='address_update',domain='aadhaar',requirements=[{'requirement_id':'address','category':'address','description':'Address evidence'}])
    links=RequirementDocumentLinker().link(content_requirement,[parsed]).links
    address_links=[link for link in links if link.requirement_category == 'address']
    assert address_links
    assert address_links[0].matched_document_id == parsed.document_id
    assert any(field['page_number']==2 for field in address_links[0].matched_fields)
    assert address_links[0].metadata['requirement_validation']['document_eligibility'] == 'unknown'
    official=RequirementDocumentLinker().link(requirements(),[parsed]).links
    assert all(link.metadata['requirement_validation']['status']=='unknown' for link in official)
    assert all(link.matched_document_id is None for link in official)


def test_api_upload_empty_and_size_errors_without_http_or_event_loop(monkeypatch):
    monkeypatch.setenv('AADHAAR_RUNTIME_MODE','demo')
    import importlib
    module=importlib.import_module('api.app')
    from fastapi import HTTPException
    from types import SimpleNamespace
    app=module.create_app(document_service=Mock())
    endpoint=next(r.endpoint for r in app.routes if getattr(r,'path','')=='/api/documents/aadhaar/extract')
    for blob,limit,status in [(b'',10,400),(b'01234567890',10,413)]:
        monkeypatch.setattr(module,'MAX_UPLOAD_BYTES',limit)
        async def read(size): return blob[:size]
        coroutine=endpoint(file=SimpleNamespace(filename='synthetic.pdf',read=read))
        try:
            with pytest.raises(HTTPException) as captured: coroutine.send(None)
            assert captured.value.status_code == status
        finally: coroutine.close()


def test_supplied_local_pdf_with_installed_ocr():
    supplied=os.environ.get('PHASE2_LOCAL_PDF')
    if not supplied: pytest.skip('Private source PDF is opt-in; no personal data is stored in fixtures.')
    result=AadhaarDocumentExtractor().extract(AadhaarDocumentInput(filename='private.pdf',content=Path(supplied).read_bytes(),mime_type='application/pdf'))
    # Assertions disclose only status/field presence, never personal field values.
    assert result.status.value == 'success'
    assert result.data is not None
    for field in ['name','date_of_birth','existing_address']:
        assert getattr(result.data,field) is not None
    assert len(result.pages) == 2
    assert result.data.existing_address.page_number == 2
