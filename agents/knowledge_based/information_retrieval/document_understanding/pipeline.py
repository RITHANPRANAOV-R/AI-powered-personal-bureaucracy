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
from agents.knowledge_based.information_retrieval.ingestion.parser import DocumentParser
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

        # 2. PDF vs Image Processing Pipeline
        if ext == ".pdf":
            try:
                parsed_pdf = self.parser.parse_pdf(file_bytes, fallback_title=orig_filename)
                page_count = parsed_pdf.total_pages or 1
                direct_text = "\n".join(p.raw_text for p in parsed_pdf.pages) if parsed_pdf.pages else ""

                # OCR Decision Logic: Check if PDF contains direct extractable text
                if len(direct_text.strip()) >= 50 and not parsed_pdf.is_ocr_required:
                    extracted_text = direct_text
                    extraction_method = ExtractionMethod.DIRECT_TEXT_PDF
                    ocr_status = OCRStatus.NOT_REQUIRED
                    avg_confidence = 0.98
                else:
                    logger.info(f"PDF '{orig_filename}' requires OCR (extracted chars < 50). Triggering OCR.")
                    ocr_text, ocr_conf = self.ocr_engine.extract_text_from_image(file_bytes)
                    if ocr_text:
                        extracted_text = ocr_text
                        extraction_method = ExtractionMethod.OCR_SCANNED_PDF
                        ocr_status = OCRStatus.SUCCESS
                        avg_confidence = ocr_conf
                    else:
                        extracted_text = direct_text
                        extraction_method = ExtractionMethod.OCR_SCANNED_PDF
                        ocr_status = OCRStatus.FAILED
                        warnings.append("Scanned PDF OCR produced empty output; using partial text.")
                        avg_confidence = 0.3

            except Exception as e:
                logger.error(f"Error parsing PDF '{orig_filename}': {e}")
                ocr_status = OCRStatus.FAILED
                warnings.append(f"PDF processing error: {str(e)}")

        elif ext in (".png", ".jpg", ".jpeg"):
            extraction_method = ExtractionMethod.OCR_IMAGE
            ocr_text, ocr_conf = self.ocr_engine.extract_text_from_image(file_bytes)
            if ocr_text:
                extracted_text = ocr_text
                ocr_status = OCRStatus.SUCCESS
                avg_confidence = ocr_conf
            else:
                ocr_status = OCRStatus.FAILED
                warnings.append("OCR on image returned empty text.")
                avg_confidence = 0.0

        # 3. Document Classification
        doc_type, class_conf = self.classifier.classify(extracted_text)

        # 4. Structured Field Extraction
        extracted_fields = self.field_extractor.extract_fields(extracted_text, doc_type)

        return UserDocument(
            document_id=doc_id,
            filename=orig_filename,
            mime_type=ext,
            document_type=doc_type,
            classification_confidence=class_conf,
            extraction_method=extraction_method,
            page_count=page_count,
            extracted_text=extracted_text,
            extracted_fields=extracted_fields,
            overall_confidence=round((avg_confidence * 0.7) + (class_conf * 0.3), 4),
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
