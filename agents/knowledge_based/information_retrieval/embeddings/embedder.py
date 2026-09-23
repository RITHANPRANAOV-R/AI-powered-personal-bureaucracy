"""
Local Embedding Service using Sentence Transformers.
"""
import logging
from typing import List, Tuple, Optional
from sentence_transformers import SentenceTransformer

from agents.knowledge_based.information_retrieval.config import default_config
from agents.knowledge_based.information_retrieval.ingestion.chunker import DocumentChunk

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Exception raised when embedding generation fails."""
    pass


class LocalEmbeddingService:
    """
    Local embedding engine powered by SentenceTransformers (all-MiniLM-L6-v2).
    """

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or default_config.embedding_model_name
        self._model: Optional[SentenceTransformer] = None

    def _get_model(self) -> SentenceTransformer:
        """Lazy load local SentenceTransformer model safely."""
        if self._model is None:
            try:
                logger.info(f"Loading local embedding model: {self.model_name}")
                self._model = SentenceTransformer(self.model_name)
            except Exception as e:
                raise EmbeddingError(f"Failed to load local embedding model '{self.model_name}': {e}")
        return self._model

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding vector for a single text string."""
        if not text or not text.strip():
            raise EmbeddingError("Cannot generate embedding for empty or whitespace text")

        try:
            model = self._get_model()
            vector = model.encode(text, convert_to_numpy=True, show_progress_bar=False)
            return vector.tolist()
        except Exception as e:
            if isinstance(e, EmbeddingError):
                raise
            raise EmbeddingError(f"Error generating text embedding: {e}")

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embedding vectors for a batch of text strings while preserving order.
        """
        if not texts:
            return []

        # Validate non-empty items
        valid_indices = [i for i, t in enumerate(texts) if t and t.strip()]
        if not valid_indices:
            raise EmbeddingError("Cannot generate embeddings for an empty text batch")

        try:
            model = self._get_model()
            valid_texts = [texts[i] for i in valid_indices]
            vectors = model.encode(valid_texts, batch_size=32, convert_to_numpy=True, show_progress_bar=False)

            results: List[Optional[List[float]]] = [None] * len(texts)
            for idx, vector in zip(valid_indices, vectors):
                results[idx] = vector.tolist()

            return [v for v in results if v is not None]
        except Exception as e:
            if isinstance(e, EmbeddingError):
                raise
            raise EmbeddingError(f"Batch embedding failed: {e}")

    def embed_chunks(self, chunks: List[DocumentChunk]) -> Tuple[List[DocumentChunk], List[List[float]]]:
        """
        Extracts non-empty chunk texts, computes embeddings in batch, and returns matching pairs.
        """
        valid_chunks = [c for c in chunks if c.text and c.text.strip()]
        if not valid_chunks:
            return [], []

        texts = [c.text for c in valid_chunks]
        embeddings = self.embed_batch(texts)
        return valid_chunks, embeddings
