"""OCR for scanned pages and image uploads (Tesseract)."""

from pathlib import Path

import pytesseract
from PIL import Image

from ..config import get_settings
from ..core.logging_config import get_logger

logger = get_logger(__name__)

if get_settings().tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = get_settings().tesseract_cmd


class OcrError(Exception):
    pass


def ocr_image_bytes(image_bytes: bytes) -> str:
    from io import BytesIO

    try:
        image = Image.open(BytesIO(image_bytes)).convert("L")
        return pytesseract.image_to_string(image)
    except pytesseract.TesseractNotFoundError as exc:
        raise OcrError(
            "Tesseract OCR is not installed or not on PATH. "
            "Install it to read scanned documents."
        ) from exc
    except Exception as exc:
        raise OcrError(f"OCR failed: {exc}") from exc


def ocr_image_file(path: Path) -> str:
    try:
        image = Image.open(path).convert("L")
        return pytesseract.image_to_string(image)
    except pytesseract.TesseractNotFoundError as exc:
        raise OcrError(
            "Tesseract OCR is not installed or not on PATH. "
            "Install it to read scanned documents."
        ) from exc
    except Exception as exc:
        raise OcrError(f"OCR failed: {exc}") from exc


def is_available() -> bool:
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False
