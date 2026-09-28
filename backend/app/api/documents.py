from fastapi import APIRouter, BackgroundTasks, File, UploadFile

from ..core.logging_config import get_logger
from ..models.schemas import (
    DeleteResponse,
    DocumentListResponse,
    DocumentOut,
    SummaryResponse,
    UploadResponse,
)
from ..services import answer_service, file_service, vector_store

logger = get_logger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks, file: UploadFile = File(...)
) -> UploadResponse:
    content = await file.read()
    document_id, _ = file_service.save_upload(file.filename or "unnamed", content)
    background_tasks.add_task(file_service.process_document, document_id)
    return UploadResponse(document_id=document_id, file_name=file.filename or "unnamed", status="processing")


@router.get("", response_model=DocumentListResponse)
def list_documents() -> DocumentListResponse:
    return DocumentListResponse(documents=file_service.list_documents())


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: str) -> DocumentOut:
    return file_service.get_document(document_id)


@router.delete("/{document_id}", response_model=DeleteResponse)
def delete_document(document_id: str) -> DeleteResponse:
    file_service.get_document(document_id)  # 404 if missing
    file_service.delete_document(document_id)
    vector_store.remove_document(document_id)
    return DeleteResponse(document_id=document_id)


@router.get("/{document_id}/summary", response_model=SummaryResponse)
def summarize_document(document_id: str, mode: str = "short") -> SummaryResponse:
    if mode not in {"short", "detailed", "key_points"}:
        mode = "short"
    file_service.get_document(document_id)  # 404 if missing
    processed = file_service.load_processed_content(document_id)
    if not processed:
        return SummaryResponse(
            document_id=document_id,
            mode=mode,
            summary="This document is still being processed. Please wait until it is ready.",
        )
    summary = answer_service.summarize_document(processed, mode)
    return SummaryResponse(document_id=document_id, mode=mode, summary=summary)
