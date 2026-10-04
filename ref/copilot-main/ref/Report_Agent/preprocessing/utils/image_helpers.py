from PIL import Image


def load_image(path: str) -> Image.Image:
    """
    Loads an image file into PIL format.
    """
    img = Image.open(path)
    return img.convert("RGB")
