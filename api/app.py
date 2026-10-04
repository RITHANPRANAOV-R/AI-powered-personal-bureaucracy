from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from agents.orchestration.document_input import (
    AadhaarDocumentInput,
    AadhaarDocumentService,
    AadhaarConfirmedData,
    ExtractionResult,
)
from agents.orchestration.pipeline import OrchestrationRequest, OrchestrationResult, TopLevelOrchestrator
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


def create_app(
    document_service: AadhaarDocumentService | None = None,
    orchestrator: TopLevelOrchestrator | None = None,
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
        allow_origins=frontend_origins,
        allow_credentials=False,
        allow_methods=["POST"],
        allow_headers=["Content-Type"],
    )
    service = document_service or AadhaarDocumentService()

    @app.post("/api/documents/aadhaar/extract", response_model=ExtractionResult)
    async def extract_aadhaar(
        file: UploadFile | None = File(default=None),
        document: UploadFile | None = File(default=None),
    ) -> ExtractionResult:
        upload = file or document
        if upload is None:
            raise HTTPException(status_code=422, detail="A document file is required.")
        filename = upload.filename or "uploaded-document"
        content = await upload.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="The uploaded document exceeds the supported size limit.")
        try:
            return service.extract(
                AadhaarDocumentInput(
                    filename=filename,
                    content=content,
                    mime_type=upload.content_type,
                )
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

    @app.post("/api/orchestration/run", response_model=OrchestrationResult)
    async def run_orchestration(payload: OrchestrationRequest) -> OrchestrationResult:
        if orchestrator is None:
            raise HTTPException(
                status_code=503,
                detail="The local orchestration runtime is not configured.",
            )
        return orchestrator.run(payload)

    return app


app = create_app(orchestrator=create_demo_orchestrator())
