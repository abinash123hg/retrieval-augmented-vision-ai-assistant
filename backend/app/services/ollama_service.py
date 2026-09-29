"""Ollama client: connection check, embeddings, generation.

Uses the exact model names from settings; never switches models silently.
"""

import httpx

from ..config import get_settings
from ..core.errors import OllamaModelMissingError, OllamaUnavailableError
from ..core.logging_config import get_logger

logger = get_logger(__name__)

TIMEOUT_EMBED = 60.0
TIMEOUT_GENERATE = 180.0


def check_ollama_connection() -> bool:
    settings = get_settings()
    try:
        response = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=5.0)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def list_models() -> list[str]:
    settings = get_settings()
    try:
        response = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=5.0)
        response.raise_for_status()
        return [m.get("name", "") for m in response.json().get("models", [])]
    except httpx.HTTPError:
        return []


def ensure_models_available() -> None:
    settings = get_settings()
    if not check_ollama_connection():
        raise OllamaUnavailableError()
    available = list_models()
    for model in (settings.ollama_chat_model, settings.ollama_embed_model):
        if model not in available:
            logger.error("Ollama model missing: %s (available: %s)", model, available)
            raise OllamaModelMissingError()


def create_embedding(text: str) -> list[float]:
    return create_embeddings([text])[0]


def create_embeddings(texts: list[str]) -> list[list[float]]:
    settings = get_settings()
    if not texts:
        return []
    payload = {"model": settings.ollama_embed_model, "input": texts}
    try:
        response = httpx.post(
            f"{settings.ollama_base_url}/api/embed", json=payload, timeout=TIMEOUT_EMBED
        )
        response.raise_for_status()
        embeddings = response.json().get("embeddings")
        if not embeddings or len(embeddings) != len(texts):
            raise OllamaUnavailableError(detail="Unexpected embedding response shape")
        return embeddings
    except httpx.HTTPError as exc:
        logger.error("Embedding request failed: %s", exc)
        raise OllamaUnavailableError(
            "Could not create embeddings. Please check that Ollama is running."
        ) from exc


def generate_answer(prompt: str, system: str | None = None) -> str:
    settings = get_settings()
    payload = {
        "model": settings.ollama_chat_model,
        "prompt": prompt,
        "stream": False,
        # Deterministic settings: grounded answers must not drift.
        "options": {"temperature": 0.0, "top_p": 0.1, "num_predict": 1024},
    }
    if system:
        payload["system"] = system
    try:
        response = httpx.post(
            f"{settings.ollama_base_url}/api/generate", json=payload, timeout=TIMEOUT_GENERATE
        )
        response.raise_for_status()
        return response.json().get("response", "").strip()
    except httpx.HTTPError as exc:
        logger.error("Generation request failed: %s", exc)
        raise OllamaUnavailableError(
            "Could not generate an answer. Please check that Ollama is running."
        ) from exc
