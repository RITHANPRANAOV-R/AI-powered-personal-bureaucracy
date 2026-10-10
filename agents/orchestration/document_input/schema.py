from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from agents.knowledge_based.information_retrieval.schemas.address_resolution import AddressResolutionResult
from agents.knowledge_based.information_retrieval.ingestion.parser import ExtractedPage

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
    ENCRYPTED_DOCUMENT = "encrypted_document"
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
    source_region: Optional[str] = None
    provenance: FieldProvenance = Field(default=FieldProvenance.EXTRACTED_FROM_DOCUMENT)


class ConfirmedField(BaseModel):
    model_config = ConfigDict(extra="ignore")

    value: str = Field(min_length=1)
    source_document_id: str = Field(min_length=1)
    provenance: FieldProvenance
    page_number: Optional[int] = Field(default=None, ge=1)
    source_region: Optional[str] = None
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
    pages: list[ExtractedPage] = Field(default_factory=list)
    document_metadata: dict[str, Any] = Field(default_factory=dict)

    def to_execution_context(self, session_id: str, application_id: str | None = None, *, confirm_resolver_projection: bool = False) -> ConfirmedExecutionContext:
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
                source_document_id=field.source_document_id,
            )
            facts[field_name] = fact
            if field_name == "aadhaar_number":
                facts["aadhaar"] = fact
                facts["uid"] = fact
            elif field_name == "new_address":
                facts["address"] = fact
        if self.document_id or self.pages or any(getattr(self, key) and getattr(self, key).page_number for key in ("name", "date_of_birth", "gender", "masked_aadhaar", "aadhaar_number", "vid", "existing_address", "new_address", "pincode")):
            fields = {
                key: {"source_document_id": field.source_document_id, "page_number": field.page_number,
                      "source_region": field.source_region, "provenance": field.provenance.value}
                for key in ("name", "date_of_birth", "gender", "masked_aadhaar", "aadhaar_number", "vid", "existing_address", "new_address", "pincode")
                if (field := getattr(self, key)) is not None
            }
            facts["document_evidence"] = ConfirmedFact(
                value={"document_id": self.document_id, "fields": fields,
                       "pages": [page.model_dump() for page in self.pages],
                       **({"document_metadata": self.document_metadata} if self.document_metadata else {})},
                provenance="document_page_evidence", status=FactStatus.UNCONFIRMED,
                allowed_for_execution=False,
            )
        if self.address_resolution is not None:
            facts["address_resolution"] = ConfirmedFact(
                value=self.address_resolution.model_copy(deep=True),
                provenance="postal_address_resolution_metadata",
                status=FactStatus.UNCONFIRMED,
                allowed_for_execution=False,
            )
        context = ConfirmedExecutionContext(
            session_id=session_id,
            application_id=application_id,
            document_refs=[self.document_id],
            facts=facts,
        )
        if confirm_resolver_projection is True:
            from agents.utility_based.execution_assistance.address_projection import project_confirmed_resolution
            return project_confirmed_resolution(context, explicitly_confirmed=True)
        return context


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: ExtractionStatus
    document_id: str = Field(min_length=1)
    data: Optional[AadhaarExtractedData] = None
    pages: list[ExtractedPage] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    conflicts: dict[str, list[ExtractedField]] = Field(default_factory=dict)
    validation_errors: dict[str, str] = Field(default_factory=dict)
    document_metadata: dict[str, Any] = Field(default_factory=dict)


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
