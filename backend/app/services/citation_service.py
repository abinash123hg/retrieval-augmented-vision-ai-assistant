"""Citation assembly.

Sources are built ONLY from retrieved sections — page numbers and document
names are never taken from model output, so they cannot be invented.
At most settings.max_sources (2) sources are exposed, deduplicated per
document page so both slots are never wasted on the same page.
"""

from ..config import get_settings
from ..models.schemas import SourceOut

EXCERPT_CHARS = 320


def build_sources(sections: list[dict], limit: int | None = None) -> list[SourceOut]:
    limit = limit if limit is not None else get_settings().max_sources
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
