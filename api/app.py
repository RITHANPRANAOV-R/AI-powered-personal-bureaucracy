from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from agents.orchestration.document_input import (
    AadhaarDocumentInput,
    AadhaarDocumentService,
    AadhaarConfirmedData,
    ExtractionResult,
)
from agents.orchestration.pipeline import (
    OrchestrationRequest,
    OrchestrationResult,
    TopLevelOrchestrator,
    create_production_orchestrator,
)
from demo.runtime import create_demo_orchestrator

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class ConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    confirmed: bool
    extraction: ExtractionResult
    corrections: dict[str, str] = Field(default_factory=dict)
    session_id: str = Field(default="document-review-session", min_length=1)
    application_id: str | None = None


class ConfirmationResponse(BaseModel):
    confirmed_data: AadhaarConfirmedData
    confirmed_context: dict[str, Any]


class LaunchBrowserRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    confirmed_context: dict[str, Any] = Field(default_factory=dict)
    urn: str = "0000/12345/67890"
    open_live_portal: bool = True


class StepConsentRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str = Field(min_length=1)
    user_consent: bool = True
    notes: str | None = None
    user_inputs: dict[str, Any] = Field(default_factory=dict)


def create_app(
    document_service: AadhaarDocumentService | None = None,
    orchestrator: Any = None,
) -> FastAPI:
    app = FastAPI(title="Aadhaar Assistant Local API", version="0.1.0")
    frontend_origins = [
        origin.strip()
        for origin in os.getenv(
            "AADHAAR_FRONTEND_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=frontend_origins + ["*"] if os.getenv("AADHAAR_ALLOW_ALL_ORIGINS", "1") == "1" else frontend_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    service = document_service or AadhaarDocumentService()

    @app.get("/api/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok", "service": "aadhaar-assistant-api", "mode": _default_mode}

    @app.post("/api/documents/aadhaar/extract", response_model=ExtractionResult)
    async def extract_aadhaar(
        file: UploadFile | None = File(default=None),
        document: UploadFile | None = File(default=None),
        new_address: str | None = None,
        pincode: str | None = None,
    ) -> ExtractionResult:
        upload = file or document
        if upload is None:
            raise HTTPException(status_code=422, detail="A document file is required.")
        filename = upload.filename or "uploaded-document"
        content = await upload.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="The uploaded document exceeds the supported size limit.")
        user_ctx = {}
        if new_address:
            user_ctx["new_address"] = new_address
        if pincode:
            user_ctx["pincode"] = pincode
        try:
            return service.extract(
                AadhaarDocumentInput(
                    filename=filename,
                    content=content,
                    mime_type=upload.content_type,
                ),
                user_context=user_ctx if user_ctx else None,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/documents/aadhaar/confirm", response_model=ConfirmationResponse)
    async def confirm_aadhaar(payload: ConfirmationRequest) -> ConfirmationResponse:
        if payload.confirmed is not True:
            raise HTTPException(status_code=400, detail="Explicit confirmation is required before continuing.")
        try:
            confirmed_data = service.confirm(payload.extraction, payload.corrections)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        context = confirmed_data.to_execution_context(payload.session_id, payload.application_id)
        return ConfirmationResponse(
            confirmed_data=confirmed_data,
            confirmed_context=context.model_dump(mode="json"),
        )

    @app.post("/api/browser/launch-uidai")
    async def launch_uidai_in_browser(payload: LaunchBrowserRequest) -> dict[str, Any]:
        from agents.utility_based.execution_assistance.browser_autofill import launch_in_chromium
        from agents.utility_based.execution_assistance.schema import ConfirmedExecutionContext

        try:
            raw_ctx = payload.confirmed_context or {}
            session_id = raw_ctx.get("session_id") or "browser-session"
            facts_data = raw_ctx.get("facts", {})
            normalized_facts = {}
            for k, v in facts_data.items():
                if isinstance(v, dict):
                    val = v.get("value")
                    prov = v.get("provenance") or "user-input"
                    stat = v.get("status") or "confirmed"
                    allowed = v.get("allowed_for_execution", True)
                    normalized_facts[k] = {
                        "value": val,
                        "provenance": prov,
                        "status": stat,
                        "allowed_for_execution": allowed,
                    }
                else:
                    normalized_facts[k] = {
                        "value": v,
                        "provenance": "user-input",
                        "status": "confirmed",
                        "allowed_for_execution": True,
                    }
            doc_refs = raw_ctx.get("document_refs", [])
            ctx = ConfirmedExecutionContext(
                session_id=session_id,
                facts=normalized_facts,
                document_refs=doc_refs,
            )
            from agents.utility_based.execution_assistance.interactive_session import interactive_manager

            session_data = await interactive_manager.start_session(ctx, urn=payload.urn)
            return {"status": "ok", "launched": True, **session_data}
        except Exception as error:
            raise HTTPException(status_code=400, detail=f"Failed to launch browser: {error}")

    @app.post("/api/browser/submit-step")
    async def submit_browser_step(payload: StepConsentRequest) -> dict[str, Any]:
        from agents.utility_based.execution_assistance.interactive_session import interactive_manager

        return await interactive_manager.submit_step(
            session_id=payload.session_id,
            user_consent=payload.user_consent,
            notes=payload.notes,
            user_inputs=payload.user_inputs,
        )

    @app.get("/api/browser/session-status/{session_id}")
    async def get_browser_session_status(session_id: str) -> dict[str, Any]:
        from agents.utility_based.execution_assistance.interactive_session import interactive_manager

        return interactive_manager.get_session_status(session_id)

    @app.post("/api/orchestration/run", response_model=OrchestrationResult)
    async def run_orchestration(payload: OrchestrationRequest) -> OrchestrationResult:
        if orchestrator is None:
            raise HTTPException(
                status_code=503,
                detail="The local orchestration runtime is not configured.",
            )
        return orchestrator.run(payload)

    return app


_default_mode = os.getenv("AADHAAR_RUNTIME_MODE", "uidai").lower()
_default_orchestrator = (
    create_demo_orchestrator()
    if _default_mode == "demo"
    else create_production_orchestrator(require_otp=True)
)

app = create_app(orchestrator=_default_orchestrator)
