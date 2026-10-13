"""OCR for scanned pages and image uploads (Tesseract).

Includes lightweight image preprocessing (PIL + numpy only, no extra models or
dependencies) so that black-and-white, grayscale, sepia/low-contrast, inverted
and low-resolution scans reach Tesseract in a readable form. Preprocessing only
improves the evidence text; grounding + numeric verification still gate every
answer, so the no-hallucination behaviour is unchanged.
"""

from pathlib import Path

import numpy as np
import pytesseract
from PIL import Image, ImageOps

from ..config import get_settings
from ..core.logging_config import get_logger

logger = get_logger(__name__)

if get_settings().tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = get_settings().tesseract_cmd

# Upscale small scans so text approaches ~300 DPI, which Tesseract needs.
MIN_SIDE = 1000
MAX_SIDE = 4000
# White margin around the page; Tesseract mis-segments text touching the edge.
PAD = 20


class OcrError(Exception):
    pass


# ---------------------------------------------------------------------------
# Preprocessing (pure PIL/numpy — unit-testable offline).
# ---------------------------------------------------------------------------
def to_grayscale(image: Image.Image) -> Image.Image:
    return image.convert("L")


def auto_invert(image: Image.Image) -> Image.Image:
    """Flip white-on-black scans (dark pages) to black-on-white."""
    if np.asarray(image, dtype=np.float32).mean() < 127.5:
        return ImageOps.invert(image)
    return image


def upscale(image: Image.Image) -> Image.Image:
    w, h = image.size
    side = min(w, h)
    if side >= MIN_SIDE:
        return image
    factor = min(MIN_SIDE / side, MAX_SIDE / max(w, h))
    if factor <= 1.0:
        return image
    return image.resize((int(round(w * factor)), int(round(h * factor))), Image.LANCZOS)


def _otsu_threshold(arr: np.ndarray) -> int:
    hist, _ = np.histogram(arr, bins=256, range=(0, 256))
    total = arr.size
    sum_all = float(np.dot(np.arange(256), hist))
    sum_b = 0.0
    w_b = 0
    best_t = 127
    best_var = -1.0
    for t in range(256):
        w_b += int(hist[t])
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * int(hist[t])
        mean_b = sum_b / w_b
        mean_f = (sum_all - sum_b) / w_f
        var = w_b * w_f * (mean_b - mean_f) ** 2
        if var > best_var:
            best_var = var
            best_t = t
    return best_t


def binarize(image: Image.Image) -> Image.Image:
    """Otsu threshold to crisp black ink on white paper.

    This is what rescues sepia/coloured/low-contrast backgrounds where
    Tesseract's internal thresholding fails outright.
    """
    arr = np.asarray(image, dtype=np.uint8)
    threshold = _otsu_threshold(arr)
    binary = np.where(arr > threshold, 255, 0).astype(np.uint8)
    return Image.fromarray(binary, mode="L")


def pad(image: Image.Image, border: int = PAD) -> Image.Image:
    return ImageOps.expand(image, border=border, fill=255)


def preprocess(image: Image.Image) -> Image.Image:
    """Full OCR-friendly pipeline: grayscale -> invert -> upscale -> binarize -> pad.

    (A median de-speckle step was tried and removed: combined with Otsu
    binarization it eroded thin digit strokes on re-rendered scans, turning
    '9876' into '8676'. Upscale + binarize alone give the low-contrast win
    without that regression.)
    """
    img = to_grayscale(image)
    img = auto_invert(img)
    img = upscale(img)
    img = binarize(img)
    img = pad(img)
    return img


# ---------------------------------------------------------------------------
# OCR entrypoints.
# ---------------------------------------------------------------------------
def _ocr(image: Image.Image) -> str:
    try:
        return pytesseract.image_to_string(image)
    except pytesseract.TesseractNotFoundError as exc:
        raise OcrError(
            "Tesseract OCR is not installed or not on PATH. "
            "Install it to read scanned documents."
        ) from exc
    except Exception as exc:
        raise OcrError(f"OCR failed: {exc}") from exc


def ocr_image_bytes(image_bytes: bytes) -> str:
    from io import BytesIO

    try:
        image = Image.open(BytesIO(image_bytes))
    except Exception as exc:
        raise OcrError(f"OCR failed: {exc}") from exc
    return _ocr(preprocess(image))


def ocr_image_file(path: Path) -> str:
    try:
        image = Image.open(path)
    except Exception as exc:
        raise OcrError(f"OCR failed: {exc}") from exc
    return _ocr(preprocess(image))


def is_available() -> bool:
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False
