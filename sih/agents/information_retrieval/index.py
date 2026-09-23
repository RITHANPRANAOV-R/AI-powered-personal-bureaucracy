"""Simple local chunk cache with optional Ollama embeddings. No Chroma."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Optional

from .config import RetrievalConfig, load_retrieval_config


class LocalChunkIndex:
    """
    JSONL cache of official-source chunks plus optional embedding vectors.

    Chosen over Chroma so every chunk keeps explicit URL/host/retrieved_at/hash
    provenance without a stale external collection.
    """

    def __init__(self, config: Optional[RetrievalConfig] = None) -> None:
        self.config = config or load_retrieval_config()
        self.path = self.config.cache_dir / "chunks.jsonl"
        self._rows: list[dict] = []

    def load(self) -> None:
        self._rows = []
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                self._rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    def add_chunk(self, row: dict) -> None:
        self._rows.append(row)

    def persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            for row in self._rows:
                serializable = {k: v for k, v in row.items() if k != "embedding" or isinstance(v, list)}
                handle.write(json.dumps(serializable, ensure_ascii=False) + "\n")

    def search(self, query: str, query_embedding: Optional[list[float]], limit: int = 8) -> list[dict]:
        scored: list[tuple[float, dict]] = []
        q_tokens = _tokens(query)
        for row in self._rows:
            keyword = _jaccard(q_tokens, _tokens(row.get("text") or ""))
            semantic = 0.0
            if query_embedding and row.get("embedding"):
                semantic = _cosine(query_embedding, row["embedding"])
            score = 0.6 * semantic + 0.4 * keyword if query_embedding and row.get("embedding") else keyword
            if score > 0:
                scored.append((score, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        results = []
        for score, row in scored[:limit]:
            item = dict(row)
            item["score"] = round(float(score), 4)
            results.append(item)
        return results


def _tokens(text: str) -> set[str]:
    return {part for part in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split() if len(part) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return (dot / (na * nb) + 1) / 2
