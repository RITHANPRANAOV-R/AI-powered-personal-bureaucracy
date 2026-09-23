from typing import List
import numpy as np
import pydicom
from PIL import Image


def dicom_to_images(dicom_path: str) -> List[Image.Image]:
    """
    Converts a DICOM file into one or more PIL Images.
    Handles single-frame and multi-frame DICOMs.
    """
    ds = pydicom.dcmread(dicom_path)
    pixel_array = ds.pixel_array

    images: List[Image.Image] = []

    if pixel_array.ndim == 2:
        images.append(_normalize_to_image(pixel_array))
    elif pixel_array.ndim == 3:
        for frame in pixel_array:
            images.append(_normalize_to_image(frame))
    else:
        raise ValueError("Unsupported DICOM pixel format")

    return images


def _normalize_to_image(arr: np.ndarray) -> Image.Image:
    arr = arr.astype("float32")
    arr -= arr.min()
    arr /= max(arr.max(), 1e-6)
    arr *= 255.0
    arr = arr.astype("uint8")
    return Image.fromarray(arr).convert("RGB")
