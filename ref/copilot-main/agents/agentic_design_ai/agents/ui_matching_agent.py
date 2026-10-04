from google.adk.agents.llm_agent import LlmAgent
from pydantic import BaseModel, Field
from typing import List

class UIMatchingOutput(BaseModel):
    matched_ui_patterns: List[str] = Field(description="Ranked UI pattern names from knowledge base")
    recommended_sections: List[str] = Field(description="Sections recommended based on matched patterns")
    recommended_components: List[str] = Field(description="Components recommended based on matched patterns")

ui_matching_agent = LlmAgent(
    name="UIMatchingAgent",
    model="gemini-flash-lite-latest",
    description="""
    You are a UI pattern expert.
    Match the current project's UI needs against a repository of known UI patterns.
    Provide actionable recommendations for sections and components based on these matches.
    """,
    output_schema=UIMatchingOutput
)
