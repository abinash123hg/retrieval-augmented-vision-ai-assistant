"""Citation assembly.

Sources are built ONLY from retrieved sections — page numbers and document
names are never taken from model output, so they cannot be invented.
"""

from ..models.schemas import SourceOut

EXCERPT_CHARS = 320


def build_sources(sections: list[dict]) -> list[SourceOut]:
    sources: list[SourceOut] = []
    seen: set[tuple[str, int, str]] = set()
    for section in sections:
        key = (
            section["document_name"],
            section["page_number"],
            section.get("section_title") or "",
        )
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
    return sources
