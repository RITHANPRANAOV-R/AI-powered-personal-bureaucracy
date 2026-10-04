from pydantic import BaseModel, Field
from typing import List


class MedicationItem(BaseModel):
    name: str
    note: str


class GuidanceComposerOutput(BaseModel):
    condition_summary: str
    self_care_guidance: List[str]
    medication_guidance: List[MedicationItem]
    lifestyle_advice: List[str]
    when_to_consult_doctor: List[str]
    emergency_warning_signs: List[str]
    disclaimer: str = Field(
        default="This guidance is informational and not a medical diagnosis. Consult a healthcare professional for personalized advice."
    )
