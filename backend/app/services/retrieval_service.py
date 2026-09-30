"""Retrieval: embed the question, search FAISS, gate by score, then rerank.

Two-stage retrieval over the local FAISS index:
  1. First stage — dense cosine similarity (vector_store.search) over-fetches a
     candidate pool; the min-score gate on the dense score preserves document
     isolation and the "insufficient evidence" refusal behavior.
  2. Second stage — a model-free reranker reorders the surviving candidates by
     IDF-weighted lexical relevance (BM25-style) blended with the dense score, so
     a chunk carrying the question's discriminative terms outranks chunks that
     merely match common/name terms with a high cosine score.

No cross-encoder/extra model is used: the reranker re-scores the already-retrieved
candidates, keeping the existing architecture, models and offline setup intact.
"""

import math
import re

from ..config import get_settings
from ..core.logging_config import get_logger
from . import embedding_service, vector_store

logger = get_logger(__name__)

# Weight of the lexical (BM25-style) signal in the rerank blend. The dense score
# still dominates; lexical relevance breaks ties and promotes term-specific chunks.
RERANK_WEIGHT = 0.4
# First-stage over-fetch multiplier so the reranker has a pool to reorder.
CANDIDATE_MULTIPLIER = 4
CANDIDATE_FLOOR = 20

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    """a an and are as at be by for from has have how i in is it its of on or that
    the this to was were what when where which who why will with you your""".split()
)


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 1 and t not in _STOPWORDS]


def _rerank(question: str, sections: list[dict]) -> list[dict]:
    """Reorder dense-qualified candidates by hybrid dense + lexical relevance.

    Returns the same section dicts (their 'score' stays the dense cosine score);
    only the ordering changes. Falls back to the dense order when the question has
    no usable terms or no candidate shares any term with it.
    """
    query_terms = set(_tokens(question))
    if not query_terms or len(sections) < 2:
        return sections

    n = len(sections)
    doc_tokens = [
        _tokens(f"{sec.get('content', '')} {sec.get('section_title') or ''}") for sec in sections
    ]
    df: dict[str, int] = {}
    for toks in doc_tokens:
        for term in set(toks):
            df[term] = df.get(term, 0) + 1

    # IDF weighting + tf saturation, with NO document-length normalization (b=0).
    # Length-normalized BM25 (b=0.75) penalized long fact-bearing chunks (e.g. an
    # EDUCATION section listing many courses) and favored short name/header chunks,
    # which is exactly wrong for fact-lookup queries.
    k1 = 1.5
    lexical: list[float] = []
    for toks in doc_tokens:
        tf: dict[str, int] = {}
        for term in toks:
            tf[term] = tf.get(term, 0) + 1
        score = 0.0
        for term in query_terms:
            freq = tf.get(term)
            if not freq:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * (freq * (k1 + 1)) / (freq + k1)
        lexical.append(score)

    max_lex = max(lexical) if lexical else 0.0
    if max_lex <= 0:
        return sections  # no lexical signal — keep the dense ordering

    ordered = sorted(
        range(n),
        key=lambda i: (
            -((1 - RERANK_WEIGHT) * sections[i].get("score", 0.0) + RERANK_WEIGHT * (lexical[i] / max_lex)),
            i,
        ),
    )
    return [sections[i] for i in ordered]


def retrieve(
    question: str,
    document_ids: list[str] | None = None,
    top_k: int | None = None,
    min_score: float | None = None,
) -> list[dict]:
    """Return relevant sections: [{...section, 'score': float}], best first.

    'score' is the first-stage dense cosine similarity; ordering reflects the
    second-stage reranker.
    """
    settings = get_settings()
    top_k = top_k or settings.top_k_results
    min_score = settings.min_retrieval_score if min_score is None else min_score

    query_embedding = embedding_service.embed_query(question)
    # Over-fetch so the reranker can promote a relevant chunk that dense similarity
    # placed just outside the final top_k.
    candidate_k = max(top_k * CANDIDATE_MULTIPLIER, CANDIDATE_FLOOR)
    results = vector_store.search(query_embedding, k=candidate_k, document_ids=document_ids)

    # Dense-score gate first: preserves refusal + document isolation (an empty
    # qualified set still means "not enough evidence", never rescued by lexical).
    qualified = [
        {**section, "score": round(score, 4)} for section, score in results if score >= min_score
    ]
    if not qualified:
        return []

    reranked = _rerank(question, qualified)
    return reranked[:top_k]



def build_context(sections: list[dict], max_characters: int | None = None) -> str:
    """Format retrieved sections as numbered evidence blocks within a character budget.

    Duplicate content (e.g. a table chunk that repeats page text) is included once.
    """
    settings = get_settings()
    max_characters = max_characters or settings.max_context_characters
    blocks: list[str] = []
    used = 0
    seen_content: set[str] = set()
    for section in sections:
        content = section["content"].strip()
        content_key = " ".join(content.lower().split())
        if content_key in seen_content:
            continue
        seen_content.add(content_key)
        header = (
            f"[Source {len(blocks) + 1}] {section['document_name']} — page {section['page_number']}"
        )
        if section.get("section_title"):
            header += f" — {section['section_title']}"
        if section.get("content_type") == "ocr":
            header += " (OCR-derived text)"
        block = f"{header}\n{content}"
        if used + len(block) > max_characters and blocks:
            break
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks)
