from pydantic import BaseModel, Field
from typing import List, Literal

class Symptom(BaseModel):
    name: str
    duration: str = "unknown"
    severity: Literal["mild", "moderate", "severe", "unknown"] = "unknown"
    notes: str = ""

class SymptomDetectiveOutput(BaseModel):
    symptoms: List[Symptom]
    missing_information: List[str]
