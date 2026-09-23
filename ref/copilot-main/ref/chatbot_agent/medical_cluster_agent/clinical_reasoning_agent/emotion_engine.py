def detect_emotion_context(state):
    if "chest pain" in str(state).lower():
        return "urgent"
    if "cancer" in str(state).lower():
        return "supportive"
    if "pain" in str(state).lower():
        return "empathetic"
    return "neutral"
