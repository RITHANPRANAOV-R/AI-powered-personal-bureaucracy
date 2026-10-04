from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from agents.orchestration.document_input import (
    AadhaarDocumentInput,
    AadhaarDocumentService,
    ExtractionResult,
    ExtractionStatus,
)
from agents.orchestration.pipeline import OrchestrationResult, OrchestrationStatus
from api.app import create_app
from demo.runtime import create_demo_orchestrator


class RecordingDocumentService:
    def __init__(self, extraction: ExtractionResult):
        self.extraction = extraction
        self.extraction_calls = []
        self.confirm_calls = []

    def extract(self, document: AadhaarDocumentInput):
        self.extraction_calls.append(document)
        return self.extraction

    def confirm(self, extraction, corrections):
        self.confirm_calls.append((extraction, corrections))
        raise AssertionError("Use the real confirmation service in confirmation tests.")


class RecordingOrchestrator:
    def __init__(self, result: OrchestrationResult):
        self.result = result
        self.calls = []

    def run(self, request):
        self.calls.append(request)
        return self.result


def extraction_result():
    return ExtractionResult(
        status=ExtractionStatus.SUCCESS,
        document_id="doc-1",
        data={
            "name": {"value": "Ramesh Kumar", "confidence": 0.9, "source_document_id": "doc-1"},
            "existing_address": {"value": "12 Main Street", "confidence": 0.8, "source_document_id": "doc-1"},
            "masked_aadhaar": {"value": "XXXX-XXXX-9012", "confidence": 0.95, "source_document_id": "doc-1"},
        },
    )


def test_upload_reaches_existing_document_service_without_raw_response():
    extraction = extraction_result()
    service = RecordingDocumentService(extraction)
    client = TestClient(create_app(document_service=service, orchestrator=None))

    response = client.post(
        "/api/documents/aadhaar/extract",
        files={"file": ("aadhaar.png", b"private-document-bytes", "image/png")},
    )

    assert response.status_code == 200
    assert service.extraction_calls[0].filename == "aadhaar.png"
    assert service.extraction_calls[0].content == b"private-document-bytes"
    assert "extracted_text" not in response.json()
    assert response.json()["data"]["masked_aadhaar"]["value"] == "XXXX-XXXX-9012"
    assert "private-document-bytes" not in response.text


def test_confirmation_requires_explicit_confirmation():
    service = AadhaarDocumentService()
    client = TestClient(create_app(document_service=service, orchestrator=None))

    response = client.post(
        "/api/documents/aadhaar/confirm",
        json={"confirmed": False, "extraction": extraction_result().model_dump(mode="json")},
    )

    assert response.status_code == 400
    assert "explicit confirmation" in response.json()["detail"].lower()


def test_confirmation_returns_confirmed_and_corrected_provenance():
    service = AadhaarDocumentService()
    client = TestClient(create_app(document_service=service, orchestrator=None))

    response = client.post(
        "/api/documents/aadhaar/confirm",
        json={
            "confirmed": True,
            "session_id": "session-1",
            "extraction": extraction_result().model_dump(mode="json"),
            "corrections": {"existing_address": "99 Corrected Road"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["confirmed_data"]["name"]["provenance"] == "user_confirmed"
    assert body["confirmed_data"]["existing_address"]["provenance"] == "user_corrected"
    assert body["confirmed_context"]["facts"]["existing_address"]["allowed_for_execution"] is True


def test_orchestration_route_reaches_existing_pipeline_and_preserves_status():
    result = OrchestrationResult(
        request_id="session-1",
        status=OrchestrationStatus.AWAITING_HUMAN_ACTION,
        blocking_reason="Manual review is required.",
    )
    orchestrator = RecordingOrchestrator(result)
    client = TestClient(create_app(document_service=None, orchestrator=orchestrator))

    response = client.post(
        "/api/orchestration/run",
        json={
            "user_request": {
                "session_id": "session-1",
                "user_message": "Update my Aadhaar address",
                "domain": "aadhaar",
            },
            "confirmed_context": {"session_id": "session-1"},
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "awaiting_human_action"
    assert orchestrator.calls[0].confirmed_context.session_id == "session-1"


def test_orchestration_runtime_unavailable_fails_safely():
    client = TestClient(create_app(document_service=None, orchestrator=None))

    response = client.post(
        "/api/orchestration/run",
        json={
            "user_request": {
                "session_id": "session-1",
                "user_message": "Update my Aadhaar address",
                "domain": "aadhaar",
            },
            "confirmed_context": {"session_id": "session-1"},
        },
    )

    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_local_demo_runtime_reaches_real_orchestration_pipeline():
    client = TestClient(create_app(orchestrator=create_demo_orchestrator()))

    response = client.post(
        "/api/orchestration/run",
        json={
            "user_request": {
                "session_id": "local-demo-session",
                "user_message": "Update my Aadhaar address to 12 Main Street",
                "domain": "aadhaar",
            },
            "confirmed_context": {"session_id": "local-demo-session"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "execution_completed"
    assert body["integration_result"]["compliance_decision"]["allowed"] is True
    assert body["integration_result"]["execution_result"]["status"] == "completed"
    assert "123456789012" not in response.text


def test_invalid_upload_fails_safely():
    client = TestClient(create_app(document_service=None, orchestrator=None))

    response = client.post(
        "/api/documents/aadhaar/extract",
        files={"file": ("document.exe", b"private-document-bytes", "application/octet-stream")},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "unsupported_document"
    assert "private-document-bytes" not in response.text


def test_document_input_does_not_log_raw_content():
    service = AadhaarDocumentService()
    records = []
    handler = logging.Handler()
    handler.emit = lambda record: records.append(record.getMessage())
    logger = logging.getLogger()
    logger.addHandler(handler)
    try:
        service.extract(AadhaarDocumentInput(filename="aadhaar.png", content=b"987654321012"))
    finally:
        logger.removeHandler(handler)

    assert all("987654321012" not in record for record in records)
