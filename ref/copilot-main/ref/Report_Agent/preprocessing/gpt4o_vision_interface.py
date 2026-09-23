import io
from typing import Any, Dict
from PIL import Image
import google.generativeai as genai

# Make sure your GEMINI_API_KEY is set in environment
# setx GEMINI_API_KEY "your_key_here"

genai.configure(api_key=None)  # ADK injects automatically

def analyze_image_with_vision(
    image: Any,
    extracted_text: str,
    model: str,
    page_index: int,
) -> Dict[str, Any]:
    """
    Uses Gemini Vision (flash/pro) to analyze medical images.
    """

    if not isinstance(image, Image.Image):
        image = Image.fromarray(image)

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    system_prompt = (
        "You are a medical document analysis engine. "
        "Given an image of a medical report or scan and optional OCR text, "
        "extract all clinically relevant information. "
        "Be factual. Do not diagnose. Return JSON only."
    )

    user_prompt = f"""
Page: {page_index}

OCR Text (may be noisy):
\"\"\"{extracted_text}\"\"\"

Return JSON with:
- document_type
- key_findings
- detected_fields
- any_warnings_about_quality
"""

    gemini_model = genai.GenerativeModel(model)

    response = gemini_model.generate_content(
        [
            system_prompt,
            user_prompt,
            {"mime_type": "image/png", "data": img_bytes},
        ],
        generation_config={"temperature": 0.2},
    )

    # Gemini may wrap JSON in markdown; strip it safely
    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]

    import json
    return json.loads(text)
