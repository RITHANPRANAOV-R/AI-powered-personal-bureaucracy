"""
Escalation Manager Agent for Medical Chatbot
"""
from google.adk.agents.llm_agent import LlmAgent
from pydantic import BaseModel

# Read prompt files
def load_prompt(filename):
    """Load prompt from prompts directory"""
    try:
        with open(f"prompts/{filename}", "r") as f:
            return f.read()
    except FileNotFoundError:
        return ""

class EscalationOutput(BaseModel):
    escalation_level: str
    action: str
    message_type: str
    final_user_message: str

# Create the Escalation Manager Agent
root_agent = LlmAgent(
    name="escalation_manager_agent",
    model="gemini-2.0-flash",
    description="""
    Agent responsible for determining the correct medical escalation level
    based on risk detection, safety analysis, confidence checks, and crisis signals.
    """,
    instruction=load_prompt("system_prompt.txt"),
    output_schema=EscalationOutput
)

