from fastapi import APIRouter

from ..config import get_settings
from ..models.schemas import HealthResponse
from ..services import ollama_service

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        ollama=ollama_service.check_ollama_connection(),
        chat_model=settings.ollama_chat_model,
        embedding_model=settings.ollama_embed_model,
    )
