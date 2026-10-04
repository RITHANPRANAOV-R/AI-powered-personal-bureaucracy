from .schemas import ClinicalReasoningOutput

def self_critique(result: ClinicalReasoningOutput) -> ClinicalReasoningOutput:
    """
    Safety & overconfidence reduction layer.
    """

    # If only one diagnosis and very high confidence, reduce certainty
    if len(result.differential_diagnosis) == 1 and result.confidence > 0.85:
        result.confidence = 0.75
        result.recommended_next_steps.append(
            "Consider alternative diagnoses and seek professional medical evaluation."
        )

    # If no red flags but symptoms are serious keywords
    serious_keywords = ["chest pain", "shortness of breath", "fainting", "blood"]

    combined_text = " ".join(
        d.condition.lower() for d in result.differential_diagnosis
    )

    for word in serious_keywords:
        if word in combined_text and not result.red_flags:
            result.red_flags.append("Potential serious condition needs urgent evaluation.")

    # Re-normalize probabilities
    total = sum(d.probability for d in result.differential_diagnosis)
    if total > 0:
        for d in result.differential_diagnosis:
            d.probability = d.probability / total

    return result
