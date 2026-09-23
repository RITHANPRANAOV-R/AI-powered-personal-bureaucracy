from google.adk.agents.llm_agent import LlmAgent
from pydantic import BaseModel, Field
from typing import List

class DesignComparisonOutput(BaseModel):
    missing_architecture_parts: List[str] = Field(description="Gaps in the user's architecture")
    missing_workflow_steps: List[str] = Field(description="Missing steps in the user's workflow")
    missing_components: List[str] = Field(description="Missing backend/system components")
    missing_ui_sections: List[str] = Field(description="Missing frontend sections/screens")
    improvements: List[str] = Field(description="General suggestions for refinement")

design_comparison_agent = LlmAgent(
    name="DesignComparisonAgent",
    model="gemini-flash-lite-latest",
    description="""
    You are a structural design critic.
    Compare the inferred project design against the synthesized reference design.
    Identify specific gaps in architecture, workflow, components, and UI.
    Be objective and highlight areas that could improve scalability or user experience.
    """,
    output_schema=DesignComparisonOutput
)
