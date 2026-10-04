from google.adk.agents.llm_agent import LlmAgent
from pydantic import BaseModel, Field
from typing import List

class MatchedProject(BaseModel):
    name: str
    similarity: float
    architecture: str
    workflow: List[str]
    components: List[str]

class SimilarProjectMatchingOutput(BaseModel):
    matched_projects: List[MatchedProject]

similar_project_matching_agent = LlmAgent(
    name="SimilarProjectMatchingAgent",
    model="gemini-flash-lite-latest",
    description="""
    You are a knowledge retrieval agent.
    Given a list of semantically matched projects retrieved from a vector database,
    summarize and rank the most relevant designs for reference.
    Maintain accuracy regarding the retrieved metadata.
    """,
    output_schema=SimilarProjectMatchingOutput
)
