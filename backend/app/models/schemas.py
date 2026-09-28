from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ProcessingStatus = Literal[
    "waiting", "processing", "ready", "partially_processed", "failed"
]
EvidenceStatus = Literal[
    "supported", "partially_supported", "not_found", "conflicting_sources", "low_quality_source"
]


class HealthResponse(BaseModel):
    status: str = "ok"
    ollama: bool
    chat_model: str
    embedding_model: str


class DocumentOut(BaseModel):
    id: str
    file_name: str
    file_type: str
    file_size: int
    page_count: int = 0
    upload_time: datetime
    processing_status: ProcessingStatus = "waiting"
    error_message: str | None = None
    ocr_pages: int = 0
    failed_pages: int = 0


class DocumentListResponse(BaseModel):
    documents: list[DocumentOut]


class UploadResponse(BaseModel):
    document_id: str
    file_name: str
    status: str


class DeleteResponse(BaseModel):
    status: str = "deleted"
    document_id: str


class SourceOut(BaseModel):
    document_name: str
    page_number: int
    section: str | None = None
    excerpt: str
    score: float = 0.0


class VerificationOut(BaseModel):
    passed: bool = True
    warnings: list[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    document_ids: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    evidence_status: EvidenceStatus = "not_found"
    sources: list[SourceOut] = Field(default_factory=list)
    verification: VerificationOut = Field(default_factory=VerificationOut)
    created_at: datetime


class ReportRequest(BaseModel):
    question: str
    answer: str
    evidence_status: EvidenceStatus = "not_found"
    sources: list[SourceOut] = Field(default_factory=list)


class ReportResponse(BaseModel):
    report_id: str
    file_name: str
    download_url: str


class SummaryResponse(BaseModel):
    document_id: str
    mode: str
    summary: str
