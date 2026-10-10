from unittest.mock import Mock
from agents.knowledge_based.information_retrieval.agent import InformationRetrievalAgent
from agents.knowledge_based.information_retrieval.document_understanding.pipeline import UserDocumentPipeline
from agents.knowledge_based.information_retrieval.document_understanding.ocr_engine import MockOCREngine
from agents.orchestration.document_input.tests.test_document_input import DOCUMENT_TEXT


def test_file_input_reaches_real_process_file(tmp_path):
    path = tmp_path / "aadhaar.png"
    path.write_bytes(b"synthetic-image")
    agent = object.__new__(InformationRetrievalAgent)
    pipeline = UserDocumentPipeline(ocr_engine=MockOCREngine(DOCUMENT_TEXT, 0.98))
    pipeline.process_file = Mock(wraps=pipeline.process_file)
    agent.doc_pipeline = pipeline
    result = agent._parse_user_document_item(str(path))
    pipeline.process_file.assert_called_once_with(file_path=str(path))
    assert result.extracted_text == DOCUMENT_TEXT
    assert result.extracted_fields["address"].value


def test_structured_file_input_keeps_known_document_id(tmp_path):
    from agents.knowledge_based.information_retrieval.schemas.retrieval_request import UserDocumentInput
    path = tmp_path / "aadhaar.png"
    path.write_bytes(b"synthetic-image")
    agent = object.__new__(InformationRetrievalAgent)
    agent.doc_pipeline = UserDocumentPipeline(ocr_engine=MockOCREngine(DOCUMENT_TEXT, 0.98))
    result = agent._parse_user_document_item(UserDocumentInput(document_id="known-source", file_path=str(path), document_type="aadhaar"))
    assert result.document_id == "known-source"
    assert result.extracted_fields["address"].value
