from google.adk.agents.llm_agent import LlmAgent
from pydantic import BaseModel, Field
from typing import List

class PromptGenerationOutput(BaseModel):
    build_prompts: List[str] = Field(description="Prompts to implement missing components")
    architecture_prompts: List[str] = Field(description="Prompts to refactor or enhance architecture")
    ui_prompts: List[str] = Field(description="Prompts to build missing UI sections")

prompt_generation_agent = LlmAgent(
    name="PromptGenerationAgent",
    model="gemini-flash-lite-latest",
    description="""
    You are an automation engineer.
    Convert the gaps identified by the DesignComparisonAgent into actionable building prompts.
    The prompts should be detailed enough for another LLM to use to implement the missing parts.
    """,
    output_schema=PromptGenerationOutput
)
