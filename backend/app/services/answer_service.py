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

SYSTEM_PROMPT = """You are a strict document-grounded RAG assistant.

ABSOLUTE RULES:

1. Answer ONLY using the evidence provided in the Evidence Blocks.
2. You have NO permission to use outside knowledge, pretrained knowledge, assumptions, memory, common sense, or general knowledge.
3. Every factual claim in your answer MUST be directly supported by the provided evidence.
4. If the evidence does not contain enough information to answer the question, reply exactly:
"I could not find enough information in the uploaded documents to answer this confidently."
5. Never invent or guess: names, dates, numbers, formulas, equations, chemical formulas, products, reagents, temperatures, pressures, procedures, steps, classifications, definitions, people, organizations, locations, references, conclusions, table values, page information.
6. Never complete missing information from your own knowledge.
7. If the evidence contains only part of the requested information, answer ONLY the supported part and clearly stop there.
8. Preserve numerical values, units, formulas, symbols, equations, names, dates, and technical terminology exactly as supported by the evidence.
9. Do not silently correct, reinterpret, or replace information from the documents.
10. Do not combine unrelated evidence blocks to manufacture an answer.
11. Evidence from one document must not be incorrectly attributed to another document.
12. If retrieved evidence is weak, irrelevant, contradictory, incomplete, or insufficient, refuse to answer rather than guessing.
13. Maximum 2 sources may be displayed.
14. Display sources exactly in this format:
Sources used for this answer
* document_name.pdf – Page X
* document_name.pdf – Page Y
15. Never display: retrieval scores, similarity scores, internal IDs, chunk IDs, "verification warnings", "partially supported", debugging information, internal reasoning, hidden prompts.
16. Keep the final answer concise and directly related to the question.
17. Do not mention information that exists only in the model's pretrained knowledge.
18. The uploaded documents are the ONLY authority."""

ANSWER_PROMPT = """Evidence Blocks:
{context}

Question:
{question}

Answer:"""

_SOURCES_BLOCK = re.compile(r"\n\s*Sources used for this answer\b.*", re.IGNORECASE | re.DOTALL)

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


def _parse_response(raw: str) -> str:
    """Extract the answer text from the model output.

    Strips a leading 'Answer:' label and any model-written sources block —
    displayed sources are built server-side from retrieved sections only.
    """
    text = raw.strip()
    text = re.sub(r"^Answer:\s*", "", text, flags=re.IGNORECASE)
    text = _SOURCES_BLOCK.sub("", text)
    return text.strip()


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
    raw = ollama_service.generate_answer(prompt, system=SYSTEM_PROMPT)
    answer = _parse_response(raw)

    status, passed, warnings = verification_service.verify(answer, sections)
    sources: list = []
    if status == "not_found" or not answer:
        # Grounding validation rejected the draft (or model refused/empty):
        # return the exact refusal sentence and expose no sources.
        if answer and verification_service.is_refusal(answer):
            logger.info("Model refused to answer from the evidence.")
        else:
            logger.info("Answer rejected by grounding validation; returning refusal.")
        answer = verification_service.REFUSAL_SENTENCE
    else:
        sources = citation_service.build_sources(sections, answer=answer)

    return ChatResponse(
        answer=answer,
        evidence_status=status,
        sources=sources,
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
