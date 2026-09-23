"""
Document Chunker for splitting parsed documents into provenance-preserving chunks.
"""
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict

from agents.knowledge_based.information_retrieval.schemas.source import Source
from agents.knowledge_based.information_retrieval.ingestion.parser import ParsedDocument
from agents.knowledge_based.information_retrieval.ingestion.cleaner import DocumentCleaner

logger = logging.getLogger(__name__)


class DocumentChunk(BaseModel):
    """
    Represents a single text chunk with complete source and page provenance metadata.
    """
    model_config = ConfigDict(extra="ignore")

    chunk_id: str = Field(description="Unique identifier for chunk e.g. src_id_p1_c0")
    source_id: str = Field(description="Associated source ID")
    authority: str = Field(description="Governing authority e.g. UIDAI")
    document_title: str = Field(description="Title of parent document")
    document_url: Optional[str] = Field(default=None, description="URL of parent document if available")
    document_version: Optional[str] = Field(default=None, description="Version or date of parent document")
    page_number: int = Field(description="1-indexed page number from which chunk originated")
    page_range: Optional[List[int]] = Field(default=None, description="Page range if chunk spans multiple pages")
    section: Optional[str] = Field(default=None, description="Section header if detected")
    text: str = Field(description="Cleaned text content of chunk")
    token_count_approx: int = Field(description="Approximate token count (~chars / 4)")
    retrieved_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 retrieval timestamp"
    )
    chunk_index: int = Field(description="0-indexed position within document chunk list")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context metadata")


class DocumentChunker:
    """
    Splits ParsedDocument pages into provenance-preserving text chunks.
    """

    def __init__(self, cleaner: Optional[DocumentCleaner] = None):
        self.cleaner = cleaner or DocumentCleaner()

    def chunk_document(
        self,
        parsed_doc: ParsedDocument,
        source: Source,
        chunk_size: int = 600,
        chunk_overlap: int = 100,
    ) -> List[DocumentChunk]:
        """
        Splits ParsedDocument pages into sliding-window text chunks preserving page provenance.
        """
        if not parsed_doc.pages:
            return []

        chunks: List[DocumentChunk] = []
        global_chunk_idx = 0
        doc_title = parsed_doc.document_title or source.document_title or "Untitled Government Document"

        for page in parsed_doc.pages:
            cleaned_text = self.cleaner.clean_text(page.raw_text)
            if not cleaned_text:
                continue

            # Sliding window over page text
            text_len = len(cleaned_text)
            start = 0

            while start < text_len:
                end = min(start + chunk_size, text_len)
                chunk_text = cleaned_text[start:end].strip()

                if chunk_text:
                    chunk_id = f"{source.source_id}_p{page.page_number}_c{global_chunk_idx}"
                    approx_tokens = max(1, len(chunk_text) // 4)

                    chunk = DocumentChunk(
                        chunk_id=chunk_id,
                        source_id=source.source_id,
                        authority=source.authority,
                        document_title=doc_title,
                        document_url=source.url,
                        document_version=parsed_doc.creation_date or source.last_checked,
                        page_number=page.page_number,
                        page_range=[page.page_number],
                        text=chunk_text,
                        token_count_approx=approx_tokens,
                        retrieved_at=source.last_checked,
                        chunk_index=global_chunk_idx,
                        metadata={
                            "char_length": len(chunk_text),
                            "total_pages": parsed_doc.total_pages,
                        },
                    )
                    chunks.append(chunk)
                    global_chunk_idx += 1

                if end >= text_len:
                    break
                start += chunk_size - chunk_overlap

        return chunks
