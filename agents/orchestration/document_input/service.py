from __future__ import annotations

from datetime import datetime, timezone

from .extractor import REQUIRED_FIELDS, AadhaarDocumentExtractor
from .schema import (
    AadhaarConfirmedData,
    AadhaarDocumentInput,
    AadhaarExtractedData,
    ConfirmedField,
    ExtractionResult,
    ExtractionStatus,
    FieldProvenance,
)


class AadhaarDocumentService:
    """Owns upload extraction and explicit user confirmation, not profile state."""

    SUPPORTED_FIELDS = (
        "name",
        "date_of_birth",
        "gender",
        "masked_aadhaar",
        "existing_address",
    )

    def __init__(self, extractor: AadhaarDocumentExtractor | None = None):
        self.extractor = extractor or AadhaarDocumentExtractor()

    def extract(self, document: AadhaarDocumentInput) -> ExtractionResult:
        return self.extractor.extract(document)

    def confirm(
        self,
        extraction: ExtractionResult,
        corrections: dict[str, str] | None = None,
    ) -> AadhaarConfirmedData:
        if extraction.data is None:
            raise ValueError("There is no extracted data available for confirmation.")
        if extraction.status not in {ExtractionStatus.SUCCESS, ExtractionStatus.MISSING_REQUIRED_FIELDS}:
            raise ValueError("Only readable extracted data can be confirmed.")

        corrections = corrections or {}
        unknown_fields = set(corrections) - set(self.SUPPORTED_FIELDS)
        if unknown_fields:
            raise ValueError(f"Unsupported Aadhaar correction fields: {sorted(unknown_fields)}")

        confirmed_values: dict[str, ConfirmedField | None] = {}
        for field_name in self.SUPPORTED_FIELDS:
            extracted = getattr(extraction.data, field_name)
            correction = corrections.get(field_name)
            if correction is not None:
                value = correction.strip()
                if not value:
                    raise ValueError(f"Correction for '{field_name}' cannot be empty.")
                source_document_id = extraction.document_id
                confirmed_values[field_name] = ConfirmedField(
                    value=value,
                    source_document_id=source_document_id,
                    provenance=FieldProvenance.USER_CORRECTED,
                    confirmed_at=datetime.now(timezone.utc),
                )
            elif extracted is not None:
                confirmed_values[field_name] = ConfirmedField(
                    value=extracted.value,
                    source_document_id=extracted.source_document_id,
                    provenance=FieldProvenance.USER_CONFIRMED,
                    confirmed_at=datetime.now(timezone.utc),
                )
            else:
                confirmed_values[field_name] = None

        missing_required = [
            field_name for field_name in REQUIRED_FIELDS
            if confirmed_values[field_name] is None
        ]
        if missing_required:
            raise ValueError(f"Required Aadhaar fields remain missing: {missing_required}")

        return AadhaarConfirmedData(
            **confirmed_values,
            document_id=extraction.document_id,
        )


__all__ = ["AadhaarDocumentService"]
