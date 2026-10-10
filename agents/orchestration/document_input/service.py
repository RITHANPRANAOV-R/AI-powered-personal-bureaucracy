from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import re

from agents.knowledge_based.information_retrieval.retrieval.address_resolver import PostalAddressResolver

from agents.knowledge_based.information_retrieval.schemas.address_resolution import AddressResolutionResult

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
        "aadhaar_number",
        "vid",
        "existing_address",
        "new_address",
        "pincode",
    )

    def __init__(self, extractor: AadhaarDocumentExtractor | None = None, *,
                 address_resolver: PostalAddressResolver | None = None):
        self.extractor = extractor or AadhaarDocumentExtractor()
        self.address_resolver = address_resolver

    def extract(self, document: AadhaarDocumentInput, user_context: dict[str, Any] | None = None) -> ExtractionResult:
        return self.extractor.extract(document, user_context=user_context)

    def confirm(
        self,
        extraction: ExtractionResult,
        corrections: dict[str, str] | None = None,
        *,
        address_resolution: AddressResolutionResult | None = None,
        resolve_address: bool = False,
    ) -> AadhaarConfirmedData:
        if extraction.data is None:
            raise ValueError("There is no extracted data available for confirmation.")
        if extraction.status not in {ExtractionStatus.SUCCESS, ExtractionStatus.MISSING_REQUIRED_FIELDS}:
            raise ValueError("Only readable extracted data can be confirmed.")

        if resolve_address and address_resolution is not None:
            raise ValueError("Request address resolution or supply an existing result, not both.")

        corrections = corrections or {}
        unknown_fields = set(corrections) - set(self.SUPPORTED_FIELDS)
        if unknown_fields:
            raise ValueError(f"Unsupported Aadhaar correction fields: {sorted(unknown_fields)}")

        unresolved = (set(extraction.conflicts) | set(extraction.validation_errors)) - set(corrections)
        if unresolved:
            raise ValueError(f"Explicit correction is required for conflicting/invalid fields: {sorted(unresolved)}")

        confirmed_values: dict[str, ConfirmedField | None] = {}
        for field_name in self.SUPPORTED_FIELDS:
            extracted = getattr(extraction.data, field_name, None)
            correction = corrections.get(field_name)
            if correction is not None:
                value = correction.strip()
                if not value:
                    raise ValueError(f"Correction for '{field_name}' cannot be empty.")
                if field_name == "pincode" and re.fullmatch(r"[1-9][0-9]{5}", value) is None:
                    raise ValueError("Corrected PIN must be exactly six digits beginning with 1-9.")
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
                    page_number=extracted.page_number,
                    source_region=extracted.source_region,
                    confirmed_at=datetime.now(timezone.utc),
                )
            else:
                confirmed_values[field_name] = None

        proposed = confirmed_values.get("new_address")
        if proposed is not None:
            proposed_pins = set(re.findall(r"\b[1-9][0-9]{5}\b", proposed.value))
            intended_pin = confirmed_values.get("pincode")
            if len(proposed_pins) > 1:
                raise ValueError("The proposed new address contains multiple PINs. Correct the new address before confirming.")
            if proposed_pins and intended_pin is not None and intended_pin.value not in proposed_pins:
                raise ValueError("The new PIN does not match the proposed new address. Correct the new address or new PIN before confirming.")

        missing_required = [
            field_name for field_name in REQUIRED_FIELDS
            if confirmed_values[field_name] is None
        ]
        if missing_required:
            raise ValueError(f"Required Aadhaar fields remain missing: {missing_required}")

        confirmed = AadhaarConfirmedData(
            **confirmed_values,
            document_id=extraction.document_id,
            pages=[page.model_copy(deep=True) for page in extraction.pages],
            address_resolution=address_resolution.model_copy(deep=True) if address_resolution is not None else None,
            document_metadata=dict(extraction.document_metadata),
        )
        if confirmed.address_resolution is not None:
            for key in ("existing_address", "new_address", "pincode"):
                original = getattr(extraction.data, key, None)
                if key in corrections and (original is None or corrections[key].strip() != original.value):
                    confirmed.address_resolution = None
                    break
        if resolve_address:
            # Use the existing confirmed PIN; never derive or replace browser facts.
            pin = confirmed.pincode.value if confirmed.pincode is not None else ""
            resolver = self.address_resolver or PostalAddressResolver()
            result = resolver.resolve(pin, confirmed)
            confirmed.address_resolution = AddressResolutionResult.model_validate(result).model_copy(deep=True)
        return confirmed


__all__ = ["AadhaarDocumentService"]
