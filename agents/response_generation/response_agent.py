from google.adk.agents import Agent
from .prompt import RESPONSE_GENERATION_PROMPT
from .schema import ExecutionResult, CitizenResponse, get_clean_output_schema

response_generation_agent = Agent(
    name="response_generation_agent",
    model="gemini-3.6-flash",
    description="""
    Converts multi-agent execution results for any government document process
    (Aadhaar, Passport, Community Certificate, etc.) into clear, actionable,
    citizen-friendly responses for UI visual dashboards and chat interfaces.
    """,
    instruction=RESPONSE_GENERATION_PROMPT,
    input_schema=ExecutionResult,
    output_schema=get_clean_output_schema(CitizenResponse),
)