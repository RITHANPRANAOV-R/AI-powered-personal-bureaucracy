from pydantic import BaseModel, Field
from typing import List

class Diagnosis(BaseModel):
    condition: str
    probability: float = Field(ge=0.0, le=1.0)
    reason: str

class ClinicalReasoningOutput(BaseModel):
    differential_diagnosis: List[Diagnosis]
    red_flags: List[str]
    missing_information: List[str]
    recommended_next_steps: List[str]
    confidence: float = Field(ge=0.0, le=1.0)
