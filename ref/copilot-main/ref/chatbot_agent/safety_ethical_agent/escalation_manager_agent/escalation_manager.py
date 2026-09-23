class EscalationManager:
    def decide(self, inputs):
        risk = inputs["risk_detection"]
        safety = inputs["medical_safety"]
        user = inputs["user_context"]

        if safety["is_safe_to_answer"] is False:
            return {
                "escalation_level": "0",
                "action": "refuse",
                "message_type": "refusal",
                "final_user_message": f"I can’t help with that because it may be unsafe. {safety['unsafe_reason']}"
            }

        if "self-harm" in user.get("crisis_indicators", []):
            return {
                "escalation_level": "5",
                "action": "crisis_support",
                "message_type": "crisis_support",
                "final_user_message": (
                    "I'm here for you. If you feel you're in immediate danger, "
                    "please contact your local emergency number or a suicide hotline."
                )
            }

        if risk["risk_level"] == "critical":
            return {
                "escalation_level": "4",
                "action": "emergency",
                "message_type": "emergency",
                "final_user_message": (
                    "Your symptoms may indicate an emergency. Seek immediate medical care."
                )
            }

        if risk["risk_level"] == "high":
            return {
                "escalation_level": "3",
                "action": "urgent_doctor",
                "message_type": "warning",
                "final_user_message": (
                    "These symptoms could be serious. You should see a doctor urgently."
                )
            }

        if risk["risk_level"] == "medium":
            return {
                "escalation_level": "2",
                "action": "caution",
                "message_type": "caution",
                "final_user_message": (
                    "Some symptoms are concerning. Monitor closely and consider seeing a doctor if worsened."
                )
            }

        return {
            "escalation_level": "1",
            "action": "safe_guidance",
            "message_type": "instruction",
            "final_user_message": (
                "It seems non-urgent. I can offer general guidance but this is not a diagnosis."
            )
        }
