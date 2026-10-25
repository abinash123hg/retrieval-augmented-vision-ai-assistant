"""HTTP API routes: health, documents (upload/list/get/delete/summary) and chat.

Mounted by main.py under the /api prefix, so the public URLs are unchanged:
  GET    /api/health
  POST   /api/documents/upload
  GET    /api/documents
  GET    /api/documents/{document_id}
  DELETE /api/documents/{document_id}
  GET    /api/documents/{document_id}/summary
  POST   /api/chat
"""

from fastapi import APIRouter, BackgroundTasks, File, UploadFile

from . import ollama_service, pdf_service, rag_service, vector_store
from .config import get_settings
from .schemas import (
    ChatRequest,
    ChatResponse,
    DeleteResponse,
    DocumentListResponse,
    DocumentOut,
    HealthResponse,
    SummaryResponse,
    UploadResponse,
)

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        ollama=ollama_service.check_ollama_connection(),
        chat_model=settings.ollama_chat_model,
        embedding_model=settings.ollama_embed_model,
    )


@router.post("/documents/upload", response_model=UploadResponse, tags=["documents"])
async def upload_document(
    background_tasks: BackgroundTasks, file: UploadFile = File(...)
) -> UploadResponse:
    content = await file.read()
    document_id, _ = pdf_service.save_upload(file.filename or "unnamed", content)
    background_tasks.add_task(pdf_service.process_document, document_id)
    return UploadResponse(document_id=document_id, file_name=file.filename or "unnamed", status="processing")


@router.get("/documents", response_model=DocumentListResponse, tags=["documents"])
def list_documents() -> DocumentListResponse:
    return DocumentListResponse(documents=pdf_service.list_documents())


@router.get("/documents/{document_id}", response_model=DocumentOut, tags=["documents"])
def get_document(document_id: str) -> DocumentOut:
    return pdf_service.get_document(document_id)


@router.delete("/documents/{document_id}", response_model=DeleteResponse, tags=["documents"])
def delete_document(document_id: str) -> DeleteResponse:
    pdf_service.get_document(document_id)  # 404 if missing
    pdf_service.delete_document(document_id)
    vector_store.remove_document(document_id)
    return DeleteResponse(document_id=document_id)


@router.get("/documents/{document_id}/summary", response_model=SummaryResponse, tags=["documents"])
def summarize_document(document_id: str, mode: str = "short") -> SummaryResponse:
    if mode not in {"short", "detailed", "key_points"}:
        mode = "short"
    pdf_service.get_document(document_id)  # 404 if missing
    processed = pdf_service.load_processed_content(document_id)
    if not processed:
        return SummaryResponse(
            document_id=document_id,
            mode=mode,
            summary="This document is still being processed. Please wait until it is ready.",
        )
    summary, truncated = rag_service.summarize_document(processed, mode)
    return SummaryResponse(
        document_id=document_id,
        mode=mode,
        summary=summary,
        truncated=truncated,
        warning=(
            "This document is long; the summary covers only its first part."
            if truncated
            else None
        ),
    )


@router.post("/chat", response_model=ChatResponse, tags=["chat"])
def chat(request: ChatRequest) -> ChatResponse:
    return rag_service.answer_question(
        request.question.strip(), document_ids=request.document_ids or None
    )
