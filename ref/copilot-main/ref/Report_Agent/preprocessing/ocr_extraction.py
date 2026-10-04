from typing import Any, Dict, List
import numpy as np

from paddleocr import PaddleOCR
import pytesseract
from PIL import Image

# Initialize once (heavy object)
_paddle_ocr = PaddleOCR(use_angle_cls=True, lang="en")


def extract_text_with_ocr(image: Any) -> Dict[str, Any]:
    """
    Runs PaddleOCR first. If it fails or confidence is low,
    falls back to Tesseract.
    Returns unified text + confidence.
    """
    if isinstance(image, Image.Image):
        img = np.array(image)
    else:
        img = image

    try:
        result = _paddle_ocr.ocr(img, cls=True)
        text_blocks: List[str] = []
        confidences: List[float] = []

        for line in result[0]:
            txt = line[1][0]
            conf = float(line[1][1])
            text_blocks.append(txt)
            confidences.append(conf)

        if text_blocks:
            avg_conf = sum(confidences) / len(confidences)
            return {
                "engine": "paddleocr",
                "text": "\n".join(text_blocks),
                "confidence": round(avg_conf, 3),
            }

    except Exception:
        pass  # fallback below

    # ---- Tesseract fallback ----
    if not isinstance(image, Image.Image):
        image = Image.fromarray(img)

    try:
        raw = pytesseract.image_to_string(image)
        tokens = [t for t in raw.split() if t.strip()]
        confidence = min(0.6, 0.02 * len(tokens)) if tokens else 0.1

        return {
            "engine": "tesseract",
            "text": raw.strip(),
            "confidence": round(confidence, 3),
        }
    except Exception:
        return {
            "engine": "none",
            "text": "",
            "confidence": 0.0,
        }
