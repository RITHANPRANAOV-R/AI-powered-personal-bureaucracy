"""
Medical Safety Checker Agent for Medical Chatbot
"""

from google.adk.agents.llm_agent import LlmAgent
from pydantic import BaseModel
from typing import List, Dict

# Utility to read prompt files
def load_prompt(filename):
    """Load prompt from prompts directory"""
    try:
        with open(f"prompts/{filename}", "r") as f:
            return f.read()
    except FileNotFoundError:
        return ""


# ---------------------------
# Output Schema
# ---------------------------
class Issue(BaseModel):
    category: str
    evidence: str
    severity: int

class MedicalSafetyOutput(BaseModel):
    safety_flag: str                    # SAFE / UNSAFE
    issues_detected: List[Issue]        # List of issues
    explanation: str                    # Short explanation
    recommended_actions: List[str]      # Recommended next steps
    is_safe_to_answer: bool             # Can AI answer safely?
    unsafe_reason: str                  # Reason why unsafe (if applicable)


# ---------------------------
# Create Medical Safety Checker Agent
# ---------------------------
root_agent = LlmAgent(
    name="medical_safety_checker",
    model="gemini-2.0-flash",
    description="""
    Agent responsible for detecting unsafe or harmful medical content
    such as self-medication, incorrect dosage, diagnosis attempts,
    dangerous instructions, and unsafe medical claims.
    """,
    instruction="""
You are a Medical Safety Checker.
Do NOT provide medical advice.
Do NOT explain or answer the user query.
Your only job is to detect potential safety risks.

Output MUST be JSON ONLY and match this schema:

{
  "safety_flag": "SAFE|UNSAFE",
  "issues_detected": [
    {
      "category": "string",
      "evidence": "string",
      "severity": 1-10
    }
  ],
  "explanation": "string",
  "recommended_actions": ["string"],
  "is_safe_to_answer": true|false,
  "unsafe_reason": "string"
}

- Analyze the user's input.
- If it involves dosage, self-medication, or unsafe medical questions, mark UNSAFE.
- Provide brief explanation and recommended action.
""",
    output_schema=MedicalSafetyOutput
)

__all__ = ["root_agent"]
