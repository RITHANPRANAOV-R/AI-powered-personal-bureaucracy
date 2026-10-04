# Safety severity score mapping
SAFETY_SEVERITY = {
    "safe": 0,
    "minor_issue": 2,
    "moderate_risk": 4,
    "high_risk": 7,
    "dangerous": 9,
}

# Anything at or above this threshold is unsafe
UNSAFE_THRESHOLD = 4

# Categories considered unsafe regardless of score
UNSAFE_CATEGORIES = {
    "self_medication",
    "dosage_query",
    "diagnosis_attempt",
    "dangerous_claim",
    "mental_health_crisis",
}
