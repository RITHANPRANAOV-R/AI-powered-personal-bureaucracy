"""
Unit tests and real live integration tests for Document Ingestion Pipeline.
"""
import unittest
import os
import tempfile
from unittest.mock import MagicMock, patch
import httpx

from agents.knowledge_based.information_retrieval.schemas.source import Source, SourceType
from agents.knowledge_based.information_retrieval.ingestion import (
    DocumentLoader,
    DocumentLoadingError,
    DocumentParser,
    DocumentCleaner,
    DocumentChunker,
    ParsedDocument,
    ExtractedPage,
    ParseStatus,
)


class TestDocumentLoader(unittest.TestCase):
    def setUp(self):
        self.loader = DocumentLoader()

    def test_is_pdf_content(self):
        self.assertTrue(self.loader.is_pdf_content(b"%PDF-1.4\n%..."))
        self.assertFalse(self.loader.is_pdf_content(b"<html>Not a PDF</html>"))
        self.assertFalse(self.loader.is_pdf_content(b""))

    def test_load_from_file_valid(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            tf.write(b"%PDF-1.5 test pdf content stream")
            temp_path = tf.name

        try:
            content, meta = self.loader.load_from_file(temp_path)
            self.assertTrue(content.startswith(b"%PDF-"))
            self.assertEqual(meta["file_path"], temp_path)
            self.assertGreater(meta["content_length"], 0)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_load_from_file_invalid_bytes(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tf:
            tf.write(b"Plain text file content")
            temp_path = tf.name

        try:
            with self.assertRaises(DocumentLoadingError):
                self.loader.load_from_file(temp_path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


class TestDocumentParser(unittest.TestCase):
    def setUp(self):
        self.parser = DocumentParser()

    def test_empty_bytes_handling(self):
        doc = self.parser.parse_pdf(b"")
        self.assertEqual(doc.status, ParseStatus.EMPTY_DOCUMENT)

    def test_malformed_pdf_handling(self):
        doc = self.parser.parse_pdf(b"%PDF-1.4 Corrupted Invalid Byte Stream $$$$")
        self.assertEqual(doc.status, ParseStatus.MALFORMED_PDF)
        self.assertIsNotNone(doc.error_message)

    @patch("pypdf.PdfReader")
    def test_scanned_image_only_pdf_handling(self, mock_pdf_reader):
        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""  # No text extracted from scanned PDF page

        mock_instance = MagicMock()
        mock_instance.pages = [mock_page]
        mock_instance.metadata = None
        mock_pdf_reader.return_value = mock_instance

        doc = self.parser.parse_pdf(b"%PDF-1.4 Scanned PDF stream")
        self.assertEqual(doc.status, ParseStatus.SCANNED_OR_IMAGE_ONLY)
        self.assertTrue(doc.is_ocr_required)
        self.assertEqual(doc.total_pages, 1)

    @patch("pypdf.PdfReader")
    def test_successful_parsing_and_metadata(self, mock_pdf_reader):
        mock_page1 = MagicMock()
        mock_page1.extract_text.return_value = "UIDAI Official Guidelines Page 1 content text."
        mock_page2 = MagicMock()
        mock_page2.extract_text.return_value = "UIDAI Official Guidelines Page 2 content text."

        mock_metadata = MagicMock()
        mock_metadata.title = "UIDAI Citizen Charter"
        mock_metadata.author = "Government of India"
        mock_metadata.creation_date = "2026-01-01"

        mock_instance = MagicMock()
        mock_instance.pages = [mock_page1, mock_page2]
        mock_instance.metadata = mock_metadata
        mock_pdf_reader.return_value = mock_instance

        doc = self.parser.parse_pdf(b"%PDF-1.4 Valid PDF stream")
        self.assertEqual(doc.status, ParseStatus.SUCCESS)
        self.assertFalse(doc.is_ocr_required)
        self.assertEqual(doc.total_pages, 2)
        self.assertEqual(doc.document_title, "UIDAI Citizen Charter")
        self.assertEqual(doc.pages[0].page_number, 1)
        self.assertIn("Page 1 content", doc.pages[0].raw_text)


class TestDocumentCleaner(unittest.TestCase):
    def setUp(self):
        self.cleaner = DocumentCleaner()

    def test_cleaning_noise_and_whitespace(self):
        raw = "Line 1  with   extra   spaces\x00\x07.\n\n\n\nLine 2 after newlines."
        cleaned = self.cleaner.clean_text(raw)
        self.assertNotIn("\x00", cleaned)
        self.assertIn("Line 1 with extra spaces.", cleaned)
        self.assertIn("\n\nLine 2", cleaned)


class TestDocumentChunker(unittest.TestCase):
    def setUp(self):
        self.chunker = DocumentChunker()
        self.source = Source(
            source_id="src_charter",
            authority="UIDAI",
            domain="aadhaar",
            url="https://backend.uidai.gov.in/doc.pdf",
            document_title="UIDAI Citizen Charter",
            last_checked="2026-01-01T00:00:00Z",
        )

    def test_chunking_provenance_preservation(self):
        parsed_doc = ParsedDocument(
            document_title="UIDAI Citizen Charter",
            total_pages=2,
            pages=[
                ExtractedPage(
                    page_number=1,
                    raw_text="This is page one of the official document outlining resident rights and guidelines.",
                    char_count=80,
                    word_count=13,
                ),
                ExtractedPage(
                    page_number=2,
                    raw_text="This is page two detailing grievance redressal officers and escalation timelines.",
                    char_count=82,
                    word_count=12,
                ),
            ],
            status=ParseStatus.SUCCESS,
        )

        chunks = self.chunker.chunk_document(parsed_doc, self.source, chunk_size=100, chunk_overlap=20)
        self.assertGreater(len(chunks), 0)

        # Verify Page and Source Provenance on all chunks
        for chunk in chunks:
            self.assertEqual(chunk.source_id, "src_charter")
            self.assertEqual(chunk.authority, "UIDAI")
            self.assertEqual(chunk.document_title, "UIDAI Citizen Charter")
            self.assertIn(chunk.page_number, [1, 2])
            self.assertTrue(chunk.chunk_id.startswith("src_charter_p"))


class TestOfficialUIDAIDocumentIngestionIntegration(unittest.TestCase):
    """
    REAL integration test performing live HTTP PDF loading, parsing, cleaning, and chunking of an official UIDAI PDF.
    """
    def setUp(self):
        self.loader = DocumentLoader()
        self.parser = DocumentParser()
        self.chunker = DocumentChunker()
        self.official_pdf_url = "https://backend.uidai.gov.in/get/files/media/document/2026-05/Citizen_Charter_Jan24.pdf"
        self.source = Source(
            source_id="src_uidai_citizen_charter_pdf",
            authority="UIDAI",
            domain="aadhaar",
            url=self.official_pdf_url,
            document_title="Citizen's Charter for UIDAI (Jan 2024)",
            source_type=SourceType.OFFICIAL_PDF,
        )

    def test_real_official_uidai_pdf_ingestion(self):
        # 1. Real HTTP Load
        pdf_bytes, load_meta = self.loader.load_from_url(self.official_pdf_url)
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
        self.assertGreater(len(pdf_bytes), 10000)

        # 2. Real Parsing
        parsed_doc = self.parser.parse_pdf(pdf_bytes, fallback_title=self.source.document_title)
        self.assertEqual(parsed_doc.status, ParseStatus.SUCCESS)
        self.assertFalse(parsed_doc.is_ocr_required)
        self.assertGreaterEqual(parsed_doc.total_pages, 25)
        self.assertGreater(parsed_doc.extracted_character_count, 1000)

        # 3. Real Chunking with Provenance
        chunks = self.chunker.chunk_document(parsed_doc, self.source, chunk_size=600, chunk_overlap=100)
        self.assertGreater(len(chunks), 20)

        # Verify first and last chunk page provenance
        first_chunk = chunks[0]
        self.assertEqual(first_chunk.source_id, "src_uidai_citizen_charter_pdf")
        self.assertEqual(first_chunk.authority, "UIDAI")
        self.assertIn("UIDAI", first_chunk.document_title)
        self.assertGreaterEqual(first_chunk.page_number, 1)


if __name__ == "__main__":
    unittest.main()
