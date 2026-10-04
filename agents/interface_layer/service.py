from __future__ import annotations

from typing import Any, Mapping

from pydantic import ValidationError

from agents.interface_layer.schemas import InterfaceRequest, InterfaceResponse


class InterfaceService:
    """Thin validation and normalization entry point for the Interface Layer."""

    @staticmethod
    def _normalize_request_data(request: InterfaceRequest) -> dict[str, Any]:
        return {
            "session_id": request.session_id,
            "user_message": request.user_message,
            "domain": request.domain,
            "conversation_history": request.conversation_history,
            "current_session_state": request.current_session_state,
        }

    def process(self, payload: InterfaceRequest | Mapping[str, Any]) -> InterfaceResponse:
        if isinstance(payload, InterfaceRequest):
            request = payload
        else:
            try:
                request = InterfaceRequest.model_validate(payload)
            except ValidationError as exc:
                session_id = str(payload.get("session_id", "")) if isinstance(payload, dict) else ""
                message = exc.errors()[0].get("msg") if exc.errors() else "Invalid request"
                return InterfaceResponse(
                    session_id=session_id or "invalid",
                    accepted=False,
                    valid=False,
                    downstream_payload=None,
                    error_message=message,
                )

        downstream_payload = self._normalize_request_data(request)
        return InterfaceResponse(
            session_id=request.session_id,
            accepted=True,
            valid=True,
            downstream_payload=downstream_payload,
            error_message=None,
        )


__all__ = [
    "InterfaceService",
]
