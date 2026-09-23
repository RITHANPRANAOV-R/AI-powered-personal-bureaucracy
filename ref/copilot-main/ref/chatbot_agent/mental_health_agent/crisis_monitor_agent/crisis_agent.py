import json
import re
from typing import Dict, Any

class CrisisMonitorAgent:
    def __init__(self, keyword_file: str):
        with open(keyword_file, "r") as f:
            self.keywords = json.load(f)

    def detect_crisis(self, text: str) -> Dict[str, Any]:
        text_clean = text.lower()
        detected_type = None
        trigger_words = []
        urgency = "low"

        # Rule-based keyword scanning
        for crisis_type, word_list in self.keywords.items():
            for word in word_list:
                if re.search(r"\b" + re.escape(word.lower()) + r"\b", text_clean):
                    detected_type = crisis_type
                    trigger_words.append(word)

        # Severity scoring logic
        severity_score = 0
        if detected_type == "self_harm":
            severity_score = 100
            urgency = "emergency"
        elif detected_type == "panic_attack":
            severity_score = 85
            urgency = "high"
        elif detected_type == "severe_anxiety":
            severity_score = 70
            urgency = "medium"
        elif detected_type == "emotional_breakdown":
            severity_score = 60
            urgency = "medium"

        crisis_detected = detected_type is not None

        # Final JSON response
        return {
            "crisis_detected": crisis_detected,
            "crisis_type": detected_type or "none",
            "trigger_keywords": trigger_words,
            "urgency": urgency,
            "severity_score": severity_score
        }
