from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile, Request
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

from agents.knowledge_based.information_retrieval.schemas.address_resolution import AddressResolutionResult

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class ConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    confirmed: bool
    extraction: ExtractionResult
    corrections: dict[str, str] = Field(default_factory=dict)
    session_id: str = Field(default="document-review-session", min_length=1)
    application_id: str | None = None
    address_resolution: AddressResolutionResult | None = None
    resolve_address: bool = False
    confirm_resolver_projection: bool = Field(default=False, strict=True)


class ConfirmationResponse(BaseModel):
    confirmed_data: AadhaarConfirmedData
    confirmed_context: dict[str, Any]
    resolver_projection: dict[str, Any] = Field(default_factory=dict)
    review_capability: str | None = Field(default=None, repr=False)


class LaunchBrowserRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    confirmed_context: dict[str, Any] = Field(default_factory=dict)
    urn: str = "0000/12345/67890"
    open_live_portal: bool = True


class StepConsentRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1, max_length=128)
    expected_stage: str = Field(min_length=1)
    expected_state_version: int = Field(ge=0, strict=True)
    user_consent: bool = True
    notes: str | None = None
    user_inputs: dict[str, Any] = Field(default_factory=dict)


def create_app(
    document_service: AadhaarDocumentService | None = None,
    orchestrator: Any = None,
) -> FastAPI:
    app = FastAPI(title="Aadhaar Assistant Local API", version="0.1.0")
    import time
    inspection_deadline = time.monotonic() + 900 if os.getenv("AADHAAR_ENABLE_PORTAL_DIAGNOSTICS", "0") == "1" else None
    frontend_origins = [
        origin.strip()
        for origin in os.getenv(
            "AADHAAR_FRONTEND_ORIGINS",
            "http://localhost:5173",
        ).split(",")
        if origin.strip()
    ]
    if frontend_origins != ["http://localhost:5173"] or os.getenv("AADHAAR_ALLOW_ALL_ORIGINS", "0") == "1":
        raise ValueError("Review capability flow requires localhost:5173 only and wildcard CORS disabled.")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=frontend_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    service = document_service or AadhaarDocumentService()
    from agents.utility_based.execution_assistance.review_context import review_registry, ReviewError
    from agents.utility_based.execution_assistance.address_projection import eligible_post_office

    @app.middleware("http")
    async def check_origin(request: Request, call_next):
        from starlette.responses import JSONResponse
        origin = request.headers.get("origin")
        if origin is not None and origin not in frontend_origins:
            return JSONResponse({"detail": "Frontend origin is not permitted."}, status_code=403)
        return await call_next(request)

    def capability(request):
        header = request.headers.get("authorization", "")
        return header[7:] if header.startswith("Bearer ") else ""

    def authorize(context_id, request, session_id=None):
        try:
            review_registry.authenticate(context_id, capability(request), session_id)
        except ReviewError as error:
            raise HTTPException(status_code=403, detail={"code": "REVIEW_CAPABILITY_AUTH_FAILED", "message": str(error)}) from error

    def authorize_session(session_id, request):
        context_id = request.headers.get("x-review-context", "")
        authorize(context_id, request, session_id)
        return context_id

    async def synchronize_session(context_id):
        from agents.utility_based.execution_assistance.interactive_session import interactive_manager
        snapshot = review_registry.snapshot(context_id)
        async with interactive_manager._lock:
            session = interactive_manager._sessions.get(snapshot.session_id)
            if session is not None:
                current = review_registry.snapshot(context_id)
                if current != session.context:
                    session.execution_version += 1
                session.context = current

    def review_response(context_id, reference=None, context=None):
        if context is None:
            context = review_registry.snapshot(context_id)
        office = eligible_post_office(context)
        return {"confirmed_context": context.model_dump(mode="json"),
                "confirmed_data": {"address_resolution": context.address_resolution.model_dump(mode="json") if context.address_resolution else None},
                "review_reference": reference,
                "resolver_projection": {"eligible": office is not None and "post_office" not in context.facts,
                    "post_office": office, "reason": None if office else "Current evidence is unresolved, ambiguous or ineligible."}}

    @app.post("/api/review-contexts/{context_id}/resolve")
    async def resolve_review(context_id: str, request: Request):
        authorize(context_id, request)
        reservation = None
        try:
            reservation, context = review_registry.begin_lookup(context_id)
            await synchronize_session(context_id)
            # Only server-retained canonical inputs reach the existing resolver.
            from agents.knowledge_based.information_retrieval.retrieval.address_resolver import PostalAddressResolver
            from starlette.concurrency import run_in_threadpool
            resolver = service.address_resolver or PostalAddressResolver()
            pin = context.facts.get("pincode")
            inputs = {k: f.value for k, f in context.facts.items()}
            try:
                result = await run_in_threadpool(resolver.resolve, pin.value if pin else "", inputs)
            except Exception:
                raise ReviewError("Server lookup failed; previous review is invalidated.")
            review_registry.finish_lookup(context_id, reservation, result)
            await synchronize_session(context_id)
            return review_response(context_id)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        finally:
            if reservation is not None:
                review_registry.fail_lookup(context_id, reservation)

    @app.get("/api/review-contexts/{context_id}/review")
    async def publish_review(context_id: str, request: Request):
        authorize(context_id, request)
        try:
            reference, context = review_registry.publish(context_id)
            return review_response(context_id, reference, context)
        except ReviewError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/api/review-contexts/{context_id}/action")
    async def review_action(context_id: str, payload: dict[str, Any], request: Request):
        authorize(context_id, request)
        try:
            if "address_resolution" in payload or "confirmed_context" in payload:
                raise ReviewError("Client resolver envelopes cannot establish server lookup authority.")
            action = payload.get("action")
            if action == "confirm_post_office" and payload.get("confirm_resolver_projection") is True:
                review_registry.confirm(context_id, payload.get("review_reference"), action)
            elif action == "correct":
                from agents.utility_based.execution_assistance.context_validator import apply_context_corrections
                apply_context_corrections(review_registry.snapshot(context_id), payload.get("corrections", {}))
            elif action == "continue_without_projection":
                review_registry.without_projection(context_id)
            elif action == "cancel":
                review_registry.revoke(context_id)
                return {"status": "revoked"}
            else:
                raise ReviewError("A distinct permitted review action is required.")
            await synchronize_session(context_id)
            return review_response(context_id)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

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
        if not content:
            raise HTTPException(status_code=400, detail="The uploaded document is empty. Choose a non-empty PDF or image.")
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
        if payload.resolve_address or payload.confirm_resolver_projection or payload.address_resolution is not None:
            raise HTTPException(status_code=400, detail="Create a server review context, then resolve, review and explicitly confirm through its scoped endpoints.")
        try:
            from agents.utility_based.execution_assistance.context_validator import normalize_address_corrections
            confirmed_data = service.confirm(payload.extraction, normalize_address_corrections(payload.corrections))
            context_id, secret, context = review_registry.create(confirmed_data.to_execution_context(payload.session_id, payload.application_id))
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return ConfirmationResponse(confirmed_data=confirmed_data, confirmed_context=context.model_dump(mode="json"),
                                    resolver_projection={"eligible": False}, review_capability=secret)

    @app.post("/api/browser/launch-uidai")
    async def launch_uidai_in_browser(payload: LaunchBrowserRequest, request: Request) -> dict[str, Any]:
        from agents.utility_based.execution_assistance.browser_autofill import launch_in_chromium
        from agents.utility_based.execution_assistance.schema import ConfirmedExecutionContext

        try:
            from agents.utility_based.execution_assistance.context_validator import reconstruct_execution_context
            raw = payload.confirmed_context or {}
            if not isinstance(raw.get("review_context"), dict):
                raise ReviewError("Server-owned review reference is required for browser launch.")
            authorize(raw["review_context"].get("id"), request, raw.get("session_id"))
            ctx = reconstruct_execution_context(raw, capability=capability(request))
            from agents.utility_based.execution_assistance.interactive_session import interactive_manager

            session_data = await interactive_manager.start_session(ctx, urn=payload.urn)
            return {"status": "ok", "launched": True, **session_data}
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(status_code=400, detail=f"Failed to launch browser: {error}")

    @app.get("/api/browser/final-review/{session_id}")
    async def final_review(session_id: str, request: Request) -> dict[str, Any]:
        from agents.utility_based.execution_assistance.interactive_session import interactive_manager
        authorize_session(session_id, request)
        return await interactive_manager.review_submission(session_id)

    @app.post("/api/browser/final-review/{session_id}")
    async def final_review_action(session_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
        from agents.utility_based.execution_assistance.interactive_session import interactive_manager
        authorize_session(session_id, request)
        return await interactive_manager.final_review_action(session_id, payload.get("action", ""), payload.get("binding"))

    @app.post("/api/browser/submit-step")
    async def submit_browser_step(payload: StepConsentRequest, request: Request) -> dict[str, Any]:
        from agents.utility_based.execution_assistance.interactive_session import interactive_manager

        from agents.utility_based.execution_assistance.context_validator import apply_context_corrections
        authorize_session(payload.session_id, request)
        return await interactive_manager.submit_step(
            session_id=payload.session_id,
            user_consent=payload.user_consent,
            notes=payload.notes,
            user_inputs=payload.user_inputs,
            request_id=payload.request_id,
            expected_stage=payload.expected_stage,
            expected_state_version=payload.expected_state_version,
        )

    @app.post("/api/browser/inspect-structure")
    async def inspect_browser_structure(payload: dict[str, str], request: Request):
        from agents.utility_based.execution_assistance.portal_inspection import require_local_inspection, inspect_existing_session
        from agents.utility_based.execution_assistance.interactive_session import interactive_manager
        from starlette.responses import JSONResponse
        require_local_inspection(request, inspection_deadline, time.monotonic())
        if set(payload) != {"session_id"} or not payload["session_id"]:
            raise HTTPException(status_code=400, detail="Only an existing session_id is permitted.")
        authorize_session(payload["session_id"], request)
        result = await inspect_existing_session(interactive_manager, payload["session_id"])
        require_local_inspection(request, inspection_deadline, time.monotonic())
        authorize_session(payload["session_id"], request)
        return JSONResponse(result, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})

    @app.get("/api/browser/session-status/{session_id}")
    async def get_browser_session_status(session_id: str, request: Request) -> dict[str, Any]:
        from agents.utility_based.execution_assistance.interactive_session import interactive_manager

        authorize_session(session_id, request)
        return interactive_manager.get_session_status(session_id)

    @app.post("/api/orchestration/run", response_model=OrchestrationResult)
    async def run_orchestration(payload: OrchestrationRequest, request: Request) -> OrchestrationResult:
        if orchestrator is None:
            raise HTTPException(
                status_code=503,
                detail="The local orchestration runtime is not configured.",
            )
        if payload.confirmed_context is not None:
            from agents.utility_based.execution_assistance.context_validator import reconstruct_execution_context
            raw = payload.confirmed_context.model_dump(mode="json")
            if not isinstance(raw.get("review_context"), dict):
                raise HTTPException(status_code=403, detail="Server-owned execution context is required.")
            authorize(raw["review_context"]["id"], request, raw["session_id"])
            try:
                payload.confirmed_context = reconstruct_execution_context(raw, capability=capability(request))
            except ValueError as error:
                raise HTTPException(status_code=403, detail=str(error)) from error
        if payload.confirmed_context is not None:
            try:
                context_id = review_registry.begin_execution(payload.confirmed_context)
            except ReviewError as error:
                raise HTTPException(status_code=403, detail=str(error)) from error
            try:
                return orchestrator.run(payload)
            finally:
                review_registry.end_execution(context_id)
        return orchestrator.run(payload)

    return app


_default_mode = os.getenv("AADHAAR_RUNTIME_MODE", "uidai").lower()
_default_orchestrator = (
    create_demo_orchestrator()
    if _default_mode == "demo"
    else create_production_orchestrator(require_otp=True)
)

app = create_app(orchestrator=_default_orchestrator)
