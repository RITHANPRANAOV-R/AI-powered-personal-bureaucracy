"""
Risk Detection Agent for Medical Chatbot
"""
from google.adk.agents.llm_agent import LlmAgent
from pydantic import BaseModel
from .schemas import RiskAssessment, RiskSignal
from .rules import ESCALATION_LEVELS


# ----------------------------
# Prompt Loader
# ----------------------------
def load_prompt(filename):
    """Load prompt from prompts directory"""
    try:
        with open(f"prompts/{filename}", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


# ----------------------------
# Deterministic Risk Engine
# ----------------------------
class RiskDetectionAgent:
    """
    RiskDetectionAgent

    Role:
        Acts as a medical safety sentinel inside an agentic medical system.

    Responsibilities:
        - Analyze user text for safety risks:
            * Self-harm or suicide ideation
            * Abuse or violence
            * Severe mental health crisis
            * Medical emergencies
        - Extract explicit or implicit danger signals
        - Assign a calibrated risk level:
            none | low | medium | high | critical
        - Decide whether the situation requires escalation

    Behavior Principles:
        - Be conservative: when in doubt, lean toward safety
        - Do not hallucinate intent; rely on linguistic evidence
        - Escalate only when severity warrants it
        - Never provide advice; only assess risk
    """

    name = "risk_detection_agent"
    description = (
        "Detects self-harm, suicide risk, abuse, crisis states, "
        "and medical emergencies in user messages and produces "
        "a structured safety assessment for the Root Agent."
    )

    def analyze(self, text: str) -> RiskAssessment:
        signals = []
        lowered = text.lower()

        # Self-harm / suicide
        if any(k in lowered for k in ["kill myself", "suicide", "end my life", "want to die"]):
            signals.append(
                RiskSignal(
                    category="self_harm",
                    evidence=text,
                    severity=9,
                )
            )

        # Abuse / violence
        if any(k in lowered for k in ["hurt me", "abuse", "he hits me", "she beats me"]):
            signals.append(
                RiskSignal(
                    category="abuse",
                    evidence=text,
                    severity=7,
                )
            )

        # Medical emergencies
        if any(k in lowered for k in ["chest pain", "can't breathe", "collapsed", "unconscious"]):
            signals.append(
                RiskSignal(
                    category="medical_emergency",
                    evidence=text,
                    severity=8,
                )
            )

        if not signals:
            return RiskAssessment(
                risk_level="none",
                summary="No risk indicators detected.",
                signals=[],
                requires_escalation=False,
            )

        max_severity = max(s.severity for s in signals)

        if max_severity >= 9:
            level = "critical"
        elif max_severity >= 7:
            level = "high"
        elif max_severity >= 4:
            level = "medium"
        else:
            level = "low"

        return RiskAssessment(
            risk_level=level,
            summary=f"Detected {len(signals)} risk signal(s) requiring safety awareness.",
            signals=signals,
            requires_escalation=level in ESCALATION_LEVELS,
        )


# ----------------------------
# ADK LLM Agent (exposed entrypoint)
# ----------------------------
root_agent = LlmAgent(
    name="risk_detection_agent",
    model="gemini-2.0-flash",
    description="""
    Agent responsible for identifying safety risks in user messages.
    """,
    instruction=load_prompt("system_prompt.txt"),
    # REMOVE output_schema
)

