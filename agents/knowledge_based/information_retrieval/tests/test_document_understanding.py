"""
Unit tests and real synthetic document integration tests for User Document Understanding & OCR pipeline.
"""
import unittest
import os
import shutil
import tempfile
from PIL import Image, ImageDraw, ImageFont

from agents.knowledge_based.information_retrieval.schemas import (
    UserDocument,
    DocumentType,
    ExtractionMethod,
    OCRStatus,
)
from agents.knowledge_based.information_retrieval.document_understanding import (
    MockOCREngine,
    DocumentClassifier,
    FieldExtractor,
    UserDocumentPipeline,
)


class TestDocumentUnderstandingUnit(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.mock_ocr = MockOCREngine(
            preset_text="GOVERNMENT OF INDIA\nAadhaar Card\nName: Ramesh Kumar\nDOB: 15/08/1985\nGender: MALE\nAddress: Flat 402 Lotus Apartments MG Road Bangalore 560001\n1234 5678 9012",
            preset_confidence=0.96,
        )
        self.classifier = DocumentClassifier()
        self.extractor = FieldExtractor()
        self.pipeline = UserDocumentPipeline(
            ocr_engine=self.mock_ocr,
            classifier=self.classifier,
            field_extractor=self.extractor,
        )

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_document_classification_and_field_extraction(self):
        sample_text = (
            "UNIQUE IDENTIFICATION AUTHORITY OF INDIA\n"
            "Name: Ananya Sharma\n"
            "DOB: 22/11/1992\n"
            "Gender: FEMALE\n"
            "9876 5432 1098\n"
        )
        doc_type, conf = self.classifier.classify(sample_text)
        self.assertEqual(doc_type, DocumentType.AADHAAR)
        self.assertGreaterEqual(conf, 0.4)

        fields = self.extractor.extract_fields(sample_text, doc_type)
        self.assertIn("gender", fields)
        self.assertEqual(fields["gender"].value, "FEMALE")
        self.assertIn("masked_aadhaar", fields)
        # Privacy verification
        self.assertEqual(fields["masked_aadhaar"].value, "XXXX-XXXX-1098")

    def test_invalid_and_unsupported_file_handling(self):
        # 1. Missing file
        doc1 = self.pipeline.process_file(os.path.join(self.temp_dir, "non_existent.pdf"))
        self.assertEqual(doc1.ocr_status, OCRStatus.FAILED)
        self.assertTrue(any("does not exist" in w for w in doc1.warnings))

        # 2. Unsupported extension
        unsupported_path = os.path.join(self.temp_dir, "test.docx")
        with open(unsupported_path, "w") as f:
            f.write("content")
        doc2 = self.pipeline.process_file(unsupported_path)
        self.assertEqual(doc2.ocr_status, OCRStatus.UNSUPPORTED_FORMAT)

    def test_image_document_ocr_pipeline(self):
        # Create synthetic image file
        img_path = os.path.join(self.temp_dir, "test_aadhaar.png")
        img = Image.new("RGB", (300, 150), color=(255, 255, 255))
        img.save(img_path)

        doc = self.pipeline.process_file(img_path)

        self.assertEqual(doc.mime_type, ".png")
        self.assertEqual(doc.extraction_method, ExtractionMethod.OCR_IMAGE)
        self.assertEqual(doc.ocr_status, OCRStatus.SUCCESS)
        self.assertEqual(doc.document_type, DocumentType.AADHAAR)
        self.assertIn("masked_aadhaar", doc.extracted_fields)
        self.assertEqual(doc.extracted_fields["masked_aadhaar"].value, "XXXX-XXXX-9012")


class TestRealSyntheticDocumentIntegration(unittest.TestCase):
    """
    REAL integration test processing a generated synthetic PDF document through UserDocumentPipeline.
    """
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.mock_ocr = MockOCREngine()
        self.pipeline = UserDocumentPipeline(ocr_engine=self.mock_ocr)

        # Create real PDF using reportlab or PyPDF/Bytes
        self.pdf_path = os.path.join(self.temp_dir, "synthetic_aadhaar.pdf")
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas

            c = canvas.Canvas(self.pdf_path, pagesize=letter)
            c.drawString(100, 750, "GOVERNMENT OF INDIA")
            c.drawString(100, 730, "UNIQUE IDENTIFICATION AUTHORITY OF INDIA")
            c.drawString(100, 700, "Name: Vikram Singh")
            c.drawString(100, 680, "DOB: 10/05/1990")
            c.drawString(100, 660, "Gender: MALE")
            c.drawString(100, 640, "Aadhaar No: 4321 8765 2109")
            c.save()
        except ImportError:
            # Fallback simple text PDF generator
            with open(self.pdf_path, "wb") as f:
                f.write(
                    b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
                    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
                    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
                    b"4 0 obj\n<< /Length 200 >>\nstream\nBT /F1 12 Tf 100 700 Td (GOVERNMENT OF INDIA UNIQUE IDENTIFICATION AUTHORITY OF INDIA Name: Vikram Singh DOB: 10/05/1990 Gender: MALE 4321 8765 2109) Tj ET\nendstream\nendobj\n"
                    b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\nxref\n0 6\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\n0000000260 00000 n\n0000000510 00000 n\ntrailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n580\n%%EOF\n"
                )

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_real_pdf_processing_pipeline(self):
        doc: UserDocument = self.pipeline.process_file(self.pdf_path)

        self.assertEqual(doc.mime_type, ".pdf")
        self.assertEqual(doc.extraction_method, ExtractionMethod.DIRECT_TEXT_PDF)
        self.assertEqual(doc.ocr_status, OCRStatus.NOT_REQUIRED)
        self.assertEqual(doc.document_type, DocumentType.AADHAAR)
        self.assertIn("gender", doc.extracted_fields)
        self.assertEqual(doc.extracted_fields["gender"].value, "MALE")
        self.assertIn("masked_aadhaar", doc.extracted_fields)
        self.assertEqual(doc.extracted_fields["masked_aadhaar"].value, "XXXX-XXXX-2109")


if __name__ == "__main__":
    unittest.main()
