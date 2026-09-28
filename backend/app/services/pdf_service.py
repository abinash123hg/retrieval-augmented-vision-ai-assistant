"""Page-level text extraction from PDFs and images.

Normal text is extracted with PyMuPDF. Pages with little or no selectable
text are rendered and passed through OCR. Failed pages are recorded, never
silently dropped.
"""

from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF

from ..core.logging_config import get_logger
from . import ocr_service

logger = get_logger(__name__)

MIN_TEXT_CHARS_FOR_NATIVE = 20


@dataclass
class ExtractedPage:
    page_number: int  # 1-based
    text: str
    ocr_used: bool = False
    error: str | None = None


@dataclass
class ExtractionResult:
    pages: list[ExtractedPage] = field(default_factory=list)
    failed_pages: int = 0
    ocr_pages: int = 0

    @property
    def page_count(self) -> int:
        return len(self.pages)


def extract_pdf(path: Path) -> ExtractionResult:
    result = ExtractionResult()
    try:
        document = fitz.open(path)
    except Exception as exc:
        logger.error("Cannot open PDF %s: %s", path.name, exc)
        raise ValueError("This PDF file cannot be read. It may be corrupted or encrypted.") from exc

    with document:
        for index, page in enumerate(document):
            page_number = index + 1
            try:
                text = page.get_text("text").strip()
                ocr_used = False
                if len(text) < MIN_TEXT_CHARS_FOR_NATIVE:
                    pixmap = page.get_pixmap(dpi=200)
                    text = ocr_service.ocr_image_bytes(pixmap.tobytes("png")).strip()
                    ocr_used = True
                if ocr_used:
                    result.ocr_pages += 1
                result.pages.append(
                    ExtractedPage(page_number=page_number, text=text, ocr_used=ocr_used)
                )
            except Exception as exc:
                logger.warning("Page %s failed in %s: %s", page_number, path.name, exc)
                result.failed_pages += 1
                result.pages.append(
                    ExtractedPage(page_number=page_number, text="", error=str(exc))
                )
    return result


def extract_image(path: Path) -> ExtractionResult:
    result = ExtractionResult()
    try:
        text = ocr_service.ocr_image_file(path).strip()
        result.ocr_pages = 1
        result.pages.append(ExtractedPage(page_number=1, text=text, ocr_used=True))
    except ocr_service.OcrError as exc:
        result.failed_pages = 1
        result.pages.append(ExtractedPage(page_number=1, text="", error=str(exc)))
    return result


def extract_document(path: Path) -> ExtractionResult:
    if path.suffix.lower() == ".pdf":
        return extract_pdf(path)
    return extract_image(path)
