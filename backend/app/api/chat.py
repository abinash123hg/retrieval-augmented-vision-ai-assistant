from fastapi import APIRouter

from ..core.logging_config import get_logger
from ..models.schemas import ChatRequest, ChatResponse
from ..services import answer_service

logger = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    return answer_service.answer_question(
        request.question.strip(), document_ids=request.document_ids or None
    )
