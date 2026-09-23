"""
Unit tests and real integration tests for GroundingVerifier and EvidenceRanker.
"""
import unittest
import os
import shutil
import tempfile

from agents.knowledge_based.information_retrieval.schemas import (
    Source,
    SourceType,
    Evidence,
    GroundingStatus,
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
    FreshnessType,
    GroundingVerifier,
    EvidenceRanker,
    HybridRetriever,
    RetrievalMode,
)


class TestGroundingVerifierAndRankerUnit(unittest.TestCase):
    def setUp(self):
        self.registry = SourceRegistry(include_defaults=True)
        self.verifier = GroundingVerifier(source_registry=self.registry)
        self.ranker = EvidenceRanker(verifier=self.verifier)

        self.valid_source = Source(
            source_id="src_uidai_portal_en",
            authority="UIDAI",
            domain="aadhaar",
            url="https://uidai.gov.in/en/",
            document_title="UIDAI Portal",
            trust_level=1.0,
        )
        self.untrusted_source = Source(
            source_id="src_untrusted_blog",
            authority="BLOG",
            domain="aadhaar",
            url="https://fakeblog.com/aadhaar",
            document_title="Fake Blog",
            trust_level=0.1,
        )

    def test_grounding_verification_valid_vs_invalid(self):
        valid_ev = Evidence(
            evidence_id="ev_valid_1",
            claim="Resident rights",
            passage="Residents have the right to update their demographic details in Aadhaar.",
            source=self.valid_source,
            metadata={"associated_requirements": ["req_1"], "category": "rights"},
        )
        invalid_short_ev = Evidence(
            evidence_id="ev_short",
            claim="Short passage",
            passage="Too short",
            source=self.valid_source,
            metadata={"associated_requirements": ["req_1"]},
        )
        invalid_untrusted_ev = Evidence(
            evidence_id="ev_untrusted",
            claim="Untrusted source",
            passage="A long passage about Aadhaar updates from an untrusted source blog post.",
            source=self.untrusted_source,
            metadata={"associated_requirements": ["req_1"]},
        )

        self.assertEqual(self.verifier.verify_grounding(valid_ev), GroundingStatus.VERIFIED_GROUNDED)
        self.assertEqual(self.verifier.verify_grounding(invalid_short_ev), GroundingStatus.INVALID)
        self.assertEqual(self.verifier.verify_grounding(invalid_untrusted_ev), GroundingStatus.INVALID)

    def test_ranking_signal_breakdown_and_sorting(self):
        ev1 = Evidence(
            evidence_id="ev_1",
            claim="Stored PDF Chunk",
            passage="Aadhaar demographic update requires valid proof of identity and proof of address documents.",
            source=self.valid_source,
            relevance_score=0.8,
            metadata={
                "freshness_type": FreshnessType.STORED_OFFICIAL_DOCUMENT.value,
                "category": "required_documents",
                "associated_requirements": ["r1"],
            },
        )
        ev2 = Evidence(
            evidence_id="ev_2",
            claim="Live Web Content",
            passage="Official UIDAI portal allows residents to order PVC card and check enrolment status online.",
            source=self.valid_source,
            relevance_score=0.9,
            metadata={
                "freshness_type": FreshnessType.LIVE_CURRENT_RETRIEVAL.value,
                "category": "order_pvc",
                "associated_requirements": ["r2"],
            },
        )

        ranked = self.ranker.rank_and_verify([ev1, ev2])

        self.assertEqual(len(ranked), 2)
        # Check grounding status & inspectable signals
        for item in ranked:
            self.assertEqual(item.grounding_status, GroundingStatus.VERIFIED_GROUNDED)
            self.assertGreater(item.ranking_score, 0.0)
            self.assertIn("ranking_signals", item.metadata)

        # Check sorting order: highest ranking_score first
        self.assertGreaterEqual(ranked[0].ranking_score, ranked[1].ranking_score)


class TestRealUIDAIRankingIntegration(unittest.TestCase):
    """
    REAL end-to-end integration test verifying ranking and grounding verification over actual UIDAI Citizen Charter PDF chunks.
    """
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.loader = DocumentLoader()
        self.parser = DocumentParser()
        self.chunker = DocumentChunker()
        self.embedder = LocalEmbeddingService()
        self.store = ChromaVectorStore(
            persist_directory=self.temp_dir,
            collection_name="uidai_ranking_phase9_test",
            embedder=self.embedder,
        )
        self.vector_retriever = VectorRetriever(vector_store=self.store, top_k=3)
        self.hybrid = HybridRetriever(vector_retriever=self.vector_retriever, default_mode=RetrievalMode.KNOWLEDGE_ONLY)

        self.official_pdf_url = "https://backend.uidai.gov.in/get/files/media/document/2026-05/Citizen_Charter_Jan24.pdf"
        self.source = Source(
            source_id="src_uidai_citizen_charter_pdf",
            authority="UIDAI",
            domain="aadhaar",
            url=self.official_pdf_url,
            document_title="Citizen's Charter for UIDAI (Jan 2024)",
            source_type=SourceType.OFFICIAL_PDF,
            trust_level=1.0,
        )

        # Ingest real official UIDAI Citizen Charter into ChromaDB
        pdf_bytes, _ = self.loader.load_from_url(self.official_pdf_url)
        parsed_doc = self.parser.parse_pdf(pdf_bytes, fallback_title=self.source.document_title)
        chunks = self.chunker.chunk_document(parsed_doc, self.source, chunk_size=600, chunk_overlap=100)
        self.store.add_chunks(chunks)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_real_uidai_ranking_and_grounding_verification(self):
        req = RetrievalRequest(
            request_id="req_rank_real_001",
            goal="Verify resident rights and service timelines in UIDAI Citizen Charter",
            service="UIDAI Service SLA",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(
                    requirement_id="req_sla",
                    category="procedure",
                    description="What are service delivery timelines under UIDAI Citizen Charter?",
                )
            ],
        )

        result = self.hybrid.retrieve(req, top_k=3)

        self.assertEqual(result.retrieval_status, RetrievalStatus.SUCCESS)
        self.assertGreater(len(result.evidence), 0)

        # 1. Grounding Verification
        for ev in result.evidence:
            self.assertEqual(ev.grounding_status, GroundingStatus.VERIFIED_GROUNDED)
            self.assertGreater(ev.ranking_score, 0.0)

        # 2. Verify deterministic descending score ordering
        scores = [ev.ranking_score for ev in result.evidence]
        sorted_scores = sorted(scores, reverse=True)
        self.assertEqual(scores, sorted_scores, "Evidence entries must be deterministically sorted by ranking_score DESC")


if __name__ == "__main__":
    unittest.main()
