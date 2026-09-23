import os
from typing import Dict, Any, List

from .hybrid_model_router import route_and_process
from .utils.pdf_helpers import pdf_to_images
from .utils.image_helpers import load_image
from .utils.dicom_helpers import dicom_to_images


SUPPORTED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".dcm"}


def preprocess_document(input_path: str) -> Dict[str, Any]:
    """
    Entry point for Person-1 preprocessing.
    Converts any medical file into images, routes through OCR/Vision,
    and returns structured intermediate output.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"{input_path} not found")

    ext = os.path.splitext(input_path)[1].lower()
    if ext not in SUPPORTED_EXT:
        raise ValueError(f"Unsupported file type: {ext}")

    images: List[Any] = []

    if ext == ".pdf":
        images = pdf_to_images(input_path)
    elif ext == ".dcm":
        images = dicom_to_images(input_path)
    else:
        images = [load_image(input_path)]

    if not images:
        raise RuntimeError("No images extracted from document")

    results = []
    for idx, img in enumerate(images):
        page_result = route_and_process(img, page_index=idx)
        results.append(page_result)

    return {
        "source_file": os.path.basename(input_path),
        "num_pages": len(images),
        "pages": results,
    }
