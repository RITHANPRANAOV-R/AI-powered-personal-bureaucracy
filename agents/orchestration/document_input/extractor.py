from __future__ import annotations

from pathlib import Path

from agents.knowledge_based.information_retrieval.document_understanding.extractor import (
    DocumentClassifier,
    FieldExtractor,
)
from agents.knowledge_based.information_retrieval.document_understanding.ocr_engine import (
    BaseOCREngine,
    PaddleOCREngine,
)
from agents.knowledge_based.information_retrieval.ingestion.parser import DocumentParser, ParseStatus
from agents.knowledge_based.information_retrieval.schemas.user_document import DocumentType

from .schema import (
    AadhaarDocumentInput,
    AadhaarExtractedData,
    ExtractedField,
    ExtractionResult,
    ExtractionStatus,
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

    def extract(self, document: AadhaarDocumentInput) -> ExtractionResult:
        extension = Path(document.filename).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            return ExtractionResult(
                status=ExtractionStatus.UNSUPPORTED_DOCUMENT,
                document_id=document.document_id,
                error="Only PDF, PNG, JPG, and JPEG Aadhaar documents are supported.",
            )
        if len(document.content) > MAX_DOCUMENT_SIZE_BYTES:
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                document_id=document.document_id,
                error="The uploaded document exceeds the supported size limit.",
            )

        text, extraction_error = self._extract_text(document, extension)
        if extraction_error:
            return ExtractionResult(
                status=extraction_error[0],
                document_id=document.document_id,
                error=extraction_error[1],
            )
        if not text.strip():
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                document_id=document.document_id,
                error="No readable text could be extracted. Please provide a clearer document or enter the fields manually.",
            )

        document_type, classification_confidence = self.classifier.classify(text)
        if document_type != DocumentType.AADHAAR:
            return ExtractionResult(
                status=ExtractionStatus.UNSUPPORTED_DOCUMENT,
                document_id=document.document_id,
                error="The uploaded document could not be reliably identified as Aadhaar.",
            )
        if classification_confidence < 0.4:
            return ExtractionResult(
                status=ExtractionStatus.UNSUPPORTED_DOCUMENT,
                document_id=document.document_id,
                error="The uploaded document could not be reliably identified as Aadhaar.",
            )

        raw_fields = self.field_extractor.extract_fields(text, document_type)
        data = AadhaarExtractedData(
            name=self._map_field(raw_fields.get("name"), document.document_id, "name"),
            date_of_birth=self._map_field(raw_fields.get("dob"), document.document_id, "date_of_birth"),
            gender=self._map_field(raw_fields.get("gender"), document.document_id, "gender"),
            masked_aadhaar=self._map_field(raw_fields.get("masked_aadhaar"), document.document_id, "masked_aadhaar"),
            existing_address=self._map_field(raw_fields.get("address"), document.document_id, "existing_address"),
        )
        missing_fields = [
            field_name for field_name in REQUIRED_FIELDS
            if getattr(data, field_name) is None or getattr(data, field_name).confidence < 0.75
        ]
        if missing_fields:
            return ExtractionResult(
                status=ExtractionStatus.MISSING_REQUIRED_FIELDS,
                document_id=document.document_id,
                data=data,
                missing_fields=missing_fields,
                error="Some required fields could not be extracted reliably. Please enter or correct them manually.",
            )
        return ExtractionResult(
            status=ExtractionStatus.SUCCESS,
            document_id=document.document_id,
            data=data,
        )

    def _extract_text(self, document: AadhaarDocumentInput, extension: str) -> tuple[str, tuple[ExtractionStatus, str] | None]:
        if extension == ".pdf":
            parsed = self.parser.parse_pdf(document.content, fallback_title=document.filename)
            if parsed.status == ParseStatus.MALFORMED_PDF:
                return "", (ExtractionStatus.MALFORMED_DOCUMENT, "The uploaded PDF is malformed or unreadable.")
            direct_text = "\n".join(page.raw_text for page in parsed.pages)
            if direct_text.strip() and not parsed.is_ocr_required:
                return direct_text, None

            # Scanned PDF: render pages to images and run OCR
            try:
                import io
                import pypdfium2 as pdfium
                pdf = pdfium.PdfDocument(document.content)
                ocr_texts = []
                for page in pdf:
                    img = page.render(scale=2.0).to_pil()
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    page_text, conf = self.ocr_engine.extract_text_from_image(buf.getvalue())
                    if page_text.strip():
                        ocr_texts.append(page_text)
                combined_ocr = "\n".join(ocr_texts)
                if combined_ocr.strip():
                    return combined_ocr, None
            except Exception:
                pass

            text, confidence = self.ocr_engine.extract_text_from_image(document.content)
            if text.strip() and confidence > 0.0:
                return text, None
            return "", (ExtractionStatus.EXTRACTION_FAILED, "This PDF appears to be scanned, but no local OCR engine is available for it.")

        text, confidence = self.ocr_engine.extract_text_from_image(document.content)
        if text.strip() and confidence > 0.0:
            return text, None
        return "", (ExtractionStatus.EXTRACTION_FAILED, "No local OCR engine produced readable text from the image.")

    @staticmethod
    def _map_field(field, document_id: str, name: str) -> ExtractedField | None:
        if field is None or not field.value.strip():
            return None
        return ExtractedField(
            value=field.value.strip(),
            confidence=field.confidence,
            source_document_id=document_id,
            page_number=field.page_number,
        )


__all__ = ["AadhaarDocumentExtractor", "UnavailableOCREngine"]
