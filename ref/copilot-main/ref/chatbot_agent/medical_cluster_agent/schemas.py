from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field


RiskLevel = Literal["none", "low", "medium", "high", "critical", "unknown"]
Status = Literal["ok", "need_more_info", "emergency"]


class EvidenceItem(BaseModel):
    source: str = ""
    title: str = ""
    url: str = ""


class ExplainabilitySafety(BaseModel):
    risk_level: RiskLevel = "unknown"
    red_flags_detected: List[str] = Field(default_factory=list)
    why_not_a_diagnosis: str = ""
    when_to_seek_urgent_help: List[str] = Field(default_factory=list)


class Explainability(BaseModel):
    summary: str = ""
    key_factors: List[str] = Field(default_factory=list)
    uncertainties: List[str] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)
    safety: ExplainabilitySafety = Field(default_factory=ExplainabilitySafety)


class SymptomItem(BaseModel):
    name: str
    duration: str = "unknown"
    severity: Literal["mild", "moderate", "severe", "unknown"] = "unknown"
    notes: str = ""


class ConditionItem(BaseModel):
    condition: str
    probability: float = Field(ge=0.0, le=1.0)
    reason: str = ""


class MedicationGuidanceItem(BaseModel):
    name: str
    note: str


class MedicalClusterOutput(BaseModel):
    status: Status
    confidence: float = Field(ge=0.0, le=1.0)

    symptoms: List[SymptomItem] = Field(default_factory=list)
    possible_conditions: List[ConditionItem] = Field(default_factory=list)

    red_flags: List[str] = Field(default_factory=list)
    recommendation: str = ""
    next_steps: List[str] = Field(default_factory=list)

    condition_summary: str = ""
    self_care_guidance: List[str] = Field(default_factory=list)
    medication_guidance: List[MedicationGuidanceItem] = Field(default_factory=list)
    lifestyle_advice: List[str] = Field(default_factory=list)
    when_to_consult_doctor: List[str] = Field(default_factory=list)
    emergency_warning_signs: List[str] = Field(default_factory=list)
    disclaimer: str = ""

    explainability: Explainability = Field(default_factory=Explainability)

