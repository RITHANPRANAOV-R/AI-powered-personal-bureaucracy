from pydantic import BaseModel
from typing import Optional

class EmotionDetectionOutput(BaseModel):
    emotion: str
    confidence: float
    intensity: Optional[str] = None
    intent: Optional[str] = None
    sentiment: Optional[str] = None 