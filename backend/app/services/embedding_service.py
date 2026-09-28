"""Embedding creation through Ollama (nomic-embed-text via /api/embed)."""

from ..core.logging_config import get_logger
from . import ollama_service

logger = get_logger(__name__)

BATCH_SIZE = 16


def embed_texts(texts: list[str]) -> list[list[float]]:
    embeddings: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        embeddings.extend(ollama_service.create_embeddings(batch))
    return embeddings


def embed_query(question: str) -> list[float]:
    return ollama_service.create_embedding(question)
