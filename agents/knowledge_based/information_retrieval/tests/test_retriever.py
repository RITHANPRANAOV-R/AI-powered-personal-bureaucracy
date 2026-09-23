"""
Unit tests and real integration tests for VectorRetriever and QueryBuilder.
"""
import unittest
import os
import shutil
import tempfile

from agents.knowledge_based.information_retrieval.schemas import (
    Source,
    SourceType,
    Evidence,
    RetrievalRequest,
    RetrievalRequirement,
    RetrievalResult,
    RetrievalStatus,
)
from agents.knowledge_based.information_retrieval.ingestion import (
    DocumentLoader,
    DocumentParser,
    DocumentCleaner,
    DocumentChunker,
)
from agents.knowledge_based.information_retrieval.embeddings import LocalEmbeddingService
from agents.knowledge_based.information_retrieval.retrieval import (
    QueryNormalizer,
    QueryBuilder,
    ConstructedQuery,
    ChromaVectorStore,
    VectorRetriever,
)


class TestQueryNormalizerAndBuilder(unittest.TestCase):
    def setUp(self):
        self.normalizer = QueryNormalizer()
        self.builder = QueryBuilder(normalizer=self.normalizer)

    def test_query_normalization(self):
        raw = "   Aadhaar    name update   -  required documents???   "
        norm = self.normalizer.normalize(raw)
        self.assertEqual(norm, "Aadhaar name update - required documents")

    def test_query_construction_with_entities(self):
        req = RetrievalRequest(
            request_id="req_001",
            goal="Update name in Aadhaar card",
            service="Aadhaar Name Update",
            domain="aadhaar",
            entities={"document": "Aadhaar", "field": "name"},
            requirements=[
                RetrievalRequirement(
                    requirement_id="req_1",
                    category="required_documents",
                    description="What supporting documents are valid for name update?",
                )
            ],
        )
        queries = self.builder.build_queries(req)
        self.assertEqual(len(queries), 1)
        q = queries[0]
        self.assertEqual(q.requirement_id, "req_1")
        self.assertEqual(q.category, "required_documents")
        self.assertIn("aadhaar", q.normalized_query.lower())
        self.assertIn("name", q.normalized_query.lower())

    def test_multiple_requirements_construction(self):
        req = RetrievalRequest(
            request_id="req_002",
            goal="Aadhaar address update",
            service="Aadhaar Address Update",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="eligibility", description="Who is eligible"),
                RetrievalRequirement(requirement_id="r2", category="fees", description="Fee structure"),
            ],
        )
        queries = self.builder.build_queries(req)
        self.assertEqual(len(queries), 2)
        categories = [q.category for q in queries]
        self.assertIn("eligibility", categories)
        self.assertIn("fees", categories)


class TestVectorRetrieverMocked(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.embedder = LocalEmbeddingService()
        self.store = ChromaVectorStore(
            persist_directory=self.temp_dir,
            collection_name="test_retriever_collection",
            embedder=self.embedder,
        )
        self.retriever = VectorRetriever(vector_store=self.store, top_k=2)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_empty_or_invalid_request_handling(self):
        result = self.retriever.retrieve_for_request(None)
        self.assertEqual(result.retrieval_status, RetrievalStatus.FAILED)
        self.assertEqual(len(result.warnings), 1)

    def test_no_hits_retrieval(self):
        req = RetrievalRequest(
            request_id="req_empty",
            goal="Random unknown query",
            service="Unknown Service",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(requirement_id="r1", category="fees", description="Fee details")
            ],
        )
        result = self.retriever.retrieve_for_request(req)
        self.assertEqual(result.retrieval_status, RetrievalStatus.NO_EVIDENCE_FOUND)
        self.assertEqual(len(result.evidence), 0)


class TestRealUIDAIRetrievalIntegration(unittest.TestCase):
    """
    REAL integration test executing query processing and candidate evidence retrieval against stored official UIDAI chunks.
    """
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.loader = DocumentLoader()
        self.parser = DocumentParser()
        self.chunker = DocumentChunker()
        self.embedder = LocalEmbeddingService()
        self.store = ChromaVectorStore(
            persist_directory=self.temp_dir,
            collection_name="uidai_retrieval_phase7_test",
            embedder=self.embedder,
        )
        self.retriever = VectorRetriever(vector_store=self.store, top_k=3)

        self.official_pdf_url = "https://backend.uidai.gov.in/get/files/media/document/2026-05/Citizen_Charter_Jan24.pdf"
        self.source = Source(
            source_id="src_uidai_citizen_charter_pdf",
            authority="UIDAI",
            domain="aadhaar",
            url=self.official_pdf_url,
            document_title="Citizen's Charter for UIDAI (Jan 2024)",
            source_type=SourceType.OFFICIAL_PDF,
        )

        # Ingest real official UIDAI Citizen Charter into ChromaDB
        pdf_bytes, _ = self.loader.load_from_url(self.official_pdf_url)
        parsed_doc = self.parser.parse_pdf(pdf_bytes, fallback_title=self.source.document_title)
        chunks = self.chunker.chunk_document(parsed_doc, self.source, chunk_size=600, chunk_overlap=100)
        self.store.add_chunks(chunks)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_real_uidai_multi_requirement_retrieval(self):
        req = RetrievalRequest(
            request_id="req_uidai_charter_001",
            goal="Understand resident rights, timelines, and services in UIDAI Citizen Charter",
            service="UIDAI Citizen Charter Information",
            domain="aadhaar",
            requirements=[
                RetrievalRequirement(
                    requirement_id="req_rights",
                    category="eligibility",
                    description="What are the main rights of residents under UIDAI Citizen Charter?",
                ),
                RetrievalRequirement(
                    requirement_id="req_timelines",
                    category="procedure",
                    description="What are the service delivery timelines for Aadhaar enrolment and update?",
                ),
                RetrievalRequirement(
                    requirement_id="req_grievance",
                    category="tracking",
                    description="How can residents lodge complaints and track grievance status?",
                ),
            ],
        )

        result = self.retriever.retrieve_for_request(req, top_k=2)

        # 1. Status Check
        self.assertEqual(result.retrieval_status, RetrievalStatus.SUCCESS)
        self.assertEqual(result.request_id, "req_uidai_charter_001")
        self.assertGreater(len(result.evidence), 0)
        self.assertGreater(len(result.sources), 0)

        # 2. Check Candidate Evidence Provenance & Requirement Associations
        first_evidence = result.evidence[0]
        self.assertIsNotNone(first_evidence.evidence_id)
        self.assertIsNotNone(first_evidence.passage)
        self.assertEqual(first_evidence.source.authority, "UIDAI")
        self.assertIn("UIDAI", first_evidence.source.document_title)
        self.assertGreaterEqual(first_evidence.page_number, 1)

        # 3. Check requirement association metadata
        self.assertIn("associated_requirements", first_evidence.metadata)
        self.assertGreater(len(first_evidence.metadata["associated_requirements"]), 0)


if __name__ == "__main__":
    unittest.main()
