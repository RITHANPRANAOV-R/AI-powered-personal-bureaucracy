from typing import Any, Dict

from .ocr_extraction import extract_text_with_ocr
from .gpt4o_vision_interface import analyze_image_with_vision


OCR_CONF_THRESHOLD = 0.65


def route_and_process(image: Any, page_index: int = 0) -> Dict[str, Any]:
    """
    Hybrid router:
    1. Run OCR (Paddle -> Tesseract fallback)
    2. If OCR confidence is high, pass text + image to GPT-4o-mini
    3. If low confidence or complex scan, upgrade to GPT-4o
    """

    ocr_result = extract_text_with_ocr(image)
    text = ocr_result["text"]
    confidence = ocr_result["confidence"]

    use_big_model = confidence < OCR_CONF_THRESHOLD or _looks_like_scan(text)

    model = "gemini-2.5-flash" if use_big_model else "gemini-2.0-flash"


    vision_result = analyze_image_with_vision(
        image=image,
        extracted_text=text,
        model=model,
        page_index=page_index,
    )

    return {
        "page_index": page_index,
        "ocr_confidence": confidence,
        "model_used": model,
        "ocr_text": text,
        "vision_analysis": vision_result,
    }


def _looks_like_scan(text: str) -> bool:
    """
    Heuristic: radiology scans usually have very little readable text.
    """
    if not text:
        return True
    tokens = text.strip().split()
    return len(tokens) < 20
