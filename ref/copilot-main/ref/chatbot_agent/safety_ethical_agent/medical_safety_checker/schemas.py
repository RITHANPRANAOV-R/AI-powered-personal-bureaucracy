from pydantic import BaseModel, Field
from typing import List, Literal

SafetyFlag = Literal["SAFE", "UNSAFE"]


class SafetyIssue(BaseModel):
    category: str = Field(..., description="Type of safety issue (self_medication, dosage_query, crisis, etc.)")
    evidence: str = Field(..., description="The specific text that triggered the safety concern")
    severity: int = Field(..., ge=1, le=10, description="Severity score from 1 to 10")


class MedicalSafetyOutput(BaseModel):
    safety_flag: SafetyFlag
    issues_detected: List[SafetyIssue]
    explanation: str
    recommended_actions: List[str]

    # REQUIRED for Escalation Manager logic
    is_safe_to_answer: bool = Field(..., description="Whether the chatbot is allowed to answer safely")
    unsafe_reason: str = Field("", description="Reason if the message is unsafe")
