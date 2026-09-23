"""
Unit tests and real integration tests for Local Embeddings and ChromaDB Vector Store.
"""
import unittest
import os
import shutil
import tempfile

from agents.knowledge_based.information_retrieval.schemas.source import Source, SourceType
from agents.knowledge_based.information_retrieval.ingestion import (
    DocumentLoader,
    DocumentParser,
    DocumentCleaner,
    DocumentChunker,
    DocumentChunk,
)
from agents.knowledge_based.information_retrieval.embeddings import (
    LocalEmbeddingService,
    EmbeddingError,
)
from agents.knowledge_based.information_retrieval.retrieval import (
    ChromaVectorStore,
    VectorStoreError,
)


class TestLocalEmbeddingService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.embedder = LocalEmbeddingService()

    def test_single_text_embedding_and_dimension(self):
        vec = self.embedder.embed_text("Official UIDAI Aadhaar guidelines")
        self.assertIsInstance(vec, list)
        self.assertEqual(len(vec), 384)
        self.assertIsInstance(vec[0], float)

    def test_batch_embedding_order_preservation(self):
        texts = ["Text item alpha", "Text item beta", "Text item gamma"]
        vectors = self.embedder.embed_batch(texts)
        self.assertEqual(len(vectors), 3)
        self.assertEqual(len(vectors[0]), 384)
        self.assertEqual(len(vectors[1]), 384)

    def test_empty_input_handling(self):
        with self.assertRaises(EmbeddingError):
            self.embedder.embed_text("")

        with self.assertRaises(EmbeddingError):
            self.embedder.embed_text("   ")


class TestChromaVectorStorePersistenceAndIdempotency(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.embedder = LocalEmbeddingService()
        self.store = ChromaVectorStore(
            persist_directory=self.temp_dir,
            collection_name="test_official_knowledge",
            embedder=self.embedder,
        )
        self.source = Source(
            source_id="src_test_doc",
            authority="UIDAI",
            domain="aadhaar",
            url="https://uidai.gov.in/test.pdf",
            document_title="Test Document Title",
            last_checked="2026-01-01T00:00:00Z",
        )
        self.sample_chunks = [
            DocumentChunk(
                chunk_id="src_test_doc_p1_c0",
                source_id="src_test_doc",
                authority="UIDAI",
                document_title="Test Document Title",
                document_url="https://uidai.gov.in/test.pdf",
                page_number=1,
                text="Aadhaar address update procedure requires valid address proof document.",
                token_count_approx=15,
                retrieved_at="2026-01-01T00:00:00Z",
                chunk_index=0,
            ),
            DocumentChunk(
                chunk_id="src_test_doc_p2_c1",
                source_id="src_test_doc",
                authority="UIDAI",
                document_title="Test Document Title",
                document_url="https://uidai.gov.in/test.pdf",
                page_number=2,
                text="The fee for updating Aadhaar details online is Rupees 50.",
                token_count_approx=12,
                retrieved_at="2026-01-01T00:00:00Z",
                chunk_index=1,
            ),
        ]

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_insertion_and_metadata_preservation(self):
        count = self.store.add_chunks(self.sample_chunks)
        self.assertEqual(count, 2)
        self.assertEqual(self.store.count(), 2)

        record = self.store.get_by_id("src_test_doc_p1_c0")
        self.assertIsNotNone(record)
        self.assertEqual(record["chunk_id"], "src_test_doc_p1_c0")
        self.assertEqual(record["metadata"]["authority"], "UIDAI")
        self.assertEqual(record["metadata"]["page_number"], 1)

    def test_idempotent_duplicate_upsert(self):
        # Insert once
        self.store.add_chunks(self.sample_chunks)
        self.assertEqual(self.store.count(), 2)

        # Re-ingest exact same chunks
        self.store.add_chunks(self.sample_chunks)
        # Total count should remain 2, not double to 4
        self.assertEqual(self.store.count(), 2)

    def test_persistence_across_client_reopen(self):
        # Process A: Insert chunks into store
        self.store.add_chunks(self.sample_chunks)
        self.assertEqual(self.store.count(), 2)
        del self.store  # Close Process A store handle

        # Process B: Re-open new client using SAME persistence path
        new_store = ChromaVectorStore(
            persist_directory=self.temp_dir,
            collection_name="test_official_knowledge",
            embedder=self.embedder,
        )

        self.assertEqual(new_store.count(), 2)
        record = new_store.get_by_id("src_test_doc_p2_c1")
        self.assertIsNotNone(record)
        self.assertIn("Rupees 50", record["text"])
        self.assertEqual(record["metadata"]["page_number"], 2)

    def test_semantic_search_smoke_test(self):
        self.store.add_chunks(self.sample_chunks)

        results = self.store.query_similar("How much does it cost to update Aadhaar?", top_k=1)
        self.assertEqual(len(results), 1)
        top_match = results[0]

        self.assertEqual(top_match["chunk_id"], "src_test_doc_p2_c1")
        self.assertIn("Rupees 50", top_match["text"])
        self.assertIsNotNone(top_match["distance"])
        self.assertEqual(top_match["metadata"]["authority"], "UIDAI")
        self.assertEqual(top_match["metadata"]["page_number"], 2)


class TestRealOfficialUIDAIVectorStoreIntegration(unittest.TestCase):
    """
    REAL integration test performing full end-to-end flow:
    Real UIDAI PDF -> Ingestion -> Embeddings -> Persistent ChromaDB -> Semantic Query.
    """
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.loader = DocumentLoader()
        self.parser = DocumentParser()
        self.chunker = DocumentChunker()
        self.embedder = LocalEmbeddingService()
        self.store = ChromaVectorStore(
            persist_directory=self.temp_dir,
            collection_name="uidai_real_knowledge_test",
            embedder=self.embedder,
        )

        self.official_pdf_url = "https://backend.uidai.gov.in/get/files/media/document/2026-05/Citizen_Charter_Jan24.pdf"
        self.source = Source(
            source_id="src_uidai_citizen_charter_pdf",
            authority="UIDAI",
            domain="aadhaar",
            url=self.official_pdf_url,
            document_title="Citizen's Charter for UIDAI (Jan 2024)",
            source_type=SourceType.OFFICIAL_PDF,
        )

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_real_uidai_document_embedding_and_retrieval(self):
        # 1. Phase 5 Ingestion
        pdf_bytes, _ = self.loader.load_from_url(self.official_pdf_url)
        parsed_doc = self.parser.parse_pdf(pdf_bytes, fallback_title=self.source.document_title)
        chunks = self.chunker.chunk_document(parsed_doc, self.source, chunk_size=600, chunk_overlap=100)

        self.assertGreater(len(chunks), 20)

        # 2. Embed & Ingest into ChromaDB
        added_count = self.store.add_chunks(chunks)
        self.assertEqual(added_count, len(chunks))
        self.assertEqual(self.store.count(), len(chunks))

        # 3. Semantic Search Smoke Test against real stored UIDAI vector knowledge
        query = "What are resident rights and timelines in UIDAI Citizen Charter?"
        search_results = self.store.query_similar(query, top_k=3)

        self.assertEqual(len(search_results), 3)

        top_result = search_results[0]
        self.assertIsNotNone(top_result["chunk_id"])
        self.assertIsNotNone(top_result["text"])
        self.assertIsNotNone(top_result["distance"])
        self.assertEqual(top_result["metadata"]["authority"], "UIDAI")
        self.assertEqual(top_result["metadata"]["source_id"], "src_uidai_citizen_charter_pdf")
        self.assertGreaterEqual(top_result["metadata"]["page_number"], 1)


if __name__ == "__main__":
    unittest.main()
