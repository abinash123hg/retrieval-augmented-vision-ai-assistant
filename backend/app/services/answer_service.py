"""Grounded answer generation.

Pipeline: retrieve evidence → prompt Ollama → parse → verify → cite.
Never answers from model general knowledge: without retrieved evidence the
service returns the fixed refusal sentence without calling the model.
"""

import re
from datetime import datetime, timezone

from ..core.logging_config import get_logger
from ..models.schemas import ChatResponse, VerificationOut
from . import citation_service, ollama_service, retrieval_service, verification_service

logger = get_logger(__name__)

ANSWER_PROMPT = """You answer questions about uploaded documents.

Use only the evidence provided below. Do not use outside knowledge.

Rules:
- Do not guess.
- Do not invent facts, numbers, dates or citations.
- Do not answer if the evidence does not support the question.
- If the answer is missing, say exactly:
  "I could not find enough information in the uploaded documents to answer this confidently."
- Preserve numbers, dates, units and percentages.
- If sources conflict, clearly describe the conflict.
- Mention the document name and page number for every important claim.
- Keep the answer direct and clear.

Evidence:
{context}

Question:
{question}

Return:

Answer:
...

Evidence status:
Supported, Partially supported, Not found, Conflicting sources, or Low-quality source

Sources:
- Document name, page number, section"""

SUMMARY_PROMPT = """You summarize uploaded documents.

Use only the text below. Do not add outside information.

Mode: {mode}
{mode_instruction}

Text:
{context}

Return only the summary."""

_MODE_INSTRUCTIONS = {
    "short": "Write a short summary in at most 5 sentences.",
    "detailed": "Write a detailed summary covering all main points, numbers and conclusions.",
    "key_points": "List the key points as bullet lines, one per line starting with '-'.",
}


def _parse_response(raw: str) -> tuple[str, str]:
    """Extract (answer_text, evidence_status_text) from the model output."""
    answer_match = re.search(
        r"Answer:\s*(.*?)(?=\n\s*Evidence status:|\Z)", raw, re.DOTALL | re.IGNORECASE
    )
    status_match = re.search(
        r"Evidence status:\s*(.*?)(?=\n\s*Sources:|\Z)", raw, re.DOTALL | re.IGNORECASE
    )
    answer = answer_match.group(1).strip() if answer_match else raw.strip()
    status_text = status_match.group(1).strip().splitlines()[0] if status_match else ""
    return answer, status_text


def answer_question(question: str, document_ids: list[str] | None = None) -> ChatResponse:
    ollama_service.ensure_models_available()

    sections = retrieval_service.retrieve(question, document_ids=document_ids)
    if not sections:
        logger.info("No relevant evidence for question; refusing to answer.")
        return ChatResponse(
            answer=verification_service.REFUSAL_SENTENCE,
            evidence_status="not_found",
            sources=[],
            verification=VerificationOut(passed=True, warnings=[]),
            created_at=datetime.now(timezone.utc),
        )

    context = retrieval_service.build_context(sections)
    prompt = ANSWER_PROMPT.format(context=context, question=question)
    raw = ollama_service.generate_answer(prompt)
    answer, status_text = _parse_response(raw)

    status, passed, warnings = verification_service.verify(answer, status_text, sections)
    if status == "not_found":
        # Model judged evidence insufficient: use the exact refusal sentence.
        answer = verification_service.REFUSAL_SENTENCE
        passed = True

    return ChatResponse(
        answer=answer,
        evidence_status=status,
        sources=citation_service.build_sources(sections),
        verification=VerificationOut(passed=passed, warnings=warnings),
        created_at=datetime.now(timezone.utc),
    )


def summarize_document(processed: dict, mode: str = "short") -> str:
    ollama_service.ensure_models_available()
    pages = processed.get("pages", [])
    text_parts = [
        f"[Page {p['page_number']}]\n{p.get('text', '')}" for p in pages if p.get("text")
    ]
    context = "\n\n".join(text_parts)[:12000]
    if not context.strip():
        return "This document has no readable text to summarize."
    prompt = SUMMARY_PROMPT.format(
        mode=mode, mode_instruction=_MODE_INSTRUCTIONS.get(mode, _MODE_INSTRUCTIONS["short"]),
        context=context,
    )
    return ollama_service.generate_answer(prompt)
