from sentence_transformers import SentenceTransformer
from .vector_store import VectorStore
import os

class SimilaritySearch:
    def __init__(self, model_name='all-MiniLM-L6-v2'):
        self.model = SentenceTransformer(model_name)
        self.store = VectorStore(storage_path=os.path.join(os.path.dirname(__file__), "vector_store.json"))
        self.store.load()

    def find_similar_projects(self, description, top_k=3):
        query_embedding = self.model.encode(description)
        all_results = self.store.search(query_embedding, top_k=10)
        project_results = [res for res in all_results if res["id"].startswith("project_")]
        return project_results[:top_k]

    def find_similar_ui(self, description, top_k=2):
        query_embedding = self.model.encode(description)
        all_results = self.store.search(query_embedding, top_k=10)
        ui_results = [res for res in all_results if res["id"].startswith("ui_pattern_")]
        return ui_results[:top_k]
