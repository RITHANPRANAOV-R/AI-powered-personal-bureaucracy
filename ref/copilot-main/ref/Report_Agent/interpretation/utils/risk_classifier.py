def classify_risk(text: str):
    text = text.lower()

    if any(w in text for w in ["critical", "severe", "life-threatening"]):
        return "high"

    if any(w in text for w in ["abnormal", "elevated", "reduced", "concern"]):
        return "moderate"

    return "low"
    return "low"    