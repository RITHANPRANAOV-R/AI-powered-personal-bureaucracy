"""
User Document Schema for User Document Understanding & OCR Pipeline.
"""
from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict


class DocumentType(str, Enum):
    """Classification type of user-uploaded document."""
    AADHAAR = "aadhaar"
    PASSPORT = "passport"
    VOTER_ID = "voter_id"
    PAN = "pan"
    DRIVING_LICENCE = "driving_licence"
    ADDRESS_PROOF = "address_proof"
    IDENTITY_PROOF = "identity_proof"
    UNKNOWN = "unknown"


class ExtractionMethod(str, Enum):
    """Method used to extract content from user document."""
    DIRECT_TEXT_PDF = "direct_text_pdf"
    OCR_SCANNED_PDF = "ocr_scanned_pdf"
    OCR_IMAGE = "ocr_image"
    UNKNOWN = "unknown"


class OCRStatus(str, Enum):
    """Status of OCR execution."""
    NOT_REQUIRED = "not_required"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    UNSUPPORTED_FORMAT = "unsupported_format"


class ExtractedField(BaseModel):
    """
    Represents an individual extracted information field from a document.
    """
    model_config = ConfigDict(extra="ignore")

    field_name: str = Field(description="Name of the extracted field e.g. 'name', 'dob'")
    value: str = Field(description="Extracted text value")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Extraction confidence score")
    page_number: Optional[int] = Field(default=1, description="Page number where field was identified")
    source_region: Optional[str] = Field(default=None, description="Bounding region or line reference if available")


class UserDocument(BaseModel):
    """
    Structured representation of a user-uploaded document produced by User Document Understanding.
    """
    model_config = ConfigDict(extra="ignore", use_enum_values=True)

    document_id: str = Field(description="Unique ID for user document")
    filename: str = Field(description="Original filename of uploaded document")
    mime_type: str = Field(description="MIME type or file extension format")
    document_type: DocumentType = Field(default=DocumentType.UNKNOWN, description="Classified document category")
    classification_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Document classification confidence")
    extraction_method: ExtractionMethod = Field(default=ExtractionMethod.UNKNOWN, description="Text extraction technique used")
    page_count: int = Field(default=1, ge=1, description="Total pages in document")
    extracted_text: str = Field(default="", description="Full raw text extracted from document")
    extracted_fields: Dict[str, ExtractedField] = Field(default_factory=dict, description="Structured fields extracted")
    overall_confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Overall extraction confidence score")
    ocr_status: OCRStatus = Field(default=OCRStatus.NOT_REQUIRED, description="OCR execution status")
    warnings: List[str] = Field(default_factory=list, description="Processing warnings or extraction alerts")
    processing_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp of document processing"
    )
