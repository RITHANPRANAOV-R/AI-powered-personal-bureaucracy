# formatters.py
def add_empathy(text: str, mode: str) -> str:
    if mode == "urgent":
        return "I’m really concerned about what you’re describing. " + text
    if mode == "supportive":
        return "I know this can be scary, but I’m here to help you through this. " + text
    if mode == "empathetic":
        return "I’m sorry you’re going through this. " + text
    return text
