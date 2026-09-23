"""
Embeddings Package for Information Retrieval Agent.
"""
from agents.knowledge_based.information_retrieval.embeddings.embedder import (
    LocalEmbeddingService,
    EmbeddingError,
)

__all__ = ["LocalEmbeddingService", "EmbeddingError"]
