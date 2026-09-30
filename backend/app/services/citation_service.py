"""Citation assembly.

Sources are built ONLY from retrieved sections — page numbers and document
names are never taken from model output, so they cannot be invented.
At most settings.max_sources (2) sources are exposed, deduplicated per
document page so both slots are never wasted on the same page.
"""

import re

from ..config import get_settings
from ..models.schemas import SourceOut

EXCERPT_CHARS = 320
_TOKEN = re.compile(r"[a-z0-9]{4,}")


def _answer_overlap(section: dict, answer_tokens: set[str]) -> int:
    """How many distinct answer tokens appear in this section's content.

    Used to cite the page the answer actually came from rather than merely the
    highest query-similarity page. Falls back to 0 (retrieval order) when the
    answer shares no substantive tokens with any section.
    """
    if not answer_tokens:
        return 0
    content = section.get("content", "").lower()
    return sum(1 for tok in answer_tokens if tok in content)


def build_sources(
    sections: list[dict], limit: int | None = None, answer: str | None = None
) -> list[SourceOut]:
    limit = limit if limit is not None else get_settings().max_sources
    if answer:
        answer_tokens = set(_TOKEN.findall(answer.lower()))
        # Stable re-rank: prefer sections that contain the answer's own tokens,
        # keeping retrieval order as the tie-breaker (and as the fallback).
        sections = sorted(
            enumerate(sections),
            key=lambda pair: (-_answer_overlap(pair[1], answer_tokens), pair[0]),
        )
        sections = [s for _, s in sections]
    sources: list[SourceOut] = []
    seen: set[tuple[str, int]] = set()
    for section in sections:
        key = (section["document_name"], section["page_number"])
        if key in seen:
            continue
        seen.add(key)
        content = section.get("content", "").strip()
        excerpt = content[:EXCERPT_CHARS]
        if len(content) > EXCERPT_CHARS:
            excerpt = excerpt.rsplit(" ", 1)[0] + "…"
        sources.append(
            SourceOut(
                document_name=section["document_name"],
                page_number=section["page_number"],
                section=section.get("section_title"),
                excerpt=excerpt,
                score=section.get("score", 0.0),
            )
        )
        if len(sources) >= limit:
            break
    return sources
