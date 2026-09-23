"""
ChromaDB Persistent Vector Store Integration.
"""
import os
import logging
from typing import List, Dict, Any, Optional
import chromadb

from agents.knowledge_based.information_retrieval.config import default_config
from agents.knowledge_based.information_retrieval.ingestion.chunker import DocumentChunk
from agents.knowledge_based.information_retrieval.embeddings.embedder import LocalEmbeddingService

logger = logging.getLogger(__name__)


class VectorStoreError(Exception):
    """Exception raised when vector store operation fails."""
    pass


class ChromaVectorStore:
    """
    Manages persistent local ChromaDB collection for authoritative government knowledge.
    """

    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: Optional[str] = None,
        embedder: Optional[LocalEmbeddingService] = None,
    ):
        self.persist_directory = persist_directory or default_config.chroma_persist_directory
        self.collection_name = collection_name or default_config.official_collection_name
        self.embedder = embedder or LocalEmbeddingService()

        # Ensure persistence directory exists
        os.makedirs(self.persist_directory, exist_ok=True)

        try:
            self._client = chromadb.PersistentClient(path=self.persist_directory)
            self._collection = self._client.get_or_create_collection(name=self.collection_name)
        except Exception as e:
            raise VectorStoreError(f"Failed to initialize ChromaDB persistent client at '{self.persist_directory}': {e}")

    def add_chunks(self, chunks: List[DocumentChunk]) -> int:
        """
        Embeds and stores DocumentChunks idempotently in ChromaDB.
        Re-ingesting existing chunk_ids updates records without creating duplicates.
        """
        if not chunks:
            return 0

        valid_chunks, embeddings = self.embedder.embed_chunks(chunks)
        if not valid_chunks:
            return 0

        ids: List[str] = []
        documents: List[str] = []
        metadatas: List[Dict[str, Any]] = []

        for chunk in valid_chunks:
            ids.append(chunk.chunk_id)
            documents.append(chunk.text)

            meta = {
                "chunk_id": chunk.chunk_id,
                "source_id": chunk.source_id,
                "authority": chunk.authority,
                "document_title": chunk.document_title,
                "document_url": chunk.document_url or "",
                "document_version": chunk.document_version or "",
                "page_number": chunk.page_number,
                "retrieved_at": chunk.retrieved_at,
                "chunk_index": chunk.chunk_index,
                "token_count_approx": chunk.token_count_approx,
            }
            metadatas.append(meta)

        try:
            self._collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )
            logger.info(f"Upserted {len(ids)} chunks into collection '{self.collection_name}'")
            return len(ids)
        except Exception as e:
            raise VectorStoreError(f"Failed to upsert chunks into ChromaDB: {e}")

    def query_similar(
        self,
        query_text: str,
        top_k: int = 5,
        where_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Executes semantic vector similarity search against the persistent collection.
        """
        if not query_text or not query_text.strip():
            raise VectorStoreError("Query text cannot be empty")

        query_vector = self.embedder.embed_text(query_text)

        try:
            kwargs: Dict[str, Any] = {
                "query_embeddings": [query_vector],
                "n_results": top_k,
            }
            if where_filter:
                kwargs["where"] = where_filter

            results = self._collection.query(**kwargs)

            formatted_results: List[Dict[str, Any]] = []
            if results and results.get("ids") and results["ids"][0]:
                res_ids = results["ids"][0]
                res_docs = results["documents"][0] if results.get("documents") else []
                res_metas = results["metadatas"][0] if results.get("metadatas") else []
                res_dists = results["distances"][0] if results.get("distances") else []

                for idx in range(len(res_ids)):
                    formatted_results.append({
                        "chunk_id": res_ids[idx],
                        "text": res_docs[idx] if idx < len(res_docs) else "",
                        "metadata": res_metas[idx] if idx < len(res_metas) else {},
                        "distance": res_dists[idx] if idx < len(res_dists) else None,
                    })

            return formatted_results
        except Exception as e:
            raise VectorStoreError(f"Failed to execute semantic query on ChromaDB: {e}")

    def count(self) -> int:
        """Returns total record count in collection."""
        try:
            return self._collection.count()
        except Exception as e:
            raise VectorStoreError(f"Error counting records in collection: {e}")

    def get_by_id(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single record by chunk_id."""
        try:
            res = self._collection.get(ids=[chunk_id])
            if res and res.get("ids") and res["ids"]:
                return {
                    "chunk_id": res["ids"][0],
                    "text": res["documents"][0] if res.get("documents") else "",
                    "metadata": res["metadatas"][0] if res.get("metadatas") else {},
                }
            return None
        except Exception as e:
            raise VectorStoreError(f"Error retrieving chunk '{chunk_id}': {e}")
