"""
Document Parser for extracting structured text and page provenance from PDFs.
"""
import io
import logging
import re
import unicodedata
from collections import Counter
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
import pypdf
from pypdf.errors import PdfReadError

logger = logging.getLogger(__name__)

MIN_DIRECT_TEXT_CHARS = 20


class ParseStatus(str, Enum):
    """Parsing outcome status for PDF documents."""
    SUCCESS = "success"
    EMPTY_DOCUMENT = "empty_document"
    MALFORMED_PDF = "malformed_pdf"
    ENCRYPTED_PDF = "encrypted_pdf"
    SCANNED_OR_IMAGE_ONLY = "scanned_or_image_only"
    PARTIAL_EXTRACTION = "partial_extraction"


class ExtractedPage(BaseModel):
    """
    Represents raw text and metadata extracted from a single document page.
    """
    model_config = ConfigDict(extra="ignore")

    page_number: int = Field(description="1-indexed page number")
    raw_text: str = Field(description="Raw text content extracted from page")
    char_count: int = Field(description="Character count on page")
    word_count: int = Field(description="Word count on page")
    is_ocr_required: bool = False
    extraction_method: str = "direct_text"
    confidence: float = Field(default=0.98, ge=0, le=1)
    ocr_lines: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class ParsedDocument(BaseModel):
    """
    Structured outcome of PDF parsing pipeline.
    """
    model_config = ConfigDict(extra="ignore", use_enum_values=True)

    document_title: Optional[str] = Field(default=None, description="Extracted document title from PDF metadata")
    author: Optional[str] = Field(default=None, description="Author metadata if available")
    creation_date: Optional[str] = Field(default=None, description="Creation date metadata if available")
    total_pages: int = Field(default=0, description="Total page count in document")
    pages: List[ExtractedPage] = Field(default_factory=list, description="List of per-page extracted content")
    status: ParseStatus = Field(default=ParseStatus.SUCCESS, description="Parsing status classification")
    extracted_character_count: int = Field(default=0, description="Total extracted text character count")
    is_ocr_required: bool = Field(default=False, description="Whether OCR is required (e.g. image-only PDF)")
    error_message: Optional[str] = Field(default=None, description="Details if parsing failed")


class DocumentParser:
    """
    Parses PDF bytes using pypdf and extracts per-page text and document metadata.
    """

    def parse_pdf(self, pdf_bytes: bytes, fallback_title: Optional[str] = None) -> ParsedDocument:
        """
        Parses PDF bytes and returns structured ParsedDocument with page provenance.
        """
        if not pdf_bytes or len(pdf_bytes) < 5:
            return ParsedDocument(
                status=ParseStatus.EMPTY_DOCUMENT,
                error_message="Provided PDF byte stream is empty or too short",
            )

        try:
            stream = io.BytesIO(pdf_bytes)
            reader = pypdf.PdfReader(stream)

            if getattr(reader, "is_encrypted", False) and not reader.decrypt(""):
                return ParsedDocument(status=ParseStatus.ENCRYPTED_PDF,
                    error_message="This PDF requires a password. Provide an unlocked copy you are authorized to use.")
            total_pages = len(reader.pages)
            if total_pages == 0:
                return ParsedDocument(
                    total_pages=0,
                    status=ParseStatus.EMPTY_DOCUMENT,
                    error_message="PDF contains zero pages",
                )

            # Metadata extraction
            title = fallback_title
            author = None
            creation_date = None

            if reader.metadata:
                if reader.metadata.title and reader.metadata.title.strip():
                    title = reader.metadata.title.strip()
                if reader.metadata.author and reader.metadata.author.strip():
                    author = reader.metadata.author.strip()
                if reader.metadata.creation_date:
                    creation_date = str(reader.metadata.creation_date)

            pages: List[ExtractedPage] = []
            total_chars = 0
            empty_page_count = 0

            for idx, page in enumerate(reader.pages):
                page_num = idx + 1
                try:
                    text = page.extract_text() or ""
                except Exception as pe:
                    logger.warning(f"Failed to extract text from page {page_num}: {pe}")
                    text = ""

                clean_text = text.strip()
                c_count = len(clean_text)
                w_count = len(clean_text.split()) if clean_text else 0

                needs_ocr = not self.is_text_usable(clean_text) or c_count < MIN_DIRECT_TEXT_CHARS
                if needs_ocr:
                    empty_page_count += 1

                total_chars += c_count
                pages.append(
                    ExtractedPage(
                        page_number=page_num,
                        raw_text=text,
                        char_count=c_count,
                        word_count=w_count,
                        is_ocr_required=needs_ocr,
                    )
                )

            # Aggregate metadata reflects the independent per-page decisions.
            is_ocr_required = empty_page_count > 0
            if empty_page_count == total_pages:
                status = ParseStatus.SCANNED_OR_IMAGE_ONLY
                error_message = "All pages require OCR or text-quality review."
            elif empty_page_count:
                status = ParseStatus.PARTIAL_EXTRACTION
                error_message = f"{empty_page_count}/{total_pages} pages require OCR or text-quality review."
            else:
                status = ParseStatus.SUCCESS
                error_message = None

            return ParsedDocument(
                document_title=title,
                author=author,
                creation_date=creation_date,
                total_pages=total_pages,
                pages=pages,
                status=status,
                extracted_character_count=total_chars,
                is_ocr_required=is_ocr_required,
                error_message=error_message,
            )

        except PdfReadError as pre:
            logger.error(f"Malformed PDF read error: {pre}")
            return ParsedDocument(
                status=ParseStatus.MALFORMED_PDF,
                error_message=f"Malformed PDF format error: {str(pre)}",
            )
        except Exception as e:
            logger.error(f"Unexpected error parsing PDF: {e}")
            return ParsedDocument(
                status=ParseStatus.MALFORMED_PDF,
                error_message=f"Unexpected parsing error: {str(e)}",
            )

    @staticmethod
    def is_text_usable(text: str) -> bool:
        """Conservative corruption checks, not language or semantic inference."""
        compact = "".join(ch for ch in text if not ch.isspace())
        if len(compact) < 4 or sum(ch.isalnum() for ch in compact) < 4:
            return False
        if "\ufffd" in text or re.search(r"\(cid:\d+\)", text):
            return False
        if any(unicodedata.category(ch).startswith("C") and not ch.isspace() for ch in text):
            return False
        if max(Counter(compact).values()) / len(compact) > 0.7:
            return False
        return True

    @staticmethod
    def _render_page(pdf_bytes: bytes, page_number: int) -> bytes:
        try:
            import fitz
            with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
                return pdf[page_number - 1].get_pixmap(dpi=150).tobytes("png")
        except Exception:
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(pdf_bytes)
            try:
                page = pdf[page_number - 1]
                try:
                    bitmap = page.render(scale=2.0)
                    try:
                        image = bitmap.to_pil()
                        try:
                            buffer = io.BytesIO()
                            image.save(buffer, format="PNG")
                            return buffer.getvalue()
                        finally:
                            image.close()
                    finally:
                        bitmap.close()
                finally:
                    page.close()
            finally:
                pdf.close()

    def extract_pdf_pages(self, pdf_bytes: bytes, ocr_engine: Any, fallback_title: Optional[str] = None) -> ParsedDocument:
        """Select direct text/OCR independently and retain all page evidence."""
        parsed = self.parse_pdf(pdf_bytes, fallback_title=fallback_title)
        for page in parsed.pages:
            direct_usable = self.is_text_usable(page.raw_text)
            if not page.is_ocr_required and direct_usable and len(page.raw_text.strip()) >= MIN_DIRECT_TEXT_CHARS:
                continue
            page.is_ocr_required = True
            try:
                image = self._render_page(pdf_bytes, page.page_number)
                lines = ocr_engine.extract_lines_from_image(image, page_number=page.page_number)
                # The parser knows the rendered page even if an OCR implementation defaults to page 1.
                lines = [line.model_copy(update={"page_number": page.page_number}, deep=True) for line in lines]
                text = "\n".join(line.text for line in lines)
                confidence = sum(line.confidence for line in lines) / len(lines) if lines else 0.0
                if not text.strip():
                    text, confidence = ocr_engine.extract_text_from_image(image)
                if self.is_text_usable(text) and confidence >= 0.3 and (not direct_usable or len(text.strip()) >= len(page.raw_text.strip())):
                    page.raw_text = text
                    page.ocr_lines = [line.model_dump() for line in lines]
                    page.confidence = confidence
                    page.extraction_method = "ocr"
                elif direct_usable:
                    page.confidence = 0.7
                    page.warnings.append("OCR did not improve sparse direct text; retained the readable direct text with uncertainty.")
                else:
                    page.confidence = 0.0
                    page.extraction_method = "unreadable"
                    page.warnings.append("Neither direct extraction nor OCR produced usable text.")
            except Exception:
                page.confidence = 0.7 if direct_usable else 0.0
                page.extraction_method = "direct_text" if direct_usable else "unreadable"
                page.warnings.append("Page rendering/OCR failed; readable direct text was retained where available.")
            page.char_count = len(page.raw_text.strip())
            page.word_count = len(page.raw_text.split())
        usable = [page for page in parsed.pages if page.confidence > 0 and self.is_text_usable(page.raw_text)]
        parsed.extracted_character_count = sum(page.char_count for page in usable)
        parsed.is_ocr_required = any(page.is_ocr_required for page in parsed.pages)
        if parsed.pages:
            parsed.status = ParseStatus.SUCCESS if len(usable) == len(parsed.pages) and not any(page.warnings for page in parsed.pages) else ParseStatus.PARTIAL_EXTRACTION
        if parsed.status == ParseStatus.SUCCESS:
            parsed.error_message = None
        return parsed
