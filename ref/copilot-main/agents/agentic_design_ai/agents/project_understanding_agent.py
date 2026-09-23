from google.adk.agents.llm_agent import LlmAgent
from pydantic import BaseModel, Field
from typing import List

class ProjectUnderstandingOutput(BaseModel):
    project_overview: str = Field(description="Brief overview of the project")
    project_type: str = Field(description="Category of the project (e.g., E-commerce, AI App)")
    features: List[str] = Field(description="Main features identified")
    capabilities: List[str] = Field(description="System capabilities")
    tech_stack: List[str] = Field(description="Inferred technology stack")
    file_structure_summary: str = Field(description="High-level summary of the files")

project_understanding_agent = LlmAgent(
    name="ProjectUnderstandingAgent",
    model="gemini-flash-lite-latest",
    description="""
    You are an expert software analyst. 
    Analyze the project based on the prompt, description, and file structure provided.
    Extract key features, technology stack, and categorize the project type.
    Be thorough but concise.
    """,
    output_schema=ProjectUnderstandingOutput
)
