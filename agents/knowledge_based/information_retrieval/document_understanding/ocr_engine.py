"""
OCR Abstraction and Engine Layer for User Document Understanding.
Provides clean interface for PaddleOCR with graceful fallback and mock support.
"""
import logging
from abc import ABC, abstractmethod
from typing import Tuple, Optional, List

logger = logging.getLogger(__name__)


class BaseOCREngine(ABC):
    """Abstract base class for OCR engines."""

    @abstractmethod
    def extract_text_from_image(self, image_bytes: bytes) -> Tuple[str, float]:
        """
        Extracts text from image bytes.

        Returns:
            Tuple[extracted_text, average_confidence]
        """
        pass


class PaddleOCREngine(BaseOCREngine):
    """
    PaddleOCR implementation for user document image and scanned PDF OCR.
    """

    def __init__(self, lang: str = "en", use_gpu: bool = False):
        self.lang = lang
        self.use_gpu = use_gpu
        self._ocr = None
        self._is_available = False

        try:
            from paddleocr import PaddleOCR
            self._ocr = PaddleOCR(use_angle_cls=True, lang=self.lang, use_gpu=self.use_gpu, show_log=False)
            self._is_available = True
            logger.info("PaddleOCR engine initialized successfully")
        except Exception as e:
            logger.warning(f"PaddleOCR is not available or failed to initialize: {e}. OCR fallback enabled.")
            self._is_available = False

    def extract_text_from_image(self, image_bytes: bytes) -> Tuple[str, float]:
        if not self._is_available or not self._ocr:
            logger.warning("PaddleOCR engine not active; returning empty extraction.")
            return "", 0.0

        try:
            import io
            import numpy as np
            from PIL import Image

            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img_np = np.array(img)

            results = self._ocr.ocr(img_np, cls=True)

            extracted_lines: List[str] = []
            scores: List[float] = []

            if results and results[0]:
                for line in results[0]:
                    text, score = line[1]
                    extracted_lines.append(text)
                    scores.append(float(score))

            full_text = "\n".join(extracted_lines)
            avg_score = sum(scores) / len(scores) if scores else 0.0
            return full_text, round(avg_score, 4)

        except Exception as e:
            logger.error(f"Error executing PaddleOCR on image bytes: {e}")
            return "", 0.0


class MockOCREngine(BaseOCREngine):
    """
    Deterministic Mock OCR Engine for unit testing.
    """

    def __init__(self, preset_text: str = "", preset_confidence: float = 0.95):
        self.preset_text = preset_text
        self.preset_confidence = preset_confidence

    def extract_text_from_image(self, image_bytes: bytes) -> Tuple[str, float]:
        if not image_bytes:
            return "", 0.0
        return self.preset_text or "GOVERNMENT OF INDIA Aadhaar Name: Ramesh Kumar DOB: 15/08/1985 Gender: MALE 1234 5678 9012", self.preset_confidence
