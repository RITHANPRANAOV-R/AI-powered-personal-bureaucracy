"""
OCR Abstraction and Engine Layer for User Document Understanding.
Provides clean interface for PaddleOCR with graceful fallback and mock support.
"""
import logging
from abc import ABC, abstractmethod
from typing import Tuple, Optional, List
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class OCRLine(BaseModel):
    text: str
    confidence: float = 1.0
    bbox: List[List[float]] = Field(default_factory=list)
    page_number: int = 1


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

    def extract_lines_from_image(self, image_bytes: bytes, page_number: int = 1) -> List[OCRLine]:
        """
        Extracts structured lines with bounding box metadata from image bytes.
        """
        text, conf = self.extract_text_from_image(image_bytes)
        if not text:
            return []
        lines = []
        for line in text.split("\n"):
            line_str = line.strip()
            if line_str:
                lines.append(OCRLine(text=line_str, confidence=conf, bbox=[], page_number=page_number))
        return lines


class PaddleOCREngine(BaseOCREngine):
    """
    OCR implementation supporting RapidOCR (ONNX-based PP-OCR) and PaddleOCR with graceful fallback.
    """

    def __init__(self, lang: str = "en", use_gpu: bool = False):
        self.lang = lang
        self.use_gpu = use_gpu
        self._rapid_ocr = None
        self._ocr = None
        self._is_available = False

        # 1. Try RapidOCR (ONNX-based, fast and reliable)
        try:
            from rapidocr_onnxruntime import RapidOCR
            self._rapid_ocr = RapidOCR()
            self._is_available = True
            logger.info("RapidOCR engine initialized successfully")
            return
        except Exception as e:
            logger.debug("RapidOCR is not available: %s", e)

        # 2. Try PaddleOCR as fallback
        try:
            from paddleocr import PaddleOCR
            try:
                self._ocr = PaddleOCR(use_angle_cls=True, lang=self.lang, use_gpu=self.use_gpu)
            except Exception:
                self._ocr = PaddleOCR(lang=self.lang)
            self._is_available = True
            logger.info("PaddleOCR engine initialized successfully")
        except Exception as e:
            logger.warning(f"PaddleOCR is not available or failed to initialize: {e}. OCR fallback enabled.")
            self._is_available = False

    def extract_text_from_image(self, image_bytes: bytes) -> Tuple[str, float]:
        if not self._is_available:
            logger.warning("OCR engine not active; returning empty extraction.")
            return "", 0.0

        lines = self.extract_lines_from_image(image_bytes)
        if not lines:
            return "", 0.0
        full_text = "\n".join(l.text for l in lines)
        avg_score = sum(l.confidence for l in lines) / len(lines)
        return full_text, round(avg_score, 4)

    def extract_lines_from_image(self, image_bytes: bytes, page_number: int = 1) -> List[OCRLine]:
        if not self._is_available:
            return []

        if self._rapid_ocr:
            try:
                results, _ = self._rapid_ocr(image_bytes)
                if not results:
                    return []
                ocr_lines: List[OCRLine] = []
                for item in results:
                    box = item[0]
                    text_str = str(item[1]).strip()
                    try:
                        score = float(item[2])
                    except (ValueError, TypeError):
                        score = 0.9
                    if text_str:
                        ocr_lines.append(
                            OCRLine(
                                text=text_str,
                                confidence=round(score, 4),
                                bbox=[[float(pt[0]), float(pt[1])] for pt in box] if box else [],
                                page_number=page_number,
                            )
                        )
                return ocr_lines
            except Exception as e:
                logger.error(f"Error executing RapidOCR lines extraction: {e}")
                return []

        if self._ocr:
            try:
                import io
                import numpy as np
                from PIL import Image

                img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                img_np = np.array(img)

                results = self._ocr.ocr(img_np, cls=True)
                ocr_lines: List[OCRLine] = []

                if results and results[0]:
                    for line in results[0]:
                        box = line[0]
                        text, score = line[1]
                        text_str = str(text).strip()
                        if text_str:
                            ocr_lines.append(
                                OCRLine(
                                    text=text_str,
                                    confidence=round(float(score), 4),
                                    bbox=[[float(pt[0]), float(pt[1])] for pt in box] if box else [],
                                    page_number=page_number,
                                )
                            )
                return ocr_lines
            except Exception as e:
                logger.error(f"Error executing PaddleOCR lines extraction: {e}")
                return []

        return []


class MockOCREngine(BaseOCREngine):
    """
    Deterministic Mock OCR Engine for unit testing.
    """

    def __init__(self, preset_text: str = "", preset_confidence: float = 0.95, preset_lines: Optional[List[OCRLine]] = None):
        self.preset_text = preset_text
        self.preset_confidence = preset_confidence
        self.preset_lines = preset_lines

    def extract_text_from_image(self, image_bytes: bytes) -> Tuple[str, float]:
        if not image_bytes:
            return "", 0.0
        if self.preset_lines:
            txt = "\n".join(l.text for l in self.preset_lines)
            conf = sum(l.confidence for l in self.preset_lines) / len(self.preset_lines)
            return txt, round(conf, 4)
        return self.preset_text or "GOVERNMENT OF INDIA Aadhaar Name: Ramesh Kumar DOB: 15/08/1985 Gender: MALE 1234 5678 9012", self.preset_confidence

    def extract_lines_from_image(self, image_bytes: bytes, page_number: int = 1) -> List[OCRLine]:
        if not image_bytes:
            return []
        if self.preset_lines:
            return self.preset_lines
        text, conf = self.extract_text_from_image(image_bytes)
        if not text:
            return []
        lines = []
        for l in text.split("\n"):
            l_str = l.strip()
            if l_str:
                lines.append(OCRLine(text=l_str, confidence=conf, bbox=[], page_number=page_number))
        return lines

