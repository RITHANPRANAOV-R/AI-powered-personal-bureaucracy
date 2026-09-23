import numpy as np
import json
import os

class VectorStore:
    def __init__(self, storage_path="vector_store.json"):
        self.storage_path = storage_path
        self.index = {}

    def add(self, id, embedding, metadata):
        # Convert embedding to list for JSON serialization
        if isinstance(embedding, np.ndarray):
            embedding = embedding.tolist()
        self.index[id] = {
            "embedding": embedding,
            "metadata": metadata
        }

    def save(self):
        with open(self.storage_path, 'w') as f:
            json.dump(self.index, f)

    def load(self):
        if os.path.exists(self.storage_path):
            with open(self.storage_path, 'r') as f:
                self.index = json.load(f)
        return self.index

    def search(self, query_embedding, top_k=3):
        results = []
        for id, data in self.index.items():
            emb = np.array(data["embedding"])
            score = np.dot(query_embedding, emb) / (np.linalg.norm(query_embedding) * np.linalg.norm(emb))
            results.append({
                "id": id,
                "metadata": data["metadata"],
                "score": float(score)
            })
        
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]
