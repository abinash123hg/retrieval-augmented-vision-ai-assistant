"""Retrieval: embed the question, search FAISS, apply score threshold."""

from ..config import get_settings
from ..core.logging_config import get_logger
from . import embedding_service, vector_store

logger = get_logger(__name__)


def retrieve(
    question: str,
    document_ids: list[str] | None = None,
    top_k: int | None = None,
    min_score: float | None = None,
) -> list[dict]:
    """Return relevant sections: [{...section, 'score': float}], best first."""
    settings = get_settings()
    top_k = top_k or settings.top_k_results
    min_score = settings.min_retrieval_score if min_score is None else min_score

    query_embedding = embedding_service.embed_query(question)
    results = vector_store.search(query_embedding, k=top_k, document_ids=document_ids)

    relevant = []
    for section, score in results:
        if score < min_score:
            continue
        relevant.append({**section, "score": round(score, 4)})
    return relevant


def build_context(sections: list[dict], max_characters: int | None = None) -> str:
    """Format retrieved sections as numbered evidence blocks within a character budget."""
    settings = get_settings()
    max_characters = max_characters or settings.max_context_characters
    blocks: list[str] = []
    used = 0
    for i, section in enumerate(sections, start=1):
        header = (
            f"[Source {i}] {section['document_name']} — page {section['page_number']}"
        )
        if section.get("section_title"):
            header += f" — {section['section_title']}"
        if section.get("content_type") == "ocr":
            header += " (OCR-derived text)"
        block = f"{header}\n{section['content']}"
        if used + len(block) > max_characters and blocks:
            break
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks)
