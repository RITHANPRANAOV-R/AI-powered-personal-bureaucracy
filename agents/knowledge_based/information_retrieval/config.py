"""
Configuration settings for Information Retrieval Agent.
"""
import os
from pydantic import BaseModel, Field


class RetrievalConfig(BaseModel):
    """Configuration options for embeddings, vector store, and retrieval."""

    embedding_model_name: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="Local HuggingFace model name for SentenceTransformers"
    )
    embedding_dimension: int = Field(
        default=384,
        description="Vector dimension for all-MiniLM-L6-v2"
    )
    chroma_persist_directory: str = Field(
        default_factory=lambda: os.path.join(os.getcwd(), "data", "chroma_db"),
        description="Local filesystem directory for persistent ChromaDB storage"
    )
    official_collection_name: str = Field(
        default="official_government_knowledge",
        description="ChromaDB collection name for authoritative government knowledge"
    )


# Default global instance
default_config = RetrievalConfig()
