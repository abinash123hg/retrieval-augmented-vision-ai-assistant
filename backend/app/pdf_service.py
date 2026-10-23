"""Document ingestion: upload storage, PDF/image text extraction, OCR, tables.

This module consolidates everything that turns an uploaded file into indexed,
searchable page text. Behaviour is unchanged:

- Uploads are validated (extension, non-empty, size), sanitized and stored under a
  random id; a JSON registry tracks each document's processing state.
- Native PDF text is extracted with PyMuPDF; pages with little or no selectable text
  are rendered at 200 DPI and passed through Tesseract OCR. Failed pages are
  recorded, never silently dropped.
- OCR preprocessing (PIL + numpy only) rescues black-and-white, grayscale,
  sepia/low-contrast, inverted and low-resolution scans. It only improves the
  evidence text; grounding + numeric verification still gate every answer.
- Tables are extracted with pdfplumber and stored as separate sections.
"""

import json
import logging
import re
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
import pytesseract
from PIL import Image, ImageOps

from .config import get_settings
from .main import DocumentNotFoundError, FileTooLargeError, InvalidFileError
from .schemas import DocumentOut

logger = logging.getLogger(__name__)

if get_settings().tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = get_settings().tesseract_cmd


# ---------------------------------------------------------------------------
# Input safety: filename sanitization and path containment.
# ---------------------------------------------------------------------------
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(filename: str) -> str:
    name = Path(filename).name
    name = _SAFE_NAME.sub("_", name).strip("._")
    return name or "unnamed"


def is_within_directory(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# OCR for scanned pages and image uploads (Tesseract).
# ---------------------------------------------------------------------------
# Upscale small scans so text approaches ~300 DPI, which Tesseract needs.
MIN_SIDE = 1000
MAX_SIDE = 4000
# White margin around the page; Tesseract mis-segments text touching the edge.
PAD = 20


class OcrError(Exception):
    pass


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


# ---------------------------------------------------------------------------
# Page-level text extraction from PDFs and images.
# ---------------------------------------------------------------------------
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
                    text = ocr_image_bytes(pixmap.tobytes("png")).strip()
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
        text = ocr_image_file(path).strip()
        result.ocr_pages = 1
        result.pages.append(ExtractedPage(page_number=1, text=text, ocr_used=True))
    except OcrError as exc:
        result.failed_pages = 1
        result.pages.append(ExtractedPage(page_number=1, text="", error=str(exc)))
    return result


def extract_document(path: Path) -> ExtractionResult:
    if path.suffix.lower() == ".pdf":
        return extract_pdf(path)
    return extract_image(path)


# ---------------------------------------------------------------------------
# Basic table extraction from PDFs using pdfplumber.
#
# Tables are converted to markdown-like text and stored as separate sections
# with their page numbers. Failures on a page are logged and skipped.
# ---------------------------------------------------------------------------
def _table_to_text(table: list[list]) -> str:
    rows = []
    for row in table:
        cells = [(c or "").replace("\n", " ").strip() for c in row]
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def extract_tables(path: Path) -> list[dict]:
    """Return [{'page_number': int, 'content': str, 'index': int}, ...]."""
    tables_found: list[dict] = []
    try:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            for page_index, page in enumerate(pdf.pages):
                page_number = page_index + 1
                try:
                    for table_index, table in enumerate(page.extract_tables()):
                        text = _table_to_text(table)
                        if len(text.strip()) > 20:
                            tables_found.append(
                                {
                                    "page_number": page_number,
                                    "content": text,
                                    "index": table_index,
                                }
                            )
                except Exception as exc:
                    logger.warning("Table extraction failed on page %s: %s", page_number, exc)
    except Exception as exc:
        logger.warning("pdfplumber could not open %s: %s", path.name, exc)
    return tables_found


# ---------------------------------------------------------------------------
# Document registry (JSON-backed), upload storage and processing pipeline.
# ---------------------------------------------------------------------------
_lock = threading.Lock()


def _registry_path() -> Path:
    return get_settings().processed_path / "documents.json"


def _load_registry() -> dict[str, dict]:
    path = _registry_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Document registry unreadable, starting fresh: %s", exc)
        return {}


def _save_registry(registry: dict[str, dict]) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(registry, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def list_documents() -> list[DocumentOut]:
    with _lock:
        registry = _load_registry()
    docs = [DocumentOut(**d) for d in registry.values()]
    docs.sort(key=lambda d: d.upload_time, reverse=True)
    return docs


def get_document(document_id: str) -> DocumentOut:
    with _lock:
        registry = _load_registry()
    if document_id not in registry:
        raise DocumentNotFoundError()
    return DocumentOut(**registry[document_id])


def update_document(document_id: str, **fields) -> DocumentOut:
    with _lock:
        registry = _load_registry()
        if document_id not in registry:
            raise DocumentNotFoundError()
        registry[document_id].update(fields)
        _save_registry(registry)
        return DocumentOut(**registry[document_id])


def save_upload(file_name: str, content: bytes) -> tuple[str, Path]:
    """Validate and store an uploaded file. Returns (document_id, stored_path)."""
    settings = get_settings()
    safe_name = sanitize_filename(file_name)
    extension = Path(safe_name).suffix.lower()
    if extension not in {".pdf", ".png", ".jpg", ".jpeg"}:
        raise InvalidFileError(
            f"'{Path(file_name).suffix or file_name}' is not supported. "
            "Please upload a PDF, PNG or JPG file."
        )
    if not content:
        raise InvalidFileError("This file is empty. Please upload a file with content.")
    if len(content) > settings.max_file_size_bytes:
        raise FileTooLargeError(
            f"This file exceeds the maximum size of {settings.max_file_size_mb} MB."
        )

    document_id = uuid.uuid4().hex
    stored_path = settings.upload_path / f"{document_id}{extension}"
    stored_path.write_bytes(content)

    file_type = "pdf" if extension == ".pdf" else "image"
    record = {
        "id": document_id,
        "file_name": safe_name,
        "file_type": file_type,
        "file_size": len(content),
        "page_count": 0,
        "upload_time": datetime.now(timezone.utc).isoformat(),
        "processing_status": "waiting",
        "error_message": None,
        "ocr_pages": 0,
        "failed_pages": 0,
        "stored_path": str(stored_path),
    }
    with _lock:
        registry = _load_registry()
        registry[document_id] = record
        _save_registry(registry)
    return document_id, stored_path


def stored_file_path(document_id: str) -> Path:
    settings = get_settings()
    with _lock:
        registry = _load_registry()
    record = registry.get(document_id)
    if not record:
        raise DocumentNotFoundError()
    path = Path(record["stored_path"])
    if not is_within_directory(path, settings.upload_path) or not path.exists():
        raise DocumentNotFoundError("The stored file for this document is missing.")
    return path


def delete_document(document_id: str) -> None:
    settings = get_settings()
    with _lock:
        registry = _load_registry()
        record = registry.pop(document_id, None)
        _save_registry(registry)
    if record is None:
        raise DocumentNotFoundError()
    stored = Path(record.get("stored_path", ""))
    if is_within_directory(stored, settings.upload_path) and stored.exists():
        stored.unlink()
    processed = settings.processed_path / f"{document_id}.json"
    if processed.exists():
        processed.unlink()


def save_processed_content(document_id: str, data: dict) -> Path:
    settings = get_settings()
    path = settings.processed_path / f"{document_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_processed_content(document_id: str) -> dict | None:
    path = get_settings().processed_path / f"{document_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def clear_all() -> None:
    """Remove every document and its stored data (used by tests)."""
    settings = get_settings()
    for doc in list_documents():
        try:
            delete_document(doc.id)
        except Exception:  # keep cleanup best-effort
            pass
    shutil.rmtree(settings.index_path, ignore_errors=True)
    settings.index_path.mkdir(parents=True, exist_ok=True)


def recover_interrupted_documents() -> int:
    """Mark documents left in waiting/processing as failed after a restart.

    A server crash mid-pipeline would otherwise leave a document stuck forever,
    with the frontend polling an unfinished state. Returns how many were reset.
    """
    with _lock:
        registry = _load_registry()
        stale = [
            doc_id
            for doc_id, record in registry.items()
            if record.get("processing_status") in {"waiting", "processing"}
        ]
        for doc_id in stale:
            registry[doc_id]["processing_status"] = "failed"
            registry[doc_id]["error_message"] = (
                "Processing was interrupted. Please upload the file again."
            )
        if stale:
            _save_registry(registry)
    if stale:
        logger.info("Recovered %d interrupted document(s) on startup.", len(stale))
    return len(stale)


def process_document(document_id: str) -> None:
    """Full processing pipeline for one uploaded document.

    extract -> tables -> chunk -> embed -> index. Failures mark the document but
    never crash the app; partially failed pages keep processing going.
    """
    from . import rag_service, vector_store

    update_document(document_id, processing_status="processing")
    try:
        path = stored_file_path(document_id)
        record = get_document(document_id)

        extraction = extract_document(path)
        tables = extract_tables(path) if path.suffix.lower() == ".pdf" else []

        pages = [
            {
                "page_number": p.page_number,
                "text": p.text,
                "ocr_used": p.ocr_used,
                "error": p.error,
            }
            for p in extraction.pages
        ]
        sections = rag_service.chunk_pages(
            document_id, record.file_name, pages, tables
        )

        if sections:
            embeddings = rag_service.embed_texts([s["content"] for s in sections])
            vector_store.add_sections(sections, embeddings)

        save_processed_content(
            document_id,
            {
                "document_id": document_id,
                "file_name": record.file_name,
                "pages": pages,
                "tables": tables,
                "sections": sections,
            },
        )

        has_text = any(p.text.strip() for p in extraction.pages)
        if extraction.failed_pages and has_text:
            status = "partially_processed"
        elif has_text:
            status = "ready"
        else:
            status = "failed"
        error_message = None
        if status == "failed":
            first_error = next((p.error for p in extraction.pages if p.error), None)
            error_message = first_error or (
                "No readable text was found in this file. If it is a scan, check that Tesseract OCR is installed."
            )
        update_document(
            document_id,
            processing_status=status,
            page_count=extraction.page_count,
            ocr_pages=extraction.ocr_pages,
            failed_pages=extraction.failed_pages,
            error_message=error_message,
        )
    except Exception as exc:
        logger.error("Processing failed for %s: %s", document_id, exc)
        try:
            update_document(
                document_id,
                processing_status="failed",
                error_message="This file could not be processed. Please try uploading it again.",
            )
        except DocumentNotFoundError:
            # The document was deleted while it was being processed; nothing to mark.
            logger.info("Document %s was removed during processing.", document_id)
