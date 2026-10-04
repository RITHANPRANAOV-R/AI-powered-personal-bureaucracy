"""
Interpretation Pipeline for medical report text.
"""

import json
from google.adk.agents.llm_agent import LlmAgent
from google.adk.runners import Runner
from .utils.risk_classifier import classify_risk
from .utils.prompts.lab_report_prompt import lab_report_prompt
from .utils.prompts.radiology_report_prompt import radiology_report_prompt
from .utils.prompts.doctor_report_prompt import doctor_report_prompt


# LLM used for interpretation
interpretation_agent = LlmAgent(
    name="interpretation_llm_model",
    model="gemini-2.5-flash",
    description="LLM used for report interpretation",
    instruction="""
You are the Medical Report Analysis Agent.

Your task is to analyze and explain a user-provided medical report,
which originates from a licensed healthcare professional.

RESPONSIBILITIES:
- Summarize the report clearly and accurately.
- Explain medical terms in simple, patient-friendly language.
- Highlight important findings or abnormal values.
- Output JSON only in the following format:
{
  "report_summary": "...",
  "key_findings": "...",
  "simplified_explanation": "...",
  "important_notes": "...",
  "when_to_seek_medical_attention": "..."
}

LIMITATIONS:
- Do NOT diagnose diseases.
- Do NOT recommend treatments or medications.
- Do NOT reinterpret professional conclusions.
- Do NOT introduce information not present in the report.

SAFETY RULES:
- Advise prompt consultation if critical indicators are detected.
- Maintain a neutral, factual, supportive tone.
- Include appropriate disclaimers.
- All outputs must pass Safety & Ethics Guards.

Return ONLY the JSON object, no additional text.
""",
)


def detect_report_type(text: str):
    t = text.lower()

    lab_keywords = ["hemoglobin", "wbc", "cbc", "platelet", "glucose", "serum"]
    radiology_keywords = ["x-ray", "ct", "mri", "imaging", "scan", "radiograph"]

    if any(k in t for k in lab_keywords):
        return "lab"
    if any(k in t for k in radiology_keywords):
        return "radiology"
    return "doctor"


def interpret_document(text: str):
    report_type = detect_report_type(text)

    # Select prompt
    if report_type == "lab":
        sys_prompt = lab_report_prompt
    elif report_type == "radiology":
        sys_prompt = radiology_report_prompt
    else:
        sys_prompt = doctor_report_prompt

    # Create runner only when needed (not at module import time)
    runner = Runner(
        agent=interpretation_agent,
        app_name="report_interpreter"
    )

    # Run model using runner
    response = runner.run(
        user_id="user1",
        session_id="session1",
        text=sys_prompt + "\n\nPlease interpret the following report:\n" + text
    )

    # Collect all content from the response
    response_parts = []
    for event in response:
        if hasattr(event, 'content') and hasattr(event.content, 'parts'):
            for part in event.content.parts:
                if hasattr(part, 'text'):
                    response_parts.append(part.text)
    
    full_response = "".join(response_parts).strip() if response_parts else ""

    # Try to parse JSON from the response
    try:
        # Extract JSON if it's wrapped in markdown code blocks
        if "```json" in full_response:
            json_start = full_response.find("```json") + 7
            json_end = full_response.find("```", json_start)
            json_str = full_response[json_start:json_end].strip()
        elif "```" in full_response:
            json_start = full_response.find("```") + 3
            json_end = full_response.find("```", json_start)
            json_str = full_response[json_start:json_end].strip()
        else:
            # Try to find JSON object in the response
            json_start = full_response.find("{")
            json_end = full_response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = full_response[json_start:json_end]
            else:
                json_str = full_response
        
        result = json.loads(json_str)
        
        # Ensure all required fields are present
        required_fields = {
            "report_summary": "",
            "key_findings": "",
            "simplified_explanation": "",
            "important_notes": "",
            "when_to_seek_medical_attention": ""
        }
        
        for field in required_fields:
            if field not in result:
                result[field] = required_fields[field]
        
        return result
        
    except (json.JSONDecodeError, ValueError):
        # If JSON parsing fails, create a structured response from the text
        risk_level = classify_risk(full_response)
        
        # Extract key information from the response text
        return {
            "report_summary": full_response[:500] if len(full_response) > 500 else full_response,
            "key_findings": "Please review the report summary above for key findings.",
            "simplified_explanation": "The report has been analyzed. Please consult with a healthcare professional for detailed explanation.",
            "important_notes": f"Risk level detected: {risk_level}. This analysis is for informational purposes only and does not replace professional medical advice.",
            "when_to_seek_medical_attention": "If you have concerns about your report, please consult with your healthcare provider. Seek immediate medical attention if you experience any urgent symptoms."
        }


__all__ = ["interpret_document"]

