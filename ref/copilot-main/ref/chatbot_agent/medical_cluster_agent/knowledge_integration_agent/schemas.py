from pydantic import BaseModel
from typing import List, Dict, Any

class EvidenceDoc(BaseModel):
    source: str
    title: str
    summary: str
    url: str

class KnowledgeResponse(BaseModel):
    evidence: List[EvidenceDoc]
