from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from agents.knowledge_based.information_retrieval.schemas.address_resolution import AddressResolutionResult

from agents.utility_based.execution_assistance.schema import ConfirmedExecutionContext, ConfirmedFact, FactStatus


class FieldProvenance(str, Enum):
    EXTRACTED_FROM_DOCUMENT = "extracted_from_document"
    USER_CONTEXT = "user_context"
    USER_CONFIRMED = "user_confirmed"
    USER_CORRECTED = "user_corrected"


class ExtractionStatus(str, Enum):
    SUCCESS = "success"
    MISSING_REQUIRED_FIELDS = "missing_required_fields"
    MALFORMED_DOCUMENT = "malformed_document"
    UNSUPPORTED_DOCUMENT = "unsupported_document"
    EXTRACTION_FAILED = "extraction_failed"


class AadhaarDocumentInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    document_id: str = Field(default_factory=lambda: f"aadhaar-doc-{uuid4().hex[:12]}")
    filename: str = Field(min_length=1)
    content: bytes = Field(min_length=1)
    mime_type: Optional[str] = None


class ExtractedField(BaseModel):
    model_config = ConfigDict(extra="ignore")

    value: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    source_document_id: str = Field(min_length=1)
    page_number: Optional[int] = Field(default=None, ge=1)
    provenance: FieldProvenance = Field(default=FieldProvenance.EXTRACTED_FROM_DOCUMENT)


class ConfirmedField(BaseModel):
    model_config = ConfigDict(extra="ignore")

    value: str = Field(min_length=1)
    source_document_id: str = Field(min_length=1)
    provenance: FieldProvenance
    confirmed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AadhaarExtractedData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: Optional[ExtractedField] = None
    date_of_birth: Optional[ExtractedField] = None
    gender: Optional[ExtractedField] = None
    masked_aadhaar: Optional[ExtractedField] = None
    aadhaar_number: Optional[ExtractedField] = None
    vid: Optional[ExtractedField] = None
    existing_address: Optional[ExtractedField] = None
    new_address: Optional[ExtractedField] = None
    pincode: Optional[ExtractedField] = None


class AadhaarConfirmedData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: Optional[ConfirmedField] = None
    date_of_birth: Optional[ConfirmedField] = None
    gender: Optional[ConfirmedField] = None
    masked_aadhaar: Optional[ConfirmedField] = None
    aadhaar_number: Optional[ConfirmedField] = None
    vid: Optional[ConfirmedField] = None
    existing_address: Optional[ConfirmedField] = None
    new_address: Optional[ConfirmedField] = None
    pincode: Optional[ConfirmedField] = None
    document_id: str = Field(min_length=1)
    address_resolution: AddressResolutionResult | None = None

    def to_execution_context(self, session_id: str, application_id: str | None = None) -> ConfirmedExecutionContext:
        facts: dict[str, ConfirmedFact] = {}
        for field_name in (
            "name",
            "date_of_birth",
            "gender",
            "masked_aadhaar",
            "aadhaar_number",
            "vid",
            "existing_address",
            "new_address",
            "pincode",
        ):
            field = getattr(self, field_name, None)
            if field is None:
                continue
            fact = ConfirmedFact(
                value=field.value,
                provenance=field.provenance.value,
                status=FactStatus.CONFIRMED,
                allowed_for_execution=True,
            )
            facts[field_name] = fact
            if field_name == "aadhaar_number":
                facts["aadhaar"] = fact
                facts["uid"] = fact
            elif field_name == "new_address":
                facts["address"] = fact
        if self.address_resolution is not None:
            facts["address_resolution"] = ConfirmedFact(
                value=self.address_resolution.model_copy(deep=True),
                provenance="postal_address_resolution_metadata",
                status=FactStatus.UNCONFIRMED,
                allowed_for_execution=False,
            )
        return ConfirmedExecutionContext(
            session_id=session_id,
            application_id=application_id,
            document_refs=[self.document_id],
            facts=facts,
        )


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: ExtractionStatus
    document_id: str = Field(min_length=1)
    data: Optional[AadhaarExtractedData] = None
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: Optional[str] = None


__all__ = [
    "AadhaarConfirmedData",
    "AadhaarDocumentInput",
    "AadhaarExtractedData",
    "ConfirmedField",
    "ExtractedField",
    "ExtractionResult",
    "ExtractionStatus",
    "FieldProvenance",
]
