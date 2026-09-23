from sentence_transformers import SentenceTransformer
import json
import os
from .vector_store import VectorStore

class EmbeddingIndex:
    def __init__(self, model_name='all-MiniLM-L6-v2'):
        self.model = SentenceTransformer(model_name)
        self.store = VectorStore(storage_path=os.path.join(os.path.dirname(__file__), "vector_store.json"))

    def index_projects(self, json_path):
        with open(json_path, 'r') as f:
            projects = json.load(f)
        
        for idx, project in enumerate(projects):
            text = f"{project['name']}: {project['description']} Architecture: {project['architecture']}"
            embedding = self.model.encode(text)
            self.store.add(f"project_{idx}", embedding, project)
        
        self.store.save()

    def index_ui_patterns(self, json_path):
        with open(json_path, 'r') as f:
            patterns = json.load(f)
        
        for idx, pattern in enumerate(patterns):
            text = f"{pattern['name']}: Sections: {', '.join(pattern['sections'])} Components: {', '.join(pattern['components'])}"
            embedding = self.model.encode(text)
            self.store.add(f"ui_pattern_{idx}", embedding, pattern)
        
        self.store.save()

if __name__ == "__main__":
    indexer = EmbeddingIndex()
    base_dir = os.path.dirname(os.path.dirname(__file__))
    indexer.index_projects(os.path.join(base_dir, "knowledge_base", "sample_projects.json"))
    indexer.index_ui_patterns(os.path.join(base_dir, "knowledge_base", "ui_patterns.json"))
