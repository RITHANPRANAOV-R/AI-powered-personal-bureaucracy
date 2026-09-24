from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class InterfaceRequest(BaseModel):
    """Validated external request accepted by the Interface Layer.

    This contract intentionally contains only input fields needed for downstream
    normalization and future delegation. It does not classify intent or imply any
    specific downstream behavior.
    """

    session_id: str = Field(min_length=1)
    user_message: str = Field(min_length=1)
    domain: str = Field(default="aadhaar", min_length=1)
    conversation_history: Optional[list[str]] = None
    current_session_state: Optional[dict[str, Any]] = None

    @field_validator("user_message")
    @classmethod
    def validate_user_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("user_message must be a non-empty string")
        return value.strip()


class InterfaceResponse(BaseModel):
    """Structured response returned by the Interface Layer.

    For valid input, this contains the normalized downstream payload. For invalid
    input, it remains deterministic and does not invent or mutate user data.
    """

    session_id: str = Field(min_length=1)
    accepted: bool = False
    valid: bool = False
    downstream_payload: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.valid and self.accepted


__all__ = [
    "InterfaceRequest",
    "InterfaceResponse",
]
