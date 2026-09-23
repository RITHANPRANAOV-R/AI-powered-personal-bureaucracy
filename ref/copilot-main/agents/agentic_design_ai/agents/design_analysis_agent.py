from google.adk.agents.llm_agent import LlmAgent
from pydantic import BaseModel, Field
from typing import List

class DesignAnalysisOutput(BaseModel):
    architecture: str = Field(description="Inferred architecture pattern")
    workflow: List[str] = Field(description="Key workflow steps")
    components: List[str] = Field(description="Core system components")
    technologies: List[str] = Field(description="Key technologies used for implementation")
    limitations: List[str] = Field(description="Potential design limitations or challenges")

design_analysis_agent = LlmAgent(
    name="DesignAnalysisAgent",
    model="gemini-flash-lite-latest",
    description="""
    You are a software architect.
    Infer the architecture pattern and detailed workflow of the project based on its understanding.
    Identify core components and potential design limitations.
    """,
    output_schema=DesignAnalysisOutput
)
