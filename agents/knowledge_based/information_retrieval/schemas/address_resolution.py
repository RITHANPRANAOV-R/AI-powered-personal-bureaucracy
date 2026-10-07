"""Postal address-resolution output; does not authorize government execution."""
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from ..live_retrieval.india_post_fetcher import PostalLookupStatus, PostalRecord
from .evidence import Evidence
from .retrieval_result import ConflictItem
from .source import Source


class AddressResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    CONFLICT = "conflict"
    NO_RESULT = "no_result"
    UNAVAILABLE = "unavailable"
    INVALID_PIN = "invalid_pin"


class AddressFieldStatus(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    CONFLICT = "conflict"
    UNRESOLVED = "unresolved"


class AddressResolutionField(BaseModel):
    value: str | None = None
    status: AddressFieldStatus = AddressFieldStatus.UNRESOLVED
    options: list[str] = Field(default_factory=list)
    value_origin: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    supporting_candidate_indexes: list[int] = Field(default_factory=list)


class AddressResolutionResult(BaseModel):
    """RESOLVED means postal fields only; VTC has a separate unresolved gate."""

    status: AddressResolutionStatus
    queried_pin: str | None = None
    state: AddressResolutionField = Field(default_factory=AddressResolutionField)
    district: AddressResolutionField = Field(default_factory=AddressResolutionField)
    post_office: AddressResolutionField = Field(default_factory=AddressResolutionField)
    vtc: AddressResolutionField = Field(default_factory=AddressResolutionField)
    vtc_requires_uidai_resolution_or_user_confirmation: bool = True
    candidates: list[PostalRecord] = Field(default_factory=list)
    plausible_candidate_indexes: list[int] = Field(default_factory=list)
    narrowing_evidence_ids: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)
    conflicts: list[ConflictItem] = Field(default_factory=list)
    ambiguity_information: list[str] = Field(default_factory=list)
    source: Source | None = None
    source_resource_id: str | None = None
    retrieved_at: str | None = None
    lookup_status: PostalLookupStatus | None = None
    error_message: str | None = None
