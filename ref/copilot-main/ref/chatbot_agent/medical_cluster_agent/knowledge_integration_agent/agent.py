
from google.adk.agents.llm_agent import LlmAgent

from .schemas import KnowledgeResponse, EvidenceDoc
from .tools import (
    search_openfda,
    search_rxnav,
    search_pubmed,
    search_who_icd,
    search_clinical_tables,
)

# ==========================================
# PURE PYTHON KNOWLEDGE RETRIEVAL FUNCTION
# ==========================================
def retrieve_medical_knowledge(query: dict) -> dict:
    """
    query = {
        "drugs": [...],
        "suspected_conditions": [...]
    }
    """

    evidence = []

    # -----------------------------
    # DRUG SOURCES
    # -----------------------------
    for drug in query.get("drugs", []):
        for item in search_openfda(drug):
            evidence.append(EvidenceDoc(
                source="OpenFDA",
                title=item["title"],
                summary=item["summary"],
                url=item["url"]
            ))

        for item in search_rxnav(drug):
            evidence.append(EvidenceDoc(
                source="RxNorm",
                title=item["title"],
                summary=item["summary"],
                url=item["url"]
            ))

    # -----------------------------
    # CONDITION SOURCES
    # -----------------------------
    for cond in query.get("suspected_conditions", []):
        for item in search_pubmed(cond):
            evidence.append(EvidenceDoc(
                source="PubMed",
                title=item["title"],
                summary=item["summary"],
                url=item["url"]
            ))

        for item in search_who_icd(cond):
            evidence.append(EvidenceDoc(
                source="WHO ICD-11",
                title=item["title"],
                summary=item["summary"],
                url=item["url"]
            ))

        for item in search_clinical_tables(cond):
            evidence.append(EvidenceDoc(
                source="ClinicalTables",
                title=item["title"],
                summary=item["summary"],
                url=item["url"]
            ))

    return KnowledgeResponse(evidence=evidence).dict()


# ==========================================
# AGENT
# ==========================================
root_agent = LlmAgent(
    name="knowledge_integration_agent",
    model="gemini-2.0-flash",
    description="""
You are a Medical Knowledge Integration Agent.

Your job:
1. You will receive JSON or a summary with symptomslike:
   {
     "drugs": [...],
     "suspected_conditions": [...]
   }

2. You MUST call the Python function:
   retrieve_medical_knowledge(query)

3. You MUST return its output with the medicine for the symptoms provided.

RULES:
- Do NOT hallucinate.
- Do NOT invent medical facts.
- Only return the function result.
- Always return JSON.
""",
)
