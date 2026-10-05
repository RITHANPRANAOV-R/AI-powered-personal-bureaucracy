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
            "date_of_birth": {"value": "15/08/1985", "confidence": 0.9, "source_document_id": "doc-1"},
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


def test_upload_accepts_document_field_name():
    extraction = extraction_result()
    service = RecordingDocumentService(extraction)
    client = TestClient(create_app(document_service=service, orchestrator=None))

    response = client.post(
        "/api/documents/aadhaar/extract",
        files={"document": ("aadhaar.png", b"private-document-bytes", "image/png")},
    )

    assert response.status_code == 200
    assert service.extraction_calls[0].filename == "aadhaar.png"
    assert service.extraction_calls[0].content == b"private-document-bytes"


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


def test_health_check():
    client = TestClient(create_app(document_service=None, orchestrator=None))
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_production_runtime_reaches_otp_and_resumes_to_completion():
    from agents.orchestration.pipeline import create_production_orchestrator

    orchestrator = create_production_orchestrator(require_otp=True)
    client = TestClient(create_app(orchestrator=orchestrator))
    session_id = "prod-test-session-1"

    # Step 1: Initial submission without OTP -> expects Awaiting Human Action / OTP
    confirmed_ctx = {
        "session_id": session_id,
        "document_refs": ["address-proof-doc-1"],
        "facts": {
            "address": {
                "value": "12 Main Street, Bangalore 560001",
                "provenance": "ocr-user-confirmed",
                "status": "confirmed",
                "allowed_for_execution": True,
            }
        },
    }

    res1 = client.post(
        "/api/orchestration/run",
        json={
            "user_request": {
                "session_id": session_id,
                "user_message": "Update my Aadhaar address to 12 Main Street, Bangalore 560001",
                "domain": "aadhaar",
            },
            "confirmed_context": confirmed_ctx,
        },
    )

    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["status"] == "awaiting_human_action"
    assert data1["integration_result"]["compliance_decision"]["allowed"] is True
    assert "OTP" in data1["integration_result"]["execution_result"]["human_intervention"]["reason"]

    # Step 2: Resume with 6-digit OTP -> expects Execution Completed with URN
    confirmed_ctx_with_otp = {
        **confirmed_ctx,
        "facts": {
            **confirmed_ctx["facts"],
            "aadhaar_otp": {
                "value": "123456",
                "provenance": "user-entered-otp",
                "status": "confirmed",
                "allowed_for_execution": True,
            },
        },
    }

    res2 = client.post(
        "/api/orchestration/run",
        json={
            "user_request": {
                "session_id": session_id,
                "user_message": "Update my Aadhaar address to 12 Main Street, Bangalore 560001",
                "domain": "aadhaar",
            },
            "confirmed_context": confirmed_ctx_with_otp,
        },
    )

    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["status"] == "execution_completed"
    assert data2["integration_result"]["compliance_decision"]["allowed"] is True
    exec_steps = data2["integration_result"]["execution_result"]["step_results"]
    urn = next((s["portal_reference"] for s in exec_steps if s.get("portal_reference") and "/" in s.get("portal_reference")), None)
    assert urn is not None
    assert "/" in urn


def test_extract_confirm_and_run_full_flow():
    from agents.orchestration.pipeline import create_production_orchestrator

    orchestrator = create_production_orchestrator(require_otp=True)
    client = TestClient(create_app(orchestrator=orchestrator))
    session_id = "flow-session-101"

    # Step 1: Document Extract
    extraction = extraction_result()
    service = RecordingDocumentService(extraction)
    client_with_service = TestClient(create_app(document_service=AadhaarDocumentService(), orchestrator=orchestrator))

    # Step 2: Confirm extracted data
    confirm_res = client_with_service.post(
        "/api/documents/aadhaar/confirm",
        json={
            "confirmed": True,
            "extraction": extraction.model_dump(mode="json"),
            "corrections": {},
            "session_id": session_id,
        },
    )
    assert confirm_res.status_code == 200
    confirmed_context = confirm_res.json()["confirmed_context"]

    # Step 3: Run pipeline with confirmed context -> Expect OTP challenge
    run1 = client_with_service.post(
        "/api/orchestration/run",
        json={
            "user_request": {
                "session_id": session_id,
                "user_message": "I want to update my Aadhaar address",
                "domain": "aadhaar",
            },
            "confirmed_context": confirmed_context,
        },
    )
    assert run1.status_code == 200
    d1 = run1.json()
    assert d1["status"] == "awaiting_human_action"
    assert d1["integration_result"]["compliance_decision"]["allowed"] is True

    # Step 4: Submit OTP
    confirmed_context_with_otp = {
        **confirmed_context,
        "facts": {
            **confirmed_context["facts"],
            "aadhaar_otp": {
                "value": "654321",
                "provenance": "user-entered-otp",
                "status": "confirmed",
                "allowed_for_execution": True,
            },
        },
    }
    run2 = client_with_service.post(
        "/api/orchestration/run",
        json={
            "user_request": {
                "session_id": session_id,
                "user_message": "I want to update my Aadhaar address",
                "domain": "aadhaar",
            },
            "confirmed_context": confirmed_context_with_otp,
        },
    )
    assert run2.status_code == 200
    d2 = run2.json()
    assert d2["status"] == "execution_completed"
    assert d2["integration_result"]["compliance_decision"]["allowed"] is True
