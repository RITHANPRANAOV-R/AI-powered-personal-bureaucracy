from pydantic import BaseModel
from typing import Optional

class StressAnxietyOutput(BaseModel):
    message: str
    detected_emotion: Optional[str] = None
