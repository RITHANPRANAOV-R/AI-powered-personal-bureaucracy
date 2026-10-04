import json
from .schemas import ClinicalReasoningOutput
from .self_critique import self_critique

CONFIDENCE_THRESHOLD = 0.75

def parse_model_json(text: str) -> ClinicalReasoningOutput:
    result = ClinicalReasoningOutput(**json.loads(text))
    result = self_critique(result)
    return result

def should_stop(result: ClinicalReasoningOutput) -> bool:
    if len(result.red_flags) > 0:
        return True
    if result.confidence >= CONFIDENCE_THRESHOLD:
        return True
    return False

def needs_more_info(result: ClinicalReasoningOutput) -> bool:
    return len(result.missing_information) > 0
