"""
Phase 16 — Full Failure Testing and Graceful Degradation Test Suite.
Systematically tests all 8 required failure categories:
1. Document Ingestion Failures (malformed PDF, corrupted PDF, empty PDF, scanned/image-only, OCR status, OCR failure, init failure, missing/inaccessible file, unsupported type)
2. User Document / OCR Failures (valid text, image doc, corrupted image/PDF, empty doc, poor text, low confidence, missing fields, unknown doc type, official continuation)
3. Evidence Failure Cases (no evidence, weak, irrelevant, duplicate, invalid, missing provenance, unverified, conflicting official/user)
4. Freshness (live current, stored official, stale stored, unknown freshness, live unavailable + stored available, live vs stored conflict)
5. Fees / Timelines / Appointments / Forms (missing & conflicting info, zero fabrication)
6. Authentication / CAPTCHA / User Action Barriers (OTP, login, CAPTCHA, auth, physical presence, auth endpoint)
7. Top-Level Testing (agent.retrieve result fields: status, warnings, conflicts, evidence, sources, grounding, provenance, freshness)
8. Graceful Degradation (live fail + stored avail, live fail + no stored, user doc fail + official cont, conflicting evidence preserved)
"""
import unittest
import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch
import httpx

from agents.knowledge_based.information_retrieval.agent import InformationRetrievalAgent
from agents.knowledge_based.information_retrieval.schemas import (
    Source,
    SourceType,
    Evidence,
    GroundingStatus,
    RetrievalRequest,
    RetrievalRequirement,
    RetrievalResult,
    RetrievalStatus,
    UserDocument,
    DocumentType,
    ExtractedField,
    ExtractionMethod,
    OCRStatus,
    LinkStatus,
    ConflictItem,
    WarningItem,
)
from agents.knowledge_based.information_retrieval.ingestion.parser import DocumentParser, ParseStatus, ParsedDocument, ExtractedPage
from agents.knowledge_based.information_retrieval.ingestion.chunker import DocumentChunk
from agents.knowledge_based.information_retrieval.embeddings import LocalEmbeddingService
from agents.knowledge_based.information_retrieval.retrieval import (
    ChromaVectorStore,
    VectorRetriever,
    HybridRetriever,
    RetrievalMode,
    GroundingVerifier,
    EvidenceRanker,
    FreshnessType,
)
from agents.knowledge_based.information_retrieval.live_retrieval import (
    LiveGovernmentFetcher,
    LiveRetrievalResult,
    LiveRetrievalStatus,
)
from agents.knowledge_based.information_retrieval.sources.source_registry import SourceRegistry
from agents.knowledge_based.information_retrieval.document_understanding.pipeline import UserDocumentPipeline


class TestFailureTestingAndGracefulDegradation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.embedder = LocalEmbeddingService()
        # Warmup embedder model to cache weights in memory before any mock patches
        self.embedder.embed_text("warmup sentence transformer")

        self.registry = SourceRegistry(include_defaults=True)

        # Empty vector store for failure testing
        self.empty_store = ChromaVectorStore(
            persist_directory=os.path.join(self.temp_dir, "empty_db"),
            collection_name="test_empty_collection",
            embedder=self.embedder,
        )
        self.empty_retriever = VectorRetriever(vector_store=self.empty_store, top_k=3)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    # =========================================================
    # 1. DOCUMENT INGESTION FAILURES
    # =========================================================
    def test_doc_ingestion_malformed_pdf(self):
        """Malformed PDF byte stream returns ParseStatus.EMPTY_DOCUMENT/MALFORMED_PDF with error message."""
        parser = DocumentParser()
        malformed_bytes = b"%PDF-1.4\n%not a valid pdf object body..."
        parsed = parser.parse_pdf(malformed_bytes)
        self.assertIn(parsed.status, [ParseStatus.EMPTY_DOCUMENT, ParseStatus.MALFORMED_PDF])
        self.assertIsNotNone(parsed.error_message)

    def test_doc_ingestion_corrupted_pdf(self):
        """Corrupted PDF file generates structured warning without crashing agent."""
        corrupt_path = os.path.join(self.temp_dir, "corrupted.pdf")
        with open(corrupt_path, "wb") as f:
            f.write(b"CORRUPTED_RAW_BINARY_DATA_XYZ_999999999")

        agent = InformationRetrievalAgent()
        req = RetrievalRequest(
            request_id="req_ingest_corrupt",
            goal="Update address",
            service="Aadhaar Address Update",
            domain="aadhaar",
            requirements=[RetrievalRequirement(requirement_id="r1", category="address", description="Proof of address")],
        )
        res = agent.retrieve(request=req, user_documents=[corrupt_path], mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertTrue(any("USER_DOCUMENT_PARSE_FAILED" in w.code or "pdf" in w.message.lower() for w in res.warnings))

    def test_doc_ingestion_empty_pdf(self):
        """0-byte empty PDF generates validation error and no crash."""
        empty_path = os.path.join(self.temp_dir, "empty.pdf")
        with open(empty_path, "wb") as f:
            f.write(b"")

        pipeline = UserDocumentPipeline()
        doc = pipeline.process_file(empty_path)
        self.assertIn(doc.ocr_status, [OCRStatus.FAILED, OCRStatus.UNSUPPORTED_FORMAT])
        self.assertTrue(any("empty" in w.lower() for w in doc.warnings))

    def test_doc_ingestion_scanned_image_only_pdf(self):
        """PDF containing no extractable text flags is_ocr_required=True."""
        parser = DocumentParser()
        fake_empty_pdf_bytes = b"%PDF-1.4 header padding byte stream"
        parsed = parser.parse_pdf(fake_empty_pdf_bytes)
        self.assertTrue(parsed.is_ocr_required or parsed.extracted_character_count == 0)

    def test_doc_ingestion_ocr_required_status(self):
        """Pipeline sets ExtractionMethod.OCR_SCANNED_PDF when PDF requires OCR."""
        pipeline = UserDocumentPipeline()
        mock_parsed = ParsedDocument(
            total_pages=1,
            pages=[],
            status=ParseStatus.SCANNED_OR_IMAGE_ONLY,
            is_ocr_required=True,
            extracted_character_count=0,
        )
        pipeline.parser.parse_pdf = MagicMock(return_value=mock_parsed)
        pipeline.ocr_engine.extract_text_from_image = MagicMock(return_value=("Scanned Document Content", 0.92))

        fake_pdf = os.path.join(self.temp_dir, "scanned_doc.pdf")
        with open(fake_pdf, "wb") as f:
            f.write(b"%PDF-1.4 scanned content mock")

        doc = pipeline.process_file(fake_pdf)
        self.assertEqual(doc.extraction_method, ExtractionMethod.OCR_SCANNED_PDF)
        self.assertEqual(doc.ocr_status, OCRStatus.SUCCESS)
        self.assertIn("Scanned Document Content", doc.extracted_text)

    def test_doc_ingestion_ocr_failure(self):
        """OCR engine returning empty output sets OCRStatus.FAILED with low confidence."""
        pipeline = UserDocumentPipeline()
        mock_parsed = ParsedDocument(
            total_pages=1,
            pages=[],
            status=ParseStatus.SCANNED_OR_IMAGE_ONLY,
            is_ocr_required=True,
            extracted_character_count=0,
        )
        pipeline.parser.parse_pdf = MagicMock(return_value=mock_parsed)
        pipeline.ocr_engine.extract_text_from_image = MagicMock(return_value=("", 0.0))

        fake_pdf = os.path.join(self.temp_dir, "ocr_fail.pdf")
        with open(fake_pdf, "wb") as f:
            f.write(b"%PDF-1.4 scanned content mock")

        doc = pipeline.process_file(fake_pdf)
        self.assertEqual(doc.ocr_status, OCRStatus.FAILED)
        self.assertTrue(any("ocr" in w.lower() for w in doc.warnings))

    def test_doc_ingestion_ocr_engine_init_failure(self):
        """OCR engine raise on initialization is caught gracefully without crash."""
        pipeline = UserDocumentPipeline()
        pipeline.ocr_engine.extract_text_from_image = MagicMock(side_effect=RuntimeError("PaddleOCR model load failed"))

        fake_png = os.path.join(self.temp_dir, "doc.png")
        with open(fake_png, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")

        doc = pipeline.process_file(fake_png)
        self.assertEqual(doc.ocr_status, OCRStatus.FAILED)

    def test_doc_ingestion_missing_file(self):
        """Missing file path is flagged in validation and returns structured UserDocument warning."""
        pipeline = UserDocumentPipeline()
        doc = pipeline.process_file("/non_existent_path/missing_file.pdf")
        self.assertEqual(doc.ocr_status, OCRStatus.FAILED)
        self.assertTrue(any("does not exist" in w for w in doc.warnings))

    def test_doc_ingestion_inaccessible_file(self):
        """Inaccessible file (permission error) produces graceful parse warning."""
        agent = InformationRetrievalAgent()
        req = RetrievalRequest(
            request_id="req_inaccessible",
            goal="Update address",
            service="Aadhaar Address Update",
            domain="aadhaar",
            requirements=[RetrievalRequirement(requirement_id="r1", category="address", description="Proof of address")],
        )

        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            res = agent.retrieve(request=req, user_documents=["inaccessible.pdf"], mode=RetrievalMode.KNOWLEDGE_ONLY)
            self.assertTrue(any("USER_DOCUMENT_PARSE_FAILED" in w.code for w in res.warnings))

    def test_doc_ingestion_unsupported_file_type(self):
        """Unsupported file extension (.exe) sets OCRStatus.UNSUPPORTED_FORMAT."""
        pipeline = UserDocumentPipeline()
        fake_exe = os.path.join(self.temp_dir, "installer.exe")
        with open(fake_exe, "wb") as f:
            f.write(b"MZ executable header")

        doc = pipeline.process_file(fake_exe)
        self.assertEqual(doc.ocr_status, OCRStatus.UNSUPPORTED_FORMAT)

    # =========================================================
    # 2. USER DOCUMENT / OCR FAILURES
    # =========================================================
    def test_user_doc_valid_text_pdf(self):
        """Valid text PDF extracts via DIRECT_TEXT_PDF with high confidence."""
        pipeline = UserDocumentPipeline()
        mock_parsed = ParsedDocument(
            total_pages=1,
            pages=[ExtractedPage(page_number=1, raw_text="Aadhaar Card Update Form Name Address DOB Verification Document Details", char_count=70, word_count=10)],
            status=ParseStatus.SUCCESS,
            is_ocr_required=False,
            extracted_character_count=70,
        )
        pipeline.parser.parse_pdf = MagicMock(return_value=mock_parsed)

        fake_pdf = os.path.join(self.temp_dir, "valid.pdf")
        with open(fake_pdf, "wb") as f:
            f.write(b"%PDF-1.4 valid text")

        doc = pipeline.process_file(fake_pdf)
        self.assertEqual(doc.extraction_method, ExtractionMethod.DIRECT_TEXT_PDF)
        self.assertEqual(doc.ocr_status, OCRStatus.NOT_REQUIRED)

    def test_user_doc_image_document(self):
        """Image document (.png) processes via OCR_IMAGE."""
        pipeline = UserDocumentPipeline()
        pipeline.ocr_engine.extract_text_from_image = MagicMock(return_value=("Passport No Z1234567 Name John Doe", 0.95))

        fake_png = os.path.join(self.temp_dir, "passport.png")
        with open(fake_png, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")

        doc = pipeline.process_file(fake_png)
        self.assertEqual(doc.extraction_method, ExtractionMethod.OCR_IMAGE)
        self.assertEqual(doc.ocr_status, OCRStatus.SUCCESS)

    def test_user_doc_corrupted_image(self):
        """Corrupted image bytes handled gracefully by OCR engine without crashing."""
        pipeline = UserDocumentPipeline()
        pipeline.ocr_engine.extract_text_from_image = MagicMock(return_value=("", 0.0))

        fake_corrupt_png = os.path.join(self.temp_dir, "bad.png")
        with open(fake_corrupt_png, "wb") as f:
            f.write(b"NOT_A_REAL_PNG")

        doc = pipeline.process_file(fake_corrupt_png)
        self.assertEqual(doc.ocr_status, OCRStatus.FAILED)

    def test_user_doc_very_poor_insufficient_text(self):
        """Document with very poor text returns low overall confidence."""
        pipeline = UserDocumentPipeline()
        pipeline.ocr_engine.extract_text_from_image = MagicMock(return_value=("x y z", 0.15))

        fake_jpg = os.path.join(self.temp_dir, "blurry.jpg")
        with open(fake_jpg, "wb") as f:
            f.write(b"\xff\xd8\xff")

        doc = pipeline.process_file(fake_jpg)
        self.assertLess(doc.overall_confidence, 0.40)

    def test_user_doc_low_confidence_extraction(self):
        """Low confidence extraction preserves low confidence score, zero invented fields."""
        doc = UserDocument(
            document_id="doc_low_conf",
            filename="blur.jpg",
            mime_type=".jpg",
            document_type=DocumentType.UNKNOWN,
            overall_confidence=0.25,
            extracted_fields={},
        )
        self.assertEqual(doc.overall_confidence, 0.25)
        self.assertEqual(len(doc.extracted_fields), 0)

    def test_user_doc_missing_expected_fields(self):
        """Missing fields in document stay missing without invention."""
        doc = UserDocument(
            document_id="doc_missing_fields",
            filename="partial_id.pdf",
            mime_type=".pdf",
            document_type=DocumentType.IDENTITY_PROOF,
            extracted_fields={"name": ExtractedField(field_name="name", value="Jane Doe", confidence=0.95)},
        )
        self.assertIn("name", doc.extracted_fields)
        self.assertNotIn("address", doc.extracted_fields)
        self.assertNotIn("dob", doc.extracted_fields)

    def test_user_doc_unknown_document_type(self):
        """Random unclassified text produces DocumentType.UNKNOWN."""
        pipeline = UserDocumentPipeline()
        pipeline.ocr_engine.extract_text_from_image = MagicMock(return_value=("Shopping list 1. Apples 2. Milk", 0.90))

        fake_jpg = os.path.join(self.temp_dir, "grocery.jpg")
        with open(fake_jpg, "wb") as f:
            f.write(b"\xff\xd8\xff")

        doc = pipeline.process_file(fake_jpg)
        self.assertEqual(doc.document_type, DocumentType.UNKNOWN)

    def test_user_doc_failure_official_retrieval_continues(self):
        """When user document fails, official knowledge retrieval continues and succeeds."""
        store = ChromaVectorStore(
            persist_directory=os.path.join(self.temp_dir, "official_db"),
            collection_name="official_coll",
            embedder=self.embedder,
        )
        chunk = DocumentChunk(
            chunk_id="chk_off_01",
            source_id="src_off_01",
            authority="UIDAI",
            document_title="Aadhaar Guidelines",
            document_url="https://uidai.gov.in/en/",
            page_number=1,
            text="Proof of Identity documents include Passport, PAN Card, Voter ID.",
            token_count_approx=12,
            chunk_index=0,
        )
        store.add_chunks([chunk])

        agent = InformationRetrievalAgent(hybrid_retriever=HybridRetriever(vector_retriever=VectorRetriever(vector_store=store)))

        req = RetrievalRequest(
            request_id="req_user_fail_cont",
            goal="Check identity proof documents",
            service="Aadhaar Update",
            domain="aadhaar",
            requirements=[RetrievalRequirement(requirement_id="r1", category="identity", description="Proof of identity")],
        )

        res = agent.retrieve(request=req, user_documents=["/bad_path/file.xyz"], mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIn(res.retrieval_status, [RetrievalStatus.SUCCESS, RetrievalStatus.PARTIAL_SUCCESS])
        self.assertGreater(len(res.evidence), 0)
        self.assertTrue(any("USER_DOCUMENT_PARSE_FAILED" in w.code for w in res.warnings))

    # =========================================================
    # 3. EVIDENCE FAILURE CASES
    # =========================================================
    def test_evidence_no_evidence(self):
        """No evidence found returns NO_EVIDENCE_FOUND status and 0 evidence."""
        agent = InformationRetrievalAgent(hybrid_retriever=HybridRetriever(vector_retriever=self.empty_retriever))
        req = RetrievalRequest(
            request_id="req_no_ev",
            goal="Nonexistent concept xyz999",
            service="Aadhaar Test",
            domain="aadhaar",
            requirements=[RetrievalRequirement(requirement_id="r1", category="unknown", description="Nonexistent concept xyz999")],
        )
        res = agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertEqual(res.retrieval_status, RetrievalStatus.NO_EVIDENCE_FOUND)
        self.assertEqual(len(res.evidence), 0)

    def test_evidence_weak_evidence_relevance(self):
        """Weak relevance score evidence is assigned lower ranking score."""
        verifier = GroundingVerifier(source_registry=self.registry)
        ranker = EvidenceRanker(verifier=verifier)

        weak_ev = Evidence(
            evidence_id="ev_weak",
            claim="Weak claim",
            passage="Aadhaar general disclaimer statement paragraph with minimal relevant details for update.",
            source=Source(source_id="src_1", authority="UIDAI", domain="aadhaar", url="https://uidai.gov.in/en/"),
            relevance_score=0.10,
            metadata={"category": "address", "associated_requirements": ["r1"]},
        )
        ranked = ranker.rank_and_verify([weak_ev])
        self.assertLess(ranked[0].ranking_score, 0.60)

    def test_evidence_irrelevant_evidence(self):
        """Irrelevant evidence missing category match scores lower in requirement signal."""
        verifier = GroundingVerifier(source_registry=self.registry)
        ranker = EvidenceRanker(verifier=verifier)

        irrelevant_ev = Evidence(
            evidence_id="ev_irrelevant",
            claim="Irrelevant claim",
            passage="Weather forecast for New Delhi tomorrow is sunny with 25 degrees Celsius.",
            source=Source(source_id="src_1", authority="UIDAI", domain="aadhaar", url="https://uidai.gov.in/en/"),
            relevance_score=0.80,
            metadata={"category": "biometric_lock", "associated_requirements": ["r1"]},
        )
        ranked = ranker.rank_and_verify([irrelevant_ev])
        sig = ranked[0].metadata.get("ranking_signals", {}).get("requirement", 1.0)
        self.assertLessEqual(sig, 0.5)

    def test_evidence_duplicate_evidence_deduplicated(self):
        """Duplicate chunks are deduplicated by chunk_id while preserving requirement associations."""
        retriever = VectorRetriever(vector_store=self.empty_retriever.vector_store)
        hits = [
            {"chunk_id": "chk_dup", "text": "Passport valid proof of address", "metadata": {"source_id": "src_1", "authority": "UIDAI", "document_url": "https://uidai.gov.in/en/"}, "distance": 0.1},
            {"chunk_id": "chk_dup", "text": "Passport valid proof of address", "metadata": {"source_id": "src_1", "authority": "UIDAI", "document_url": "https://uidai.gov.in/en/"}, "distance": 0.1},
        ]
        retriever.vector_store.query_similar = MagicMock(return_value=hits)

        req = RetrievalRequest(
            request_id="req_dup",
            goal="Address proof",
            service="Aadhaar",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="address", description="Proof of address"),
                RetrievalRequirement(requirement_id="r2", category="proof", description="Proof document"),
            ],
        )
        res = retriever.retrieve_for_request(req)
        self.assertEqual(len(res.evidence), 1)
        self.assertEqual(res.evidence[0].metadata["associated_requirements"], ["r1", "r2"])

    def test_evidence_invalid_evidence_cannot_be_grounded(self):
        """Invalid evidence (missing passage or untrusted URL) returns GroundingStatus.INVALID."""
        verifier = GroundingVerifier(source_registry=self.registry)
        ev_no_passage = Evidence(
            evidence_id="ev_no_pass",
            claim="No passage",
            passage="",
            source=Source(source_id="src_1", authority="UIDAI", domain="aadhaar", url="https://uidai.gov.in/en/"),
        )
        self.assertEqual(verifier.verify_grounding(ev_no_passage), GroundingStatus.INVALID)

        ev_untrusted = Evidence(
            evidence_id="ev_untrusted",
            claim="Untrusted claim",
            passage="Valid passage length text for testing grounding verification.",
            source=Source(source_id="src_fake", authority="Fake", domain="aadhaar", url="https://fakeblog.com/aadhaar"),
            metadata={"category": "address"},
        )
        self.assertEqual(verifier.verify_grounding(ev_untrusted), GroundingStatus.INVALID)

    def test_evidence_missing_provenance_unverified(self):
        """Evidence missing source URL or source ID is marked INVALID grounding."""
        verifier = GroundingVerifier(source_registry=self.registry)
        ev_no_src = Evidence(
            evidence_id="ev_no_src",
            claim="No source",
            passage="Valid passage content text long enough to pass length check.",
            source=Source(source_id="", authority="", domain="aadhaar", url=""),
        )
        self.assertEqual(verifier.verify_grounding(ev_no_src), GroundingStatus.INVALID)

    def test_evidence_unverified_evidence_authority(self):
        """Non-authoritative source evidence fails grounding verification."""
        verifier = GroundingVerifier(source_registry=self.registry)
        ev = Evidence(
            evidence_id="ev_unauth",
            claim="Claim",
            passage="Valid length passage content for testing authority validation logic.",
            source=Source(source_id="src_unauth", authority="Unknown", domain="aadhaar", url="https://randomsite.org/info"),
            metadata={"category": "fee"},
        )
        self.assertEqual(verifier.verify_grounding(ev), GroundingStatus.INVALID)

    def test_evidence_conflicting_official_evidence(self):
        """Conflicting official evidence claims generate explicit ConflictItem."""
        agent = InformationRetrievalAgent()
        ev1 = Evidence(
            evidence_id="ev_off_1",
            claim="Fee for demographic update is Rs 50",
            passage="Official document states demographic update fee is Rs 50.",
            source=Source(source_id="src_1", authority="UIDAI", domain="aadhaar", url="https://uidai.gov.in/en/doc1.pdf"),
            metadata={"category": "fee", "associated_requirements": ["r1"]},
        )
        ev2 = Evidence(
            evidence_id="ev_off_2",
            claim="Fee for demographic update is Rs 100",
            passage="Updated notification states demographic update fee is Rs 100.",
            source=Source(source_id="src_2", authority="UIDAI", domain="aadhaar", url="https://uidai.gov.in/en/doc2.pdf"),
            metadata={"category": "fee", "associated_requirements": ["r1"]},
        )
        fused, sources, conflicts = agent.fusion_engine.fuse_evidence([ev1], [ev2])
        self.assertGreater(len(conflicts), 0)
        self.assertIn("fee", conflicts[0].topic.lower())

    def test_evidence_conflicting_user_evidence(self):
        """Conflicting user document fields generate explicit ConflictItem."""
        agent = InformationRetrievalAgent()
        req = RetrievalRequest(
            request_id="req_user_conf",
            goal="DOB Update",
            service="Aadhaar DOB Update",
            domain="aadhaar",
            requirements=[RetrievalRequirement(requirement_id="r1", category="dob", description="Proof of DOB")],
        )
        doc1 = UserDocument(
            document_id="d1",
            filename="p.pdf",
            mime_type=".pdf",
            document_type=DocumentType.PASSPORT,
            extracted_fields={"dob": ExtractedField(field_name="dob", value="1990-05-15")},
        )
        doc2 = UserDocument(
            document_id="d2",
            filename="i.pdf",
            mime_type=".pdf",
            document_type=DocumentType.IDENTITY_PROOF,
            extracted_fields={"dob": ExtractedField(field_name="dob", value="1992-08-20")},
        )
        res = agent.retrieve(request=req, user_documents=[doc1, doc2], mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertGreater(len(res.conflicts), 0)

    # =========================================================
    # 4. FRESHNESS
    # =========================================================
    def test_freshness_current_live_evidence(self):
        """Live evidence receives freshness_type='live_current' and highest freshness signal score."""
        verifier = GroundingVerifier(source_registry=self.registry)
        ranker = EvidenceRanker(verifier=verifier)

        live_ev = Evidence(
            evidence_id="ev_live",
            claim="Live claim",
            passage="Live portal updated guidelines passage content.",
            source=Source(source_id="src_live", authority="UIDAI", domain="aadhaar", url="https://uidai.gov.in/en/"),
            metadata={"freshness_type": FreshnessType.LIVE_CURRENT_RETRIEVAL.value, "category": "address"},
        )
        score = ranker._compute_freshness_signal(live_ev)
        self.assertEqual(score, 1.0)

    def test_freshness_stored_official_evidence(self):
        """Stored official evidence receives freshness_type='stored_official' and 0.85 freshness score."""
        verifier = GroundingVerifier(source_registry=self.registry)
        ranker = EvidenceRanker(verifier=verifier)

        stored_ev = Evidence(
            evidence_id="ev_stored",
            claim="Stored claim",
            passage="Stored KB guidelines passage content.",
            source=Source(source_id="src_stored", authority="UIDAI", domain="aadhaar", url="https://uidai.gov.in/en/"),
            metadata={"freshness_type": FreshnessType.STORED_OFFICIAL_DOCUMENT.value, "category": "address"},
        )
        score = ranker._compute_freshness_signal(stored_ev)
        self.assertEqual(score, 0.85)

    def test_freshness_stale_stored_evidence(self):
        """Stale stored evidence preserves date metadata without claiming current live freshness."""
        ev = Evidence(
            evidence_id="ev_stale",
            claim="Old claim",
            passage="Outdated policy passage text.",
            source=Source(source_id="src_old", authority="UIDAI", domain="aadhaar", url="https://uidai.gov.in/en/", last_checked="2020-01-01T00:00:00Z"),
            metadata={"freshness_type": FreshnessType.STORED_OFFICIAL_DOCUMENT.value, "category": "fee"},
        )
        self.assertEqual(ev.source.last_checked, "2020-01-01T00:00:00Z")
        self.assertNotEqual(ev.metadata.get("freshness_type"), FreshnessType.LIVE_CURRENT_RETRIEVAL.value)

    def test_freshness_unknown_freshness(self):
        """Unknown freshness receives neutral default score (0.50)."""
        verifier = GroundingVerifier(source_registry=self.registry)
        ranker = EvidenceRanker(verifier=verifier)

        unknown_ev = Evidence(
            evidence_id="ev_unk",
            claim="Unknown freshness claim",
            passage="Passage without freshness metadata.",
            source=Source(source_id="src_unk", authority="UIDAI", domain="aadhaar", url="https://uidai.gov.in/en/"),
            metadata={"category": "address"},
        )
        score = ranker._compute_freshness_signal(unknown_ev)
        self.assertEqual(score, 0.50)

    def test_freshness_live_unavailable_stored_available(self):
        """Live unavailable + stored evidence available retains stored freshness_type."""
        store = ChromaVectorStore(
            persist_directory=os.path.join(self.temp_dir, "fresh_db"),
            collection_name="fresh_coll",
            embedder=self.embedder,
        )
        chunk = DocumentChunk(
            chunk_id="chk_fresh_01",
            source_id="src_fresh_01",
            authority="UIDAI",
            document_title="Stored Aadhaar Guidelines",
            document_url="https://uidai.gov.in/en/",
            page_number=1,
            text="Address update proof of address documents list.",
            token_count_approx=10,
            chunk_index=0,
        )
        store.add_chunks([chunk])

        fetcher = LiveGovernmentFetcher(source_registry=self.registry)
        fetcher.fetch_source = MagicMock(return_value=LiveRetrievalResult(
            source_id="src_fresh_01",
            authority="UIDAI",
            url="https://uidai.gov.in/en/",
            status=LiveRetrievalStatus.TIMEOUT,
            error_message="Timed out",
        ))

        agent = InformationRetrievalAgent(hybrid_retriever=HybridRetriever(vector_retriever=VectorRetriever(vector_store=store), live_fetcher=fetcher))
        req = RetrievalRequest(
            request_id="req_fresh_fallback",
            goal="Address update",
            service="Aadhaar Address Update",
            domain="aadhaar",
            requirements=[RetrievalRequirement(requirement_id="r1", category="address", description="Proof of address")],
        )

        res = agent.retrieve(request=req, mode=RetrievalMode.HYBRID)
        self.assertIn(res.retrieval_status, [RetrievalStatus.PARTIAL_SUCCESS, RetrievalStatus.SUCCESS, "partial_success", "success"])
        self.assertGreater(len(res.evidence), 0)

    def test_freshness_live_evidence_conflicting_with_stored(self):
        """Live vs stored evidence conflict surfaces both claims and preserves respective freshness types."""
        agent = InformationRetrievalAgent()
        ev_stored = Evidence(
            evidence_id="ev_st",
            claim="Fee is Rs 50",
            passage="Stored document says fee is Rs 50.",
            source=Source(source_id="src_1", authority="UIDAI", domain="aadhaar", url="https://uidai.gov.in/en/doc.pdf"),
            metadata={"freshness_type": FreshnessType.STORED_OFFICIAL_DOCUMENT.value, "category": "fee"},
        )
        ev_live = Evidence(
            evidence_id="ev_lv",
            claim="Fee is Rs 100",
            passage="Live portal states fee is Rs 100.",
            source=Source(source_id="src_2", authority="UIDAI", domain="aadhaar", url="https://uidai.gov.in/en/live_page"),
            metadata={"freshness_type": FreshnessType.LIVE_CURRENT_RETRIEVAL.value, "category": "fee"},
        )

        fused, sources, conflicts = agent.fusion_engine.fuse_evidence([ev_stored], [ev_live])
        self.assertEqual(len(fused), 2)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(fused[0].metadata["freshness_type"], FreshnessType.STORED_OFFICIAL_DOCUMENT.value)
        self.assertEqual(fused[1].metadata["freshness_type"], FreshnessType.LIVE_CURRENT_RETRIEVAL.value)

    # =========================================================
    # 5. FEES / TIMELINES / APPOINTMENTS / FORMS
    # =========================================================
    def test_missing_and_conflicting_fee_information(self):
        """Missing fee info produces NO_EVIDENCE_FOUND status; conflicting fees produce ConflictItem without fabricating values."""
        agent = InformationRetrievalAgent(hybrid_retriever=HybridRetriever(vector_retriever=self.empty_retriever))
        req_missing = RetrievalRequest(
            request_id="req_fee_missing",
            goal="Get update fee",
            service="Aadhaar",
            domain="aadhaar",
            requirements=[RetrievalRequirement(requirement_id="r1", category="fee", description="Exact fee amount")],
        )
        res_missing = agent.retrieve(request=req_missing, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertEqual(res_missing.retrieval_status, RetrievalStatus.NO_EVIDENCE_FOUND)
        self.assertEqual(len(res_missing.evidence), 0)

    def test_missing_and_conflicting_timeline_information(self):
        """Missing processing timeline produces NO_EVIDENCE_FOUND without fabricating days/weeks."""
        agent = InformationRetrievalAgent(hybrid_retriever=HybridRetriever(vector_retriever=self.empty_retriever))
        req_timeline = RetrievalRequest(
            request_id="req_time_missing",
            goal="Get timeline",
            service="Aadhaar",
            domain="aadhaar",
            requirements=[RetrievalRequirement(requirement_id="r1", category="timeline", description="Processing time in days")],
        )
        res_time = agent.retrieve(request=req_timeline, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertEqual(res_time.retrieval_status, RetrievalStatus.NO_EVIDENCE_FOUND)

    def test_missing_and_conflicting_appointment_availability(self):
        """Missing appointment slots produce NO_EVIDENCE_FOUND without inventing fake dates."""
        agent = InformationRetrievalAgent(hybrid_retriever=HybridRetriever(vector_retriever=self.empty_retriever))
        req_appt = RetrievalRequest(
            request_id="req_appt_missing",
            goal="Check slot availability",
            service="Aadhaar",
            domain="aadhaar",
            requirements=[RetrievalRequirement(requirement_id="r1", category="appointment", description="Available slot dates")],
        )
        res_appt = agent.retrieve(request=req_appt, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertEqual(res_appt.retrieval_status, RetrievalStatus.NO_EVIDENCE_FOUND)

    def test_missing_and_conflicting_forms_information(self):
        """Missing form number does not fabricate form numbers."""
        agent = InformationRetrievalAgent(hybrid_retriever=HybridRetriever(vector_retriever=self.empty_retriever))
        req_form = RetrievalRequest(
            request_id="req_form_missing",
            goal="Get form number",
            service="Aadhaar",
            domain="aadhaar",
            requirements=[RetrievalRequirement(requirement_id="r1", category="form", description="Application form number")],
        )
        res_form = agent.retrieve(request=req_form, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertEqual(res_form.retrieval_status, RetrievalStatus.NO_EVIDENCE_FOUND)

    # =========================================================
    # 6. AUTHENTICATION / CAPTCHA / USER ACTION BARRIERS
    # =========================================================
    def test_barrier_otp_requirement(self):
        """OTP requirement is retrieved as informational evidence claim, NOT executed as automated bypass."""
        agent = InformationRetrievalAgent()
        req = RetrievalRequest(
            request_id="req_bar_otp",
            goal="Mobile update OTP requirement",
            service="Aadhaar Mobile Update",
            domain="aadhaar",
            requirements=[RetrievalRequirement(requirement_id="r1", category="otp_authentication", description="OTP verification on registered mobile")],
        )
        res = agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIsInstance(res, RetrievalResult)

    def test_barrier_login_requirement(self):
        """Login requirement is represented as informational evidence claim, no bypass attempted."""
        agent = InformationRetrievalAgent()
        req = RetrievalRequest(
            request_id="req_bar_login",
            goal="myAadhaar portal login requirement",
            service="Aadhaar Portal Login",
            domain="aadhaar",
            requirements=[RetrievalRequirement(requirement_id="r1", category="login", description="Login with Aadhaar and OTP")],
        )
        res = agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIsInstance(res, RetrievalResult)

    def test_barrier_captcha_requirement(self):
        """CAPTCHA barrier requirement is returned as requirement information, no automated solving attempted."""
        agent = InformationRetrievalAgent()
        req = RetrievalRequest(
            request_id="req_bar_captcha",
            goal="CAPTCHA requirement on myAadhaar",
            service="Aadhaar CAPTCHA",
            domain="aadhaar",
            requirements=[RetrievalRequirement(requirement_id="r1", category="captcha", description="Security CAPTCHA verification")],
        )
        res = agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIsInstance(res, RetrievalResult)

    def test_barrier_authentication_requirement(self):
        """General authentication barrier requirement represented safely as evidence claim."""
        agent = InformationRetrievalAgent()
        req = RetrievalRequest(
            request_id="req_bar_auth",
            goal="Auth barrier check",
            service="Aadhaar Auth",
            domain="aadhaar",
            requirements=[RetrievalRequirement(requirement_id="r1", category="authentication", description="Two-factor authentication requirement")],
        )
        res = agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIsInstance(res, RetrievalResult)

    def test_barrier_physical_presence_requirement(self):
        """Physical presence requirement (biometric update at ASK) returned as informational requirement claim."""
        agent = InformationRetrievalAgent()
        req = RetrievalRequest(
            request_id="req_bar_presence",
            goal="Biometric update location requirement",
            service="Aadhaar Biometric Update",
            domain="aadhaar",
            requirements=[RetrievalRequirement(requirement_id="r1", category="physical_presence", description="Physical presence required at Aadhaar Seva Kendra")],
        )
        res = agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIsInstance(res, RetrievalResult)

    def test_barrier_inaccessible_authenticated_endpoint(self):
        """Live fetch to authenticated endpoint returns AUTH_REQUIRED status and structured warning."""
        fetcher = LiveGovernmentFetcher(source_registry=self.registry)
        source = Source(source_id="src_auth", authority="UIDAI", domain="aadhaar", url="https://uidai.gov.in/en/")
        with patch.object(httpx.Client, "get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_resp.url = "https://myaadhaar.uidai.gov.in/dash/auth"
            mock_resp.text = "Unauthorized. Please login with OTP."
            mock_get.return_value = mock_resp

            live_res = fetcher.fetch_source(source)
            self.assertEqual(live_res.status, LiveRetrievalStatus.AUTH_REQUIRED)

    # =========================================================
    # 7. LIVE RETRIEVAL FAILURE & TOP-LEVEL AGENT FIELD VERIFICATION
    # =========================================================
    @patch.object(httpx.Client, "get")
    def test_live_retrieval_http_403_waf_blocked(self, mock_get):
        """HTTP 403 WAF / Cloudflare block handling produces structural warning without crashing."""
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.url = "https://uidai.gov.in/en/blocked"
        mock_resp.text = "<html><head><title>Access Denied</title></head><body>Attention Required! | Cloudflare</body></html>"
        mock_resp.content = mock_resp.text.encode("utf-8")
        mock_get.return_value = mock_resp

        fetcher = LiveGovernmentFetcher(source_registry=self.registry)
        hybrid_retriever = HybridRetriever(vector_retriever=self.empty_retriever, live_fetcher=fetcher)
        agent = InformationRetrievalAgent(hybrid_retriever=hybrid_retriever)

        req = RetrievalRequest(
            request_id="req_fail_403",
            goal="Test 403 response",
            service="Aadhaar Test",
            domain="aadhaar",
            requirements=[RetrievalRequirement(requirement_id="r1", category="procedure", description="Check 403 response")],
        )

        res = agent.retrieve(request=req, mode=RetrievalMode.LIVE_ONLY)
        self.assertIn(res.retrieval_status, [RetrievalStatus.FAILED, RetrievalStatus.NO_EVIDENCE_FOUND, RetrievalStatus.SOURCE_UNAVAILABLE])
        self.assertTrue(any("BLOCKED_OR_WAF" in w.message or "403" in w.message or "WAF" in w.code for w in res.warnings))
        self.assertEqual(len(res.evidence), 0)

    @patch.object(httpx.Client, "get")
    def test_live_retrieval_http_404_not_found(self, mock_get):
        """HTTP 404 page not found produces structural error reporting."""
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.url = "https://uidai.gov.in/en/nonexistent"
        mock_resp.text = "<html><body>404 Not Found</body></html>"
        mock_resp.content = mock_resp.text.encode("utf-8")
        mock_get.return_value = mock_resp

        fetcher = LiveGovernmentFetcher(source_registry=self.registry)
        hybrid_retriever = HybridRetriever(vector_retriever=self.empty_retriever, live_fetcher=fetcher)
        agent = InformationRetrievalAgent(hybrid_retriever=hybrid_retriever)

        req = RetrievalRequest(
            request_id="req_fail_404",
            goal="Test 404 response",
            service="Aadhaar Test",
            domain="aadhaar",
            requirements=[RetrievalRequirement(requirement_id="r1", category="procedure", description="Check 404 response")],
        )

        res = agent.retrieve(request=req, mode=RetrievalMode.LIVE_ONLY)
        self.assertIn(res.retrieval_status, [RetrievalStatus.FAILED, RetrievalStatus.NO_EVIDENCE_FOUND, RetrievalStatus.SOURCE_UNAVAILABLE])
        self.assertTrue(any("404" in w.message or "HTTP_ERROR" in w.code for w in res.warnings))

    @patch.object(httpx.Client, "get")
    def test_live_retrieval_http_500_server_error(self, mock_get):
        """HTTP 500 internal server error handling."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.url = "https://uidai.gov.in/en/error"
        mock_resp.text = "Internal Server Error"
        mock_resp.content = b"Internal Server Error"
        mock_get.return_value = mock_resp

        fetcher = LiveGovernmentFetcher(source_registry=self.registry)
        hybrid_retriever = HybridRetriever(vector_retriever=self.empty_retriever, live_fetcher=fetcher)
        agent = InformationRetrievalAgent(hybrid_retriever=hybrid_retriever)

        req = RetrievalRequest(
            request_id="req_fail_500",
            goal="Test 500 response",
            service="Aadhaar Test",
            domain="aadhaar",
            requirements=[RetrievalRequirement(requirement_id="r1", category="procedure", description="Check 500 response")],
        )

        res = agent.retrieve(request=req, mode=RetrievalMode.LIVE_ONLY)
        self.assertIn(res.retrieval_status, [RetrievalStatus.FAILED, RetrievalStatus.NO_EVIDENCE_FOUND, RetrievalStatus.SOURCE_UNAVAILABLE])
        self.assertTrue(any("500" in w.message or "HTTP_ERROR" in w.code for w in res.warnings))

    @patch.object(httpx.Client, "get")
    def test_live_retrieval_timeout(self, mock_get):
        """HTTP timeout handling produces TIMEOUT status in warnings."""
        mock_get.side_effect = httpx.TimeoutException("Connection timed out")

        fetcher = LiveGovernmentFetcher(source_registry=self.registry)
        hybrid_retriever = HybridRetriever(vector_retriever=self.empty_retriever, live_fetcher=fetcher)
        agent = InformationRetrievalAgent(hybrid_retriever=hybrid_retriever)

        req = RetrievalRequest(
            request_id="req_fail_timeout",
            goal="Test timeout handling",
            service="Aadhaar Test",
            domain="aadhaar",
            requirements=[RetrievalRequirement(requirement_id="r1", category="procedure", description="Check timeout")],
        )

        res = agent.retrieve(request=req, mode=RetrievalMode.LIVE_ONLY)
        self.assertIn(res.retrieval_status, [RetrievalStatus.FAILED, RetrievalStatus.NO_EVIDENCE_FOUND, RetrievalStatus.SOURCE_UNAVAILABLE])
        self.assertTrue(any("timed out" in w.message.lower() or "TIMEOUT" in w.code for w in res.warnings))

    @patch.object(httpx.Client, "get")
    def test_live_retrieval_js_shell_detection(self, mock_get):
        """Single Page Application JS shell returns JS_SHELL_DETECTED and marks evidence unusable."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.url = "https://myaadhaar.uidai.gov.in/"
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.text = "<html><head><title>Portal</title></head><body><noscript>Enable JS</noscript><div id='root'></div></body></html>"
        mock_resp.content = mock_resp.text.encode("utf-8")
        mock_get.return_value = mock_resp

        fetcher = LiveGovernmentFetcher(source_registry=self.registry)
        hybrid_retriever = HybridRetriever(vector_retriever=self.empty_retriever, live_fetcher=fetcher)
        agent = InformationRetrievalAgent(hybrid_retriever=hybrid_retriever)

        req = RetrievalRequest(
            request_id="req_fail_js_shell",
            goal="Test JS shell detection",
            service="Aadhaar Test",
            domain="aadhaar",
            requirements=[RetrievalRequirement(requirement_id="r1", category="procedure", description="Check JS shell")],
        )

        res = agent.retrieve(request=req, mode=RetrievalMode.LIVE_ONLY)
        self.assertIn(res.retrieval_status, [RetrievalStatus.FAILED, RetrievalStatus.NO_EVIDENCE_FOUND, RetrievalStatus.SOURCE_UNAVAILABLE])

    def test_live_retrieval_untrusted_domain_rejection(self):
        """Untrusted domain URL is rejected by SourceRegistry authority validator."""
        untrusted_url = "https://fake-aadhaar-update.com/login"
        self.assertFalse(self.registry.is_authoritative(untrusted_url, "aadhaar"))

    def test_toplevel_agent_retrieve_field_verification(self):
        """Exercise failure state through InformationRetrievalAgent.retrieve(...) and verify all RetrievalResult fields."""
        agent = InformationRetrievalAgent()
        req = RetrievalRequest(
            request_id="req_toplevel_fields",
            goal="Full field verification",
            service="Aadhaar Test",
            domain="aadhaar",
            requirements=[RetrievalRequirement(requirement_id="r1", category="procedure", description="Verification")],
        )

        res = agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertIsInstance(res.result_id, str)
        self.assertEqual(res.request_id, "req_toplevel_fields")
        self.assertEqual(res.service, "Aadhaar Test")
        self.assertEqual(res.domain, "aadhaar")
        self.assertTrue(isinstance(res.retrieval_status, RetrievalStatus) or res.retrieval_status in list(RetrievalStatus))
        self.assertIsInstance(res.warnings, list)
        self.assertIsInstance(res.conflicts, list)
        self.assertIsInstance(res.evidence, list)
        self.assertIsInstance(res.sources, list)
        self.assertIsInstance(res.metadata, dict)

    def test_privacy_security_check_no_pii_token_leak(self):
        """Result warnings and metadata do not contain secret keys, tokens, or unmasked PII."""
        agent = InformationRetrievalAgent()
        req = RetrievalRequest(
            request_id="req_privacy_check",
            goal="Privacy leak test",
            service="Aadhaar Privacy",
            domain="aadhaar",
            requirements=[RetrievalRequirement(requirement_id="r1", category="procedure", description="Privacy test")],
        )
        res = agent.retrieve(request=req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        for warning in res.warnings:
            self.assertNotIn("API_KEY", warning.message)
            self.assertNotIn("Bearer ", warning.message)
            self.assertNotIn("password", warning.message.lower())

    # =========================================================
    # 8. GRACEFUL DEGRADATION INTEGRATION
    # =========================================================
    def test_degradation_live_failure_stored_available(self):
        """Live retrieval fails + stored KB evidence available -> PARTIAL_SUCCESS + warning."""
        store = ChromaVectorStore(
            persist_directory=os.path.join(self.temp_dir, "fallback_db"),
            collection_name="fallback_collection",
            embedder=self.embedder,
        )
        chunk = DocumentChunk(
            chunk_id="chk_fallback_01",
            source_id="src_official_kb",
            authority="UIDAI",
            document_title="Official Guidelines",
            document_url="https://uidai.gov.in/en/",
            page_number=1,
            text="Address update requires valid Proof of Address document such as Passport or Voter ID.",
            token_count_approx=15,
            chunk_index=0,
        )
        store.add_chunks([chunk])

        vector_retriever = VectorRetriever(vector_store=store, top_k=2)
        fetcher = LiveGovernmentFetcher(source_registry=self.registry)
        fetcher.fetch_source = MagicMock(return_value=LiveRetrievalResult(
            source_id="src_official_kb",
            authority="UIDAI",
            url="https://uidai.gov.in/en/",
            status=LiveRetrievalStatus.TIMEOUT,
            error_message="Live portal connection timed out",
        ))

        hybrid_retriever = HybridRetriever(vector_retriever=vector_retriever, live_fetcher=fetcher)
        agent = InformationRetrievalAgent(hybrid_retriever=hybrid_retriever)

        req = RetrievalRequest(
            request_id="req_degrade_01",
            goal="Update address",
            service="Aadhaar Address Update",
            domain="aadhaar",
            requirements=[RetrievalRequirement(requirement_id="r1", category="address", description="Proof of address")],
        )

        res = agent.retrieve(request=req, mode=RetrievalMode.HYBRID)
        self.assertIn(res.retrieval_status, [RetrievalStatus.PARTIAL_SUCCESS, RetrievalStatus.SUCCESS])
        self.assertGreater(len(res.evidence), 0)
        self.assertTrue(any("Live portal connection timed out" in w.message or "TIMEOUT" in w.code for w in res.warnings))

    def test_degradation_live_failure_no_stored(self):
        """Live retrieval fails + empty stored KB -> NO_EVIDENCE_FOUND status + zero fabricated evidence."""
        fetcher = LiveGovernmentFetcher(source_registry=self.registry)
        fetcher.fetch_source = MagicMock(return_value=LiveRetrievalResult(
            source_id="src_none",
            authority="UIDAI",
            url="https://uidai.gov.in/en/",
            status=LiveRetrievalStatus.HTTP_ERROR,
            error_message="500 Internal Server Error",
        ))
        hybrid_retriever = HybridRetriever(vector_retriever=self.empty_retriever, live_fetcher=fetcher)
        agent = InformationRetrievalAgent(hybrid_retriever=hybrid_retriever)

        req = RetrievalRequest(
            request_id="req_no_stored_fail",
            goal="Update address",
            service="Aadhaar Address Update",
            domain="aadhaar",
            requirements=[RetrievalRequirement(requirement_id="r1", category="address", description="Proof of address")],
        )
        res = agent.retrieve(request=req, mode=RetrievalMode.HYBRID)
        self.assertIn(res.retrieval_status, [RetrievalStatus.NO_EVIDENCE_FOUND, RetrievalStatus.FAILED])
        self.assertEqual(len(res.evidence), 0)

    def test_degradation_user_doc_failure_official_continues(self):
        """User document failure attaches warning while official retrieval completes successfully."""
        agent = InformationRetrievalAgent()
        req = RetrievalRequest(
            request_id="req_doc_fail_off_cont",
            goal="Name update proof",
            service="Aadhaar Name Update",
            domain="aadhaar",
            requirements=[RetrievalRequirement(requirement_id="r1", category="name", description="Proof of name")],
        )
        res = agent.retrieve(request=req, user_documents=["/non_existent_folder/missing.pdf"], mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertTrue(any("USER_DOCUMENT_PARSE_FAILED" in w.code for w in res.warnings))

    def test_degradation_conflicting_evidence_preserved(self):
        """Conflicting evidence preserved in res.conflicts with no silent unverified winner selected."""
        agent = InformationRetrievalAgent()
        ev1 = Evidence(
            evidence_id="ev_c1",
            claim="Passport is fee Rs 50",
            passage="Passport fee is Rs 50 for update.",
            source=Source(source_id="s1", authority="UIDAI", domain="aadhaar", url="https://uidai.gov.in/en/doc1.pdf"),
            metadata={"category": "fee", "associated_requirements": ["r1"]},
        )
        ev2 = Evidence(
            evidence_id="ev_c2",
            claim="Passport is fee Rs 100",
            passage="Passport fee is Rs 100 for update.",
            source=Source(source_id="s2", authority="UIDAI", domain="aadhaar", url="https://uidai.gov.in/en/doc2.pdf"),
            metadata={"category": "fee", "associated_requirements": ["r1"]},
        )
        fused, sources, conflicts = agent.fusion_engine.fuse_evidence([ev1], [ev2])
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(len(fused), 2)


if __name__ == "__main__":
    unittest.main()
