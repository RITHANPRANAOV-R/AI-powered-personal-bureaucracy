from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, model_validator


class ValidationStatus(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"


class ConfidenceLevel(str, Enum):
    VERIFIED = "VERIFIED"
    USER_CONFIRMED = "USER_CONFIRMED"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"


class DocumentType(str, Enum):
    AADHAAR = "AADHAAR"
    PASSPORT = "PASSPORT"
    PAN = "PAN"
    DRIVING_LICENSE = "DRIVING_LICENSE"
    INCOME_CERTIFICATE = "INCOME_CERTIFICATE"
    ADDRESS_PROOF = "ADDRESS_PROOF"
    EDUCATIONAL_CERTIFICATE = "EDUCATIONAL_CERTIFICATE"
    OTHER = "OTHER"


class EvidenceEntry(BaseModel):
    source: str
    requirement: str
    evidence: str
    result: ValidationStatus
    next_action: str


class ComplianceValidationInput(BaseModel):
    document_type: Union[str, DocumentType] = DocumentType.OTHER
    service_type: str = "general_service"
    user_information: Dict[str, Any] = Field(default_factory=dict)
    documents: Dict[str, Any] = Field(default_factory=dict)
    requirements: Dict[str, Any] = Field(default_factory=dict)
    form_data: Dict[str, Any] = Field(default_factory=dict)
    confidence: Dict[str, ConfidenceLevel] = Field(default_factory=dict)


class ComplianceValidationResult(BaseModel):
    document_type: str
    service_type: str
    status: ValidationStatus
    overall_status: ValidationStatus

    missing_information: List[str] = Field(default_factory=list)
    missing_documents: List[str] = Field(default_factory=list)
    invalid_documents: List[str] = Field(default_factory=list)
    inconsistencies: List[str] = Field(default_factory=list)
    form_errors: List[str] = Field(default_factory=list)
    security_issues: List[str] = Field(default_factory=list)
    evidence: List[EvidenceEntry] = Field(default_factory=list)
    next_action: str
    confidence: Dict[str, ConfidenceLevel] = Field(default_factory=dict)

    @model_validator(mode="after")
    def sync_status(self):
        self.overall_status = self.status
        return self