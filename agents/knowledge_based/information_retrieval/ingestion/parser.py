"""
Document Parser for extracting structured text and page provenance from PDFs.
"""
import io
import logging
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
import pypdf
from pypdf.errors import PdfReadError

logger = logging.getLogger(__name__)


class ParseStatus(str, Enum):
    """Parsing outcome status for PDF documents."""
    SUCCESS = "success"
    EMPTY_DOCUMENT = "empty_document"
    MALFORMED_PDF = "malformed_pdf"
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

                if c_count == 0:
                    empty_page_count += 1

                total_chars += c_count
                pages.append(
                    ExtractedPage(
                        page_number=page_num,
                        raw_text=text,
                        char_count=c_count,
                        word_count=w_count,
                    )
                )

            # Determine parsing status and OCR requirement
            is_ocr_required = False
            if total_chars < 50 and total_pages > 0:
                status = ParseStatus.SCANNED_OR_IMAGE_ONLY
                is_ocr_required = True
                error_message = "Document contains little to no text; image-only/scanned PDF requiring OCR"
            elif empty_page_count > 0 and empty_page_count < total_pages:
                status = ParseStatus.PARTIAL_EXTRACTION
                error_message = f"Extracted text from {total_pages - empty_page_count}/{total_pages} pages ({empty_page_count} pages were empty)"
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
