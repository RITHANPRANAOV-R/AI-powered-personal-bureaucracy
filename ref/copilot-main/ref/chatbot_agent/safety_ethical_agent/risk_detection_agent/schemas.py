from pydantic import BaseModel, Field
from typing import List, Literal


RiskLevel = Literal["none", "low", "medium", "high", "critical"]


class RiskSignal(BaseModel):
    category: str = Field(..., description="Type of risk (suicide, abuse, medical emergency, etc)")
    evidence: str = Field(..., description="Text that triggered this signal")
    severity: int = Field(..., ge=1, le=10)


class RiskAssessment(BaseModel):
    risk_level: RiskLevel
    summary: str
    signals: List[RiskSignal]
    requires_escalation: bool
