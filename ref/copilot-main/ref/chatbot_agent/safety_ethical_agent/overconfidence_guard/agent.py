"""
Overconfidence Guard Agent for Medical Chatbot
"""
from google.adk.agents.llm_agent import LlmAgent
from pydantic import BaseModel
from .utils.confidence_checker import check_overconfidence
from .utils.thresholds import CONFIDENCE_THRESHOLD
from .prompts.over_confidence import SYSTEM_PROMPT

class OverconfidenceOutput(BaseModel):
    confidence_flag: bool      # True if overconfident
    confidence_score: float    # Model's confidence level
    action: str                # Suggested action (e.g., escalate, warn)
    message_type: str          # Type of message (info/warning/escalation)
    final_user_message: str    # Processed user message

# ------------------------------
# Must be called root_agent for ADK Web
# ------------------------------
root_agent = LlmAgent(
    name="overconfidence_guard_agent",
    model="gemini-2.0-flash",
    description="""
    Agent responsible for detecting overconfident responses in the medical chatbot.
    Triggers warnings or escalations if confidence exceeds defined thresholds.
    """,
    instruction=SYSTEM_PROMPT,
    output_schema=OverconfidenceOutput
)

# ------------------------------
# Optional helper function
# ------------------------------
def run_overconfidence_check(message: str, confidence_score: float) -> OverconfidenceOutput:
    """
    Checks if the confidence score is over the threshold and returns structured output.
    """
    flag = check_overconfidence(confidence_score, CONFIDENCE_THRESHOLD)
    action = "escalate to human" if flag else "proceed"
    message_type = "warning" if flag else "info"
    
    return OverconfidenceOutput(
        confidence_flag=flag,
        confidence_score=confidence_score,
        action=action,
        message_type=message_type,
        final_user_message=message
    )
