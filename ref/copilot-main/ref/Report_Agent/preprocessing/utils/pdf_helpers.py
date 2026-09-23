from typing import List
import fitz  # pymupdf
from PIL import Image


def pdf_to_images(pdf_path: str, dpi: int = 200) -> List[Image.Image]:
    """
    Converts a PDF into a list of PIL Images.
    """
    doc = fitz.open(pdf_path)
    images: List[Image.Image] = []

    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        mode = "RGB" if pix.alpha == 0 else "RGBA"
        img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
        images.append(img)

    doc.close()
    return images
