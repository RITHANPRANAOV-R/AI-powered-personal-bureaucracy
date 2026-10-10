from __future__ import annotations

from typing import Any
from pathlib import Path
import re
import hashlib

from agents.knowledge_based.information_retrieval.document_understanding.extractor import (
    DocumentClassifier,
    FieldExtractor,
)
from agents.knowledge_based.information_retrieval.document_understanding.ocr_engine import (
    BaseOCREngine,
    PaddleOCREngine,
)
from agents.knowledge_based.information_retrieval.ingestion.parser import DocumentParser, ParseStatus, ExtractedPage
from agents.knowledge_based.information_retrieval.schemas.user_document import DocumentType

from .schema import (
    AadhaarDocumentInput,
    AadhaarExtractedData,
    ExtractedField,
    ExtractionResult,
    ExtractionStatus,
    FieldProvenance,
)


SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
MAX_DOCUMENT_SIZE_BYTES = 25 * 1024 * 1024
REQUIRED_FIELDS = ("name", "date_of_birth", "existing_address")


class UnavailableOCREngine(BaseOCREngine):
    """Explicit no-OCR implementation used when no local OCR engine is supplied."""

    def extract_text_from_image(self, image_bytes: bytes) -> tuple[str, float]:
        return "", 0.0


class AadhaarDocumentExtractor:
    def __init__(
        self,
        parser: DocumentParser | None = None,
        ocr_engine: BaseOCREngine | None = None,
        classifier: DocumentClassifier | None = None,
        field_extractor: FieldExtractor | None = None,
    ):
        self.parser = parser or DocumentParser()
        self.ocr_engine = ocr_engine or PaddleOCREngine()
        self.classifier = classifier or DocumentClassifier()
        self.field_extractor = field_extractor or FieldExtractor()

    def extract(self, document: AadhaarDocumentInput, user_context: dict[str, Any] | None = None) -> ExtractionResult:
        extension = Path(document.filename).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            return ExtractionResult(
                status=ExtractionStatus.UNSUPPORTED_DOCUMENT,
                document_id=document.document_id,
                error="Only PDF, PNG, JPG, and JPEG Aadhaar documents are supported.",
            )
        mime = (document.mime_type or "").split(";", 1)[0].strip().lower()
        if extension == ".pdf" and mime not in {"", "application/pdf", "application/octet-stream"}:
            return ExtractionResult(status=ExtractionStatus.UNSUPPORTED_DOCUMENT,
                document_id=document.document_id,
                error="The PDF filename and uploaded content type disagree. Upload the original PDF as application/pdf.")
        if len(document.content) > MAX_DOCUMENT_SIZE_BYTES:
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                document_id=document.document_id,
                error="The uploaded document exceeds the supported size limit.",
            )

        pages, extraction_error = self._extract_pages(document, extension)
        usable_pages = [page for page in pages if page.confidence > 0 and self.parser.is_text_usable(page.raw_text)]
        text = "\n".join(page.raw_text for page in usable_pages)
        warnings = [f"Page {page.page_number}: {warning}" for page in pages for warning in page.warnings]
        if extraction_error:
            return ExtractionResult(
                status=extraction_error[0],
                document_id=document.document_id,
                error=extraction_error[1],
                pages=pages, warnings=warnings,
            )
        if not text.strip():
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                document_id=document.document_id,
                error="No readable text could be extracted. Please provide a clearer document or enter the fields manually.",
                pages=pages, warnings=warnings,
            )

        document_type, classification_confidence = self.classifier.classify(text)
        if document_type != DocumentType.AADHAAR:
            return ExtractionResult(
                status=ExtractionStatus.UNSUPPORTED_DOCUMENT,
                document_id=document.document_id,
                error="The uploaded document could not be reliably identified as Aadhaar.",
                pages=pages, warnings=warnings,
            )
        if classification_confidence < 0.4:
            return ExtractionResult(
                status=ExtractionStatus.UNSUPPORTED_DOCUMENT,
                document_id=document.document_id,
                error="The uploaded document could not be reliably identified as Aadhaar.",
                pages=pages, warnings=warnings,
            )

        from agents.knowledge_based.information_retrieval.document_understanding.ocr_engine import OCRLine
        raw_fields = {}
        document_pins = []
        for page in usable_pages:
            lines = [OCRLine.model_validate(line) for line in page.ocr_lines]
            try:
                fields = self.field_extractor.extract_fields(page.raw_text, document_type, page_number=page.page_number, ocr_lines=lines)
            except Exception:
                warnings.append(f"Page {page.page_number}: Field extraction failed; page text remains available for manual correction.")
                continue
            address_evidence = fields.get("address")
            if address_evidence is not None and min(address_evidence.confidence, page.confidence) >= 0.75:
                for pin in sorted(set(re.findall(r"\b[1-9][0-9]{5}\b", address_evidence.value))):
                    document_pins.append(ExtractedField(value=pin,
                        confidence=min(address_evidence.confidence, page.confidence),
                        source_document_id=document.document_id, page_number=address_evidence.page_number,
                        source_region=address_evidence.source_region))
            for key, field in fields.items():
                field = field.model_copy(update={"confidence": min(field.confidence, page.confidence)}, deep=True)
                if key not in raw_fields or field.confidence > raw_fields[key].confidence:
                    raw_fields[key] = field

        # Compare PIN evidence only within the intended address context.
        new_address_field = None
        user_pins = []
        derived_pins = []
        conflicts = {}
        validation_errors = {}
        user_context = user_context or {}
        raw_new_addr = user_context.get("new_address") or user_context.get("address")
        if isinstance(raw_new_addr, str) and raw_new_addr.strip():
            new_address_field = ExtractedField(value=raw_new_addr.strip(), confidence=0.95,
                source_document_id=document.document_id, provenance=FieldProvenance.USER_CONTEXT)
            derived_pins = [ExtractedField(value=pin, confidence=0.95, source_document_id=document.document_id,
                provenance=FieldProvenance.USER_CONTEXT) for pin in sorted(set(re.findall(r"\b[1-9][0-9]{5}\b", raw_new_addr)))]
        if isinstance(user_context.get("new_address"), str) and isinstance(user_context.get("address"), str) and user_context["new_address"].strip() and user_context["address"].strip() and user_context["new_address"].strip() != user_context["address"].strip():
            conflicts["new_address"] = [ExtractedField(value=user_context[key], confidence=0.95,
                source_document_id=document.document_id, provenance=FieldProvenance.USER_CONTEXT) for key in ("new_address", "address")]
            new_address_field = None
        for key in ("pincode", "pin"):
            if key not in user_context:
                continue
            raw_pin = user_context[key]
            if not isinstance(raw_pin, str) or re.fullmatch(r"[1-9][0-9]{5}", raw_pin.strip()) is None:
                validation_errors["pincode"] = "Explicit PIN must be a six-digit string beginning with 1-9."
            else:
                user_pins.append(ExtractedField(value=raw_pin.strip(), confidence=0.95,
                    source_document_id=document.document_id, provenance=FieldProvenance.USER_CONTEXT))
        has_new_address = isinstance(raw_new_addr, str) and bool(raw_new_addr.strip())
        choices = user_pins + derived_pins if has_new_address else user_pins + document_pins
        if len({pin.value for pin in choices}) > 1:
            conflicts["pincode"] = choices
        pincode_field = None
        if "pincode" not in conflicts and "pincode" not in validation_errors:
            preferred = (user_pins or derived_pins) if has_new_address else (user_pins or document_pins)
            if preferred:
                pincode_field = preferred[0].model_copy(deep=True)  # All retained candidates agree.
        for key in conflicts:
            warnings.append(f"Conflicting {key} evidence; explicit citizen correction is required.")
        warnings.extend(validation_errors.values())

        data = AadhaarExtractedData(
            name=self._map_field(raw_fields.get("name"), document.document_id, "name"),
            date_of_birth=self._map_field(raw_fields.get("dob"), document.document_id, "date_of_birth"),
            gender=self._map_field(raw_fields.get("gender"), document.document_id, "gender"),
            masked_aadhaar=self._map_field(raw_fields.get("masked_aadhaar"), document.document_id, "masked_aadhaar"),
            aadhaar_number=self._map_field(raw_fields.get("aadhaar_number"), document.document_id, "aadhaar_number"),
            vid=self._map_field(raw_fields.get("vid"), document.document_id, "vid"),
            existing_address=self._map_field(raw_fields.get("address"), document.document_id, "existing_address"),
            new_address=new_address_field,
            pincode=pincode_field,
        )
        missing_fields = [
            field_name for field_name in REQUIRED_FIELDS
            if getattr(data, field_name) is None or getattr(data, field_name).confidence < 0.75
        ]
        unresolved = sorted(set(conflicts) | set(validation_errors))
        missing_fields = sorted(set(missing_fields) | set(unresolved))
        metadata = {"filename": document.filename, "mime_type": document.mime_type,
                    "size_bytes": len(document.content), "sha256": hashlib.sha256(document.content).hexdigest(),
                    "document_type": document_type.value}
        if missing_fields:
            return ExtractionResult(
                status=ExtractionStatus.MISSING_REQUIRED_FIELDS,
                document_id=document.document_id,
                data=data,
                pages=pages, warnings=warnings,
                conflicts=conflicts, validation_errors=validation_errors, document_metadata=metadata,
                missing_fields=missing_fields,
                error="Some required fields could not be extracted reliably. Please enter or correct them manually.",
            )
        return ExtractionResult(
            status=ExtractionStatus.SUCCESS,
            document_id=document.document_id,
            data=data,
            pages=pages, warnings=warnings,
            conflicts=conflicts, validation_errors=validation_errors, document_metadata=metadata,
        )

    def _extract_text(self, document: AadhaarDocumentInput, extension: str) -> tuple[str, tuple[ExtractionStatus, str] | None]:
        text, lines, err = self._extract_text_and_lines(document, extension)
        return text, err

    def _extract_pages(self, document: AadhaarDocumentInput, extension: str):
        if extension == ".pdf":
            parsed = self.parser.extract_pdf_pages(document.content, self.ocr_engine, fallback_title=document.filename)
            if parsed.status == ParseStatus.ENCRYPTED_PDF:
                return parsed.pages, (ExtractionStatus.ENCRYPTED_DOCUMENT, parsed.error_message)
            if parsed.status == ParseStatus.MALFORMED_PDF:
                return parsed.pages, (ExtractionStatus.MALFORMED_DOCUMENT, "The uploaded PDF is malformed or unreadable.")
            if parsed.status == ParseStatus.EMPTY_DOCUMENT:
                return parsed.pages, (ExtractionStatus.EXTRACTION_FAILED, "The PDF has no readable pages. Upload a non-empty document.")
            return parsed.pages, None
        try:
            lines = self.ocr_engine.extract_lines_from_image(document.content, page_number=1)
            text = "\n".join(line.text for line in lines)
            confidence = sum(line.confidence for line in lines) / len(lines) if lines else 0.0
            if not text.strip():
                text, confidence = self.ocr_engine.extract_text_from_image(document.content)
            page = ExtractedPage(page_number=1, raw_text=text, char_count=len(text.strip()), word_count=len(text.split()),
                extraction_method="ocr", is_ocr_required=True, confidence=confidence,
                ocr_lines=[line.model_copy(update={"page_number": 1}, deep=True).model_dump() for line in lines])
            return [page], None
        except Exception:
            return [], (ExtractionStatus.EXTRACTION_FAILED, "Image OCR could not be completed.")

    def _extract_text_and_lines(self, document: AadhaarDocumentInput, extension: str):
        from agents.knowledge_based.information_retrieval.document_understanding.ocr_engine import OCRLine
        pages, error = self._extract_pages(document, extension)
        usable = [page for page in pages if page.confidence > 0 and self.parser.is_text_usable(page.raw_text)]
        return "\n".join(page.raw_text for page in usable), [OCRLine.model_validate(line) for page in usable for line in page.ocr_lines], error

    @staticmethod
    def _map_field(field, document_id: str, name: str) -> ExtractedField | None:
        if field is None or not field.value.strip():
            return None
        return ExtractedField(
            value=field.value.strip(),
            confidence=field.confidence,
            source_document_id=document_id,
            page_number=field.page_number,
            source_region=field.source_region,
        )


__all__ = ["AadhaarDocumentExtractor", "UnavailableOCREngine"]
