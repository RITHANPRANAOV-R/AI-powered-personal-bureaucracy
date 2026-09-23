"""
Unit tests and real integration tests for HybridRetriever, EvidenceFusionEngine, and ConflictDetector.
"""
import unittest
import os
import shutil
import tempfile
from unittest.mock import MagicMock

from agents.knowledge_based.information_retrieval.schemas import (
    Source,
    SourceType,
    Evidence,
    RetrievalRequest,
    RetrievalRequirement,
    RetrievalResult,
    RetrievalStatus,
)
from agents.knowledge_based.information_retrieval.sources.source_registry import SourceRegistry
from agents.knowledge_based.information_retrieval.ingestion import (
    DocumentLoader,
    DocumentParser,
    DocumentCleaner,
    DocumentChunker,
)
from agents.knowledge_based.information_retrieval.embeddings import LocalEmbeddingService
from agents.knowledge_based.information_retrieval.retrieval import (
    ChromaVectorStore,
    VectorRetriever,
    EvidenceFusionEngine,
    ConflictDetector,
    FreshnessType,
    HybridRetriever,
    RetrievalMode,
)


class TestEvidenceFusionAndConflictDetection(unittest.TestCase):
    def setUp(self):
        self.detector = ConflictDetector()
        self.fusion = EvidenceFusionEngine(conflict_detector=self.detector)
        self.source1 = Source(
            source_id="src_pdf",
            authority="UIDAI",
            domain="aadhaar",
            url="https://uidai.gov.in/doc1.pdf",
            document_title="UIDAI Document 1",
        )
        self.source2 = Source(
            source_id="src_web",
            authority="UIDAI",
            domain="aadhaar",
            url="https://uidai.gov.in/page",
            document_title="UIDAI Web Portal",
        )

    def test_freshness_metadata_annotation(self):
        ev_know = Evidence(
            evidence_id="k1",
            claim="PDF Evidence",
            passage="Aadhaar update fee is Rs 50.",
            source=self.source1,
            page_number=2,
        )
        ev_live = Evidence(
            evidence_id="l1",
            claim="Web Evidence",
            passage="Aadhaar update fee is Rs 50.",
            source=self.source2,
        )

        fused, sources, conflicts = self.fusion.fuse_evidence([ev_know], [ev_live])
        self.assertEqual(len(fused), 2)
        self.assertEqual(len(sources), 2)
        self.assertEqual(len(conflicts), 0)

        # Check freshness annotations
        self.assertEqual(fused[0].metadata["freshness_type"], FreshnessType.STORED_OFFICIAL_DOCUMENT.value)
        self.assertEqual(fused[1].metadata["freshness_type"], FreshnessType.LIVE_CURRENT_RETRIEVAL.value)

    def test_conflict_detection_fee_discrepancy(self):
        ev1 = Evidence(
            evidence_id="e1",
            claim="Claim 1",
            passage="The fee for Aadhaar biometric update is Rs 100 at enrolment centers.",
            source=self.source1,
            metadata={"category": "fees"},
        )
        ev2 = Evidence(
            evidence_id="e2",
            claim="Claim 2",
            passage="The fee for Aadhaar demographic update is Rs 50 online.",
            source=self.source2,
            metadata={"category": "fees"},
        )

        fused, sources, conflicts = self.fusion.fuse_evidence([ev1], [ev2])
        self.assertEqual(len(conflicts), 1)
        conflict = conflicts[0]
        self.assertIn("Fee amount discrepancy", conflict.topic)
        self.assertEqual(len(conflict.sources), 2)


class TestHybridRetrieverMocked(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.embedder = LocalEmbeddingService()
        self.store = ChromaVectorStore(
            persist_directory=self.temp_dir,
            collection_name="test_hybrid_collection",
            embedder=self.embedder,
        )
        self.vector_retriever = VectorRetriever(vector_store=self.store, top_k=2)
        self.hybrid = HybridRetriever(vector_retriever=self.vector_retriever)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_knowledge_only_mode(self):
        req = RetrievalRequest(
            request_id="req_k_only",
            goal="Test knowledge mode",
            service="Aadhaar Service",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="fees", description="Fee query")
            ],
        )
        res = self.hybrid.retrieve(req, mode=RetrievalMode.KNOWLEDGE_ONLY)
        self.assertEqual(res.metadata["retrieval_mode"], RetrievalMode.KNOWLEDGE_ONLY.value)

    def test_untrusted_source_rejection(self):
        # Mock source registry rejecting URL
        mock_registry = MagicMock()
        mock_registry.list_sources.return_value = [
            Source(source_id="src_fake", authority="BLOG", domain="aadhaar", url="https://fakeblog.com")
        ]
        mock_registry.is_authoritative.return_value = False

        hybrid_untrusted = HybridRetriever(
            vector_retriever=self.vector_retriever,
            source_registry=mock_registry,
        )
        req = RetrievalRequest(
            request_id="req_untrusted",
            goal="Test untrusted domain rejection",
            service="Aadhaar Service",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="fees", description="Fee query")
            ],
        )

        res = hybrid_untrusted.retrieve(req, mode=RetrievalMode.LIVE_ONLY)
        self.assertEqual(len(res.evidence), 0)
        self.assertTrue(any("rejected by authority filter" in w.message for w in res.warnings))


class TestRealUIDAIHybridRetrievalIntegration(unittest.TestCase):
    """
    REAL integration test performing true hybrid retrieval:
    Persistent ChromaDB Official UIDAI PDF Knowledge + Real Live Official UIDAI Web Retrieval.
    """
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.loader = DocumentLoader()
        self.parser = DocumentParser()
        self.chunker = DocumentChunker()
        self.embedder = LocalEmbeddingService()
        self.store = ChromaVectorStore(
            persist_directory=self.temp_dir,
            collection_name="uidai_hybrid_phase8_test",
            embedder=self.embedder,
        )
        self.vector_retriever = VectorRetriever(vector_store=self.store, top_k=2)
        self.hybrid = HybridRetriever(vector_retriever=self.vector_retriever, default_mode=RetrievalMode.HYBRID)

        self.official_pdf_url = "https://backend.uidai.gov.in/get/files/media/document/2026-05/Citizen_Charter_Jan24.pdf"
        self.source = Source(
            source_id="src_uidai_citizen_charter_pdf",
            authority="UIDAI",
            domain="aadhaar",
            url=self.official_pdf_url,
            document_title="Citizen's Charter for UIDAI (Jan 2024)",
            source_type=SourceType.OFFICIAL_PDF,
        )

        # Ingest real official UIDAI Citizen Charter into ChromaDB knowledge base
        pdf_bytes, _ = self.loader.load_from_url(self.official_pdf_url)
        parsed_doc = self.parser.parse_pdf(pdf_bytes, fallback_title=self.source.document_title)
        chunks = self.chunker.chunk_document(parsed_doc, self.source, chunk_size=600, chunk_overlap=100)
        self.store.add_chunks(chunks)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_real_hybrid_retrieval_execution(self):
        req = RetrievalRequest(
            request_id="req_hybrid_real_001",
            goal="Verify resident rights and official UIDAI portal services",
            service="UIDAI Resident Services",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(
                    requirement_id="req_h1",
                    category="eligibility",
                    description="Resident rights and guidelines in UIDAI charter",
                )
            ],
        )

        result = self.hybrid.retrieve(req, mode=RetrievalMode.HYBRID, top_k=2)

        # 1. Verification of status and evidence presence
        self.assertIn(result.retrieval_status, [RetrievalStatus.SUCCESS, RetrievalStatus.PARTIAL_SUCCESS])
        self.assertGreater(len(result.evidence), 0)

        # 2. Verify evidence contains STORED_OFFICIAL_DOCUMENT from ChromaDB
        has_stored = any(
            ev.metadata.get("freshness_type") == FreshnessType.STORED_OFFICIAL_DOCUMENT.value
            for ev in result.evidence
        )
        self.assertTrue(has_stored, "Hybrid retrieval result must contain stored official PDF evidence from ChromaDB")

        # 3. Check metadata and mode
        self.assertEqual(result.metadata["retrieval_mode"], RetrievalMode.HYBRID.value)


if __name__ == "__main__":
    unittest.main()
