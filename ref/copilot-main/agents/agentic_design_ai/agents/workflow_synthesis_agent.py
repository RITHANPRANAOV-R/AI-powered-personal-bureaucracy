from google.adk.agents.llm_agent import LlmAgent
from pydantic import BaseModel, Field
from typing import List

class WorkflowSynthesisOutput(BaseModel):
    reference_architecture: str = Field(description="Normalized canonical architecture for this project type")
    reference_workflow: List[str] = Field(description="Consolidated reference workflow steps")
    reference_components: List[str] = Field(description="Standard components required for this design")

workflow_synthesis_agent = LlmAgent(
    name="WorkflowSynthesisAgent",
    model="gemini-flash-lite-latest",
    description="""
    You are a systems design synthesizer.
    Merge the best parts of matched reference projects to produce a canonical, high-quality reference design for the current project.
    Ensure the reference design is balanced and follows industry best practices.
    """,
    output_schema=WorkflowSynthesisOutput
)
