"""Response Generation Agent implementation.

Generates concise, citizen-friendly responses grounded strictly in upstream structured results.
Enforces deterministic status precedence and evidence reference mapping.
"""

from __future__ import annotations

import json
from typing import Optional

from pydantic import ValidationError

from .config import ResponseConfig, load_response_config
from .formatter import (
    build_evidence_references,
    calculate_overall_status,
    extract_citizen_next_step,
    extract_completed_actions,
    extract_official_links,
    extract_pending_actions,
    render_markdown_response,
)
from .llm import ResponseModelUnavailableError, ResponseOllamaClient
from .schema import (
    CitizenResponse,
    GenerationMode,
    OverallStatus,
    ResponseGenerationRequest,
    utc_now,
)


class ResponseGenerationError(ValueError):
    """Raised when response generation request fails validation."""


class ResponseGenerationAgent:
    """Public Response Generation Agent."""

    def __init__(
        self,
        config: Optional[ResponseConfig] = None,
        *,
        allow_llm: bool = True,
    ) -> None:
        self.config = config or load_response_config()
        self.allow_llm = allow_llm
        self.ollama = ResponseOllamaClient(self.config)

    def generate_citizen_response(self, request: ResponseGenerationRequest) -> CitizenResponse:
        """
        Public callable interface for Response Generation Agent.

        Signature:
            def generate_citizen_response(request: ResponseGenerationRequest) -> CitizenResponse
        """
        try:
            request = ResponseGenerationRequest.model_validate(request)
        except ValidationError as exc:
            raise ResponseGenerationError(f"Invalid ResponseGenerationRequest contract: {exc}") from exc

        warnings: List[str] = []

        # 1. Correlation ID check
        intent = request.intent
        plan = request.workflow_plan
        val_res = request.validation_result

        ids = {
            "intent": intent.request_id,
            "plan": plan.request_id,
            "validation": val_res.request_id,
        }
        if request.execution_result:
            ids["execution"] = request.execution_result.request_id
        if request.monitoring_result:
            ids["monitoring"] = request.monitoring_result.request_id

        if len(set(ids.values())) > 1:
            warnings.append(f"Request ID correlation discrepancy detected across inputs: {ids}")

        # 2. Deterministic Status Precedence Calculation
        overall_status = calculate_overall_status(request)

        # 3. Extract Grounded Details
        completed_actions = extract_completed_actions(request)
        pending_actions = extract_pending_actions(request)
        citizen_next_step = extract_citizen_next_step(request)
        official_links = extract_official_links(request)
        evidence_references = build_evidence_references(request)

        language = request.response_language or intent.language or "English"
        generation_mode = GenerationMode.DETERMINISTIC_FALLBACK
        headline = f"{intent.service_name or 'Official Service'} Status: {overall_status.value.replace('_', ' ').title()}"
        summary = (
            f"Your request for {intent.service_name or 'official guidance'} is currently {overall_status.value.replace('_', ' ')}. "
            f"Please follow the immediate next step below."
        )

        # 4. Optional Ollama Language Synthesis
        if self.allow_llm:
            try:
                compact_context = _build_compact_context(request, overall_status)
                completion = self.ollama.generate_response_json(compact_context)
                payload = json.loads(completion.content)
                if isinstance(payload, dict):
                    headline = str(payload.get("headline") or headline)
                    summary = str(payload.get("summary") or summary)
                    generation_mode = GenerationMode.OLLAMA
            except (ResponseModelUnavailableError, json.JSONDecodeError, Exception) as exc:
                warnings.append(f"Ollama local model was skipped or unavailable ({exc}). Used deterministic_fallback.")

        # 5. Render Ready-to-Display Markdown
        markdown = render_markdown_response(
            request=request,
            status=overall_status,
            summary=summary,
            next_step=citizen_next_step,
            completed=completed_actions,
            pending=pending_actions,
            official_links=official_links,
            evidence_refs=evidence_references,
        )

        return CitizenResponse(
            contract_version="1.0",
            response_request_id=request.response_request_id,
            request_id=intent.request_id,
            plan_id=plan.plan_id,
            headline=headline,
            overall_status=overall_status,
            summary=summary,
            completed_actions=completed_actions,
            pending_actions=pending_actions,
            citizen_next_step=citizen_next_step,
            missing_items=[],
            important_details=[],
            official_links=official_links,
            evidence_references=evidence_references,
            warnings=warnings,
            language=language,
            formatted_markdown=markdown,
            generated_at=utc_now(),
            generation_mode=generation_mode,
        )


def generate_citizen_response(
    request: ResponseGenerationRequest, allow_llm: bool = True
) -> CitizenResponse:
    """Public callable interface for Response Generation Agent."""
    return ResponseGenerationAgent(allow_llm=allow_llm).generate_citizen_response(request)


def _build_compact_context(request: ResponseGenerationRequest, status: OverallStatus) -> dict:
    return {
        "service_name": request.intent.service_name,
        "task_type": request.intent.task_type.value,
        "language": request.response_language or request.intent.language,
        "overall_status": status.value,
        "goal_summary": request.intent.normalized_goal,
        "validation_decision": request.validation_result.decision.value,
    }
