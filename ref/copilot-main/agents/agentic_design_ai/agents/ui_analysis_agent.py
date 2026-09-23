from google.adk.agents.llm_agent import LlmAgent
from pydantic import BaseModel, Field
from typing import List

class UIAnalysisOutput(BaseModel):
    ui_features: List[str] = Field(description="Predicted or existing UI features")
    ui_components: List[str] = Field(description="UI components identified or required")
    ui_sections: List[str] = Field(description="Major UI layout sections")
    missing_sections: List[str] = Field(description="Potentially missing critical UI sections")

ui_analysis_agent = LlmAgent(
    name="UIAnalysisAgent",
    model="gemini-flash-lite-latest",
    description="""
    You are a UI/UX analyst.
    Extract the UI structure from the project description and requirements.
    Identify features, components, and layout sections. 
    Infer what might be missing based on standard UX patterns for this project type.
    """,
    output_schema=UIAnalysisOutput
)
