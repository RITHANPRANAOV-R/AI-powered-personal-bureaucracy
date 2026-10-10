"""
User Document Understanding Pipeline.
Validates uploads, orchestrates text/OCR extraction, classifies documents, and extracts structured fields.
"""
import os
import uuid
import logging
from typing import Optional, Tuple
from datetime import datetime, timezone

from agents.knowledge_based.information_retrieval.schemas.user_document import (
    UserDocument,
    DocumentType,
    ExtractionMethod,
    OCRStatus,
)
from agents.knowledge_based.information_retrieval.ingestion.parser import DocumentParser, ParseStatus
from agents.knowledge_based.information_retrieval.document_understanding.ocr_engine import (
    BaseOCREngine,
    PaddleOCREngine,
)
from agents.knowledge_based.information_retrieval.document_understanding.extractor import (
    DocumentClassifier,
    FieldExtractor,
)

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB max limit


class UserDocumentPipeline:
    """
    Orchestrates validation, text extraction, OCR decision logic, classification, and field extraction.
    """

    def __init__(
        self,
        parser: Optional[DocumentParser] = None,
        ocr_engine: Optional[BaseOCREngine] = None,
        classifier: Optional[DocumentClassifier] = None,
        field_extractor: Optional[FieldExtractor] = None,
    ):
        self.parser = parser or DocumentParser()
        self.ocr_engine = ocr_engine or PaddleOCREngine()
        self.classifier = classifier or DocumentClassifier()
        self.field_extractor = field_extractor or FieldExtractor()

    def process_file(self, file_path: str, filename: Optional[str] = None) -> UserDocument:
        """
        Main entry point for processing a user document file.
        """
        doc_id = f"doc_{uuid.uuid4().hex[:12]}"
        orig_filename = filename or os.path.basename(file_path)

        # 1. File Validation
        is_valid, val_err, ext = self._validate_file(file_path)
        if not is_valid:
            logger.warning(f"File validation failed for '{orig_filename}': {val_err}")
            return UserDocument(
                document_id=doc_id,
                filename=orig_filename,
                mime_type=ext or "unknown",
                document_type=DocumentType.UNKNOWN,
                ocr_status=OCRStatus.UNSUPPORTED_FORMAT if "unsupported" in val_err.lower() else OCRStatus.FAILED,
                warnings=[val_err],
                overall_confidence=0.0,
            )

        # Read binary content
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        extracted_text = ""
        extraction_method = ExtractionMethod.UNKNOWN
        ocr_status = OCRStatus.NOT_REQUIRED
        avg_confidence = 1.0
        page_count = 1
        warnings = []
        pages = []

        # 2. PDF vs Image Processing Pipeline
        if ext == ".pdf":
            try:
                parsed_pdf = self.parser.extract_pdf_pages(file_bytes, self.ocr_engine, fallback_title=orig_filename)
                if parsed_pdf.status in {ParseStatus.MALFORMED_PDF, ParseStatus.ENCRYPTED_PDF, ParseStatus.EMPTY_DOCUMENT}:
                    return UserDocument(document_id=doc_id, filename=orig_filename, mime_type=ext,
                        ocr_status=OCRStatus.FAILED, overall_confidence=0.0,
                        warnings=[parsed_pdf.error_message or "PDF could not be read."])
                pages = parsed_pdf.pages
                page_count = parsed_pdf.total_pages or 1
                usable = [page for page in pages if page.confidence > 0 and self.parser.is_text_usable(page.raw_text)]
                extracted_text = "\n".join(page.raw_text for page in usable)
                used_ocr = any(page.extraction_method == "ocr" for page in usable)
                extraction_method = ExtractionMethod.OCR_SCANNED_PDF if used_ocr else ExtractionMethod.DIRECT_TEXT_PDF
                avg_confidence = sum(page.confidence for page in usable) / len(usable) if usable else 0.0
                warnings.extend(f"Page {page.page_number}: {warning}" for page in pages for warning in page.warnings)
                if not usable:
                    ocr_status = OCRStatus.FAILED
                    warnings.append("No readable text was extracted. Provide a clearer document or an available local OCR engine.")
                elif len(usable) < len(pages) or any(page.warnings for page in pages):
                    ocr_status = OCRStatus.PARTIAL_SUCCESS
                else:
                    ocr_status = OCRStatus.SUCCESS if used_ocr else OCRStatus.NOT_REQUIRED

            except Exception as e:
                logger.error(f"Error parsing PDF '{orig_filename}': {e}")
                ocr_status = OCRStatus.FAILED
                warnings.append(f"PDF processing error: {str(e)}")

        elif ext in (".png", ".jpg", ".jpeg"):
            extraction_method = ExtractionMethod.OCR_IMAGE
            try:
                ocr_text, ocr_conf = self.ocr_engine.extract_text_from_image(file_bytes)
                if ocr_text:
                    extracted_text = ocr_text
                    ocr_status = OCRStatus.SUCCESS
                    avg_confidence = ocr_conf
                else:
                    ocr_status = OCRStatus.FAILED
                    warnings.append("OCR on image returned empty text.")
                    avg_confidence = 0.0
            except Exception as e:
                logger.error(f"Error performing OCR on image '{orig_filename}': {e}")
                ocr_status = OCRStatus.FAILED
                warnings.append(f"Image OCR processing error: {str(e)}")
                avg_confidence = 0.0

        # 3. Document Classification
        doc_type, class_conf = self.classifier.classify(extracted_text)

        # 4. Structured Field Extraction
        if pages:
            from .ocr_engine import OCRLine
            extracted_fields = {}
            for page in pages:
                if page.confidence <= 0 or not self.parser.is_text_usable(page.raw_text):
                    continue
                fields = self.field_extractor.extract_fields(page.raw_text, doc_type, page_number=page.page_number,
                    ocr_lines=[OCRLine.model_validate(line) for line in page.ocr_lines])
                for key, field in fields.items():
                    field = field.model_copy(update={"confidence": min(field.confidence, page.confidence)}, deep=True)
                    if key not in extracted_fields or field.confidence > extracted_fields[key].confidence:
                        extracted_fields[key] = field
        else:
            extracted_fields = self.field_extractor.extract_fields(extracted_text, doc_type)

        return UserDocument(
            document_id=doc_id,
            filename=orig_filename,
            mime_type=ext,
            document_type=doc_type,
            classification_confidence=class_conf,
            extraction_method=extraction_method,
            page_count=page_count,
            pages=[page.model_dump(mode="json") for page in pages],
            extracted_text=extracted_text,
            extracted_fields=extracted_fields,
            overall_confidence=round((avg_confidence * 0.7) + (class_conf * 0.3), 4) if extracted_text.strip() else 0.0,
            ocr_status=ocr_status,
            warnings=warnings,
        )

    def _validate_file(self, file_path: str) -> Tuple[bool, str, str]:
        """Validates file existence, non-emptiness, size, and extension."""
        if not os.path.exists(file_path):
            return False, f"File path '{file_path}' does not exist", ""

        file_size = os.path.getsize(file_path)
        if file_size == 0:
            return False, f"File '{file_path}' is empty (0 bytes)", ""

        if file_size > MAX_FILE_SIZE_BYTES:
            return False, f"File size ({file_size} bytes) exceeds limit (25MB)", ""

        _, ext_raw = os.path.splitext(file_path)
        ext = ext_raw.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return False, f"Unsupported file extension '{ext}'. Supported: {SUPPORTED_EXTENSIONS}", ext

        return True, "", ext
