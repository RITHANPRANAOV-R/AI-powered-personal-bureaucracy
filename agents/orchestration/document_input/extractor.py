from __future__ import annotations

from pathlib import Path
import re

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
        if len(document.content) > MAX_DOCUMENT_SIZE_BYTES:
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                document_id=document.document_id,
                error="The uploaded document exceeds the supported size limit.",
            )

        text, ocr_lines, extraction_error = self._extract_text_and_lines(document, extension)
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

        raw_fields = self.field_extractor.extract_fields(text, document_type, ocr_lines=ocr_lines)

        # Context-based autofill for new address and pincode from user request
        new_address_field = None
        pincode_field = None
        if user_context:
            raw_new_addr = user_context.get("new_address") or user_context.get("address")
            if raw_new_addr and isinstance(raw_new_addr, str) and raw_new_addr.strip():
                new_address_field = ExtractedField(
                    value=raw_new_addr.strip(),
                    confidence=0.95,
                    source_document_id=document.document_id,
                    provenance=FieldProvenance.USER_CONTEXT,
                )
                pin_match = re.search(r"\b[1-9]\d{5}\b", raw_new_addr)
                if pin_match:
                    pincode_field = ExtractedField(
                        value=pin_match.group(0),
                        confidence=0.95,
                        source_document_id=document.document_id,
                        provenance=FieldProvenance.USER_CONTEXT,
                    )
            raw_pin = user_context.get("pincode") or user_context.get("pin")
            if raw_pin and isinstance(raw_pin, str) and re.fullmatch(r"[1-9]\d{5}", raw_pin.strip()):
                pincode_field = ExtractedField(
                    value=raw_pin.strip(),
                    confidence=0.95,
                    source_document_id=document.document_id,
                    provenance=FieldProvenance.USER_CONTEXT,
                )

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
        text, lines, err = self._extract_text_and_lines(document, extension)
        return text, err

    def _extract_text_and_lines(
        self, document: AadhaarDocumentInput, extension: str
    ) -> tuple[str, list[Any], tuple[ExtractionStatus, str] | None]:
        if extension == ".pdf":
            parsed = self.parser.parse_pdf(document.content, fallback_title=document.filename)
            if parsed.status == ParseStatus.MALFORMED_PDF:
                return "", [], (ExtractionStatus.MALFORMED_DOCUMENT, "The uploaded PDF is malformed or unreadable.")
            direct_text = "\n".join(page.raw_text for page in parsed.pages)
            if direct_text.strip() and not parsed.is_ocr_required:
                return direct_text, [], None

            # Scanned PDF: render pages to images and run OCR
            try:
                import fitz  # PyMuPDF
                pdf_doc = fitz.open(stream=document.content, filetype="pdf")
                ocr_texts = []
                all_ocr_lines = []
                for p_idx, page in enumerate(pdf_doc, start=1):
                    pix = page.get_pixmap(dpi=150)
                    img_bytes = pix.tobytes("png")
                    lines = self.ocr_engine.extract_lines_from_image(img_bytes, page_number=p_idx)
                    page_text = "\n".join(l.text for l in lines) if lines else ""
                    if not page_text:
                        page_text, conf = self.ocr_engine.extract_text_from_image(img_bytes)
                    if page_text.strip():
                        ocr_texts.append(page_text)
                    all_ocr_lines.extend(lines)
                pdf_doc.close()
                combined_ocr = "\n".join(ocr_texts)
                if combined_ocr.strip():
                    return combined_ocr, all_ocr_lines, None
            except Exception:
                try:
                    import io
                    import pypdfium2 as pdfium
                    pdf = pdfium.PdfDocument(document.content)
                    ocr_texts = []
                    all_ocr_lines = []
                    for p_idx, page in enumerate(pdf, start=1):
                        img = page.render(scale=2.0).to_pil()
                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        lines = self.ocr_engine.extract_lines_from_image(buf.getvalue(), page_number=p_idx)
                        page_text = "\n".join(l.text for l in lines) if lines else ""
                        if not page_text:
                            page_text, conf = self.ocr_engine.extract_text_from_image(buf.getvalue())
                        if page_text.strip():
                            ocr_texts.append(page_text)
                        all_ocr_lines.extend(lines)
                    combined_ocr = "\n".join(ocr_texts)
                    if combined_ocr.strip():
                        return combined_ocr, all_ocr_lines, None
                except Exception:
                    pass

            return "", [], (ExtractionStatus.EXTRACTION_FAILED, "This PDF appears to be scanned, but no local OCR engine is available for it.")

        lines = self.ocr_engine.extract_lines_from_image(document.content)
        text = "\n".join(l.text for l in lines) if lines else ""
        if not text.strip():
            text, confidence = self.ocr_engine.extract_text_from_image(document.content)
        if text.strip():
            return text, lines, None
        return "", [], (ExtractionStatus.EXTRACTION_FAILED, "No local OCR engine produced readable text from the image.")

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
