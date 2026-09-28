"""Document registry (JSON-backed) and upload storage."""

import json
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..config import get_settings
from ..core.errors import DocumentNotFoundError, InvalidFileError
from ..core.logging_config import get_logger
from ..core.security import is_within_directory, sanitize_filename
from ..models.schemas import DocumentOut

logger = get_logger(__name__)

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
        from ..core.errors import FileTooLargeError

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


def process_document(document_id: str) -> None:
    """Full processing pipeline for one uploaded document.

    extract → tables → chunk → embed → index. Failures mark the document but
    never crash the app; partially failed pages keep processing going.
    """
    from . import chunk_service, embedding_service, pdf_service, table_service, vector_store

    update_document(document_id, processing_status="processing")
    try:
        path = stored_file_path(document_id)
        record = get_document(document_id)

        extraction = pdf_service.extract_document(path)
        tables = table_service.extract_tables(path) if path.suffix.lower() == ".pdf" else []

        pages = [
            {
                "page_number": p.page_number,
                "text": p.text,
                "ocr_used": p.ocr_used,
                "error": p.error,
            }
            for p in extraction.pages
        ]
        sections = chunk_service.chunk_pages(
            document_id, record.file_name, pages, tables
        )

        if sections:
            embeddings = embedding_service.embed_texts([s["content"] for s in sections])
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
        update_document(
            document_id,
            processing_status="failed",
            error_message="This file could not be processed. Please try uploading it again.",
        )
