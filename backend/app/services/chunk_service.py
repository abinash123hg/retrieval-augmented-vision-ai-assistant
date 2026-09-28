"""Cleaning and sectioning of extracted page content.

Every section carries document identity, page number, optional heading and
content type (text | table | ocr).
"""

import re
import uuid

MAX_SECTION_CHARS = 1600
MIN_SECTION_CHARS = 40


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"-\n(?=[a-z])", "", text)  # de-hyphenate line breaks
    return text.strip()


def _looks_like_heading(line: str) -> bool:
    """Strict heading check: short ALL-CAPS or Title Case line, no ending punctuation."""
    line = line.strip()
    if not line or len(line) > 60:
        return False
    core = re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", line)
    words = core.split()
    if not words or len(words) > 8:
        return False
    if any(w.endswith((".", ",", ";", ":")) for w in words):
        return False
    alpha_words = [w for w in words if any(c.isalpha() for c in w)]
    if not alpha_words:
        return False
    if not alpha_words[0][0].isupper():
        return False
    if len(alpha_words) == 1:
        return alpha_words[0].isupper() and len(alpha_words[0]) >= 3
    all_caps = all(w.isupper() for w in alpha_words if len(w) > 1)
    title_case = all(w[0].isupper() for w in alpha_words)
    return all_caps or title_case


def _split_long(block: str) -> list[str]:
    if len(block) <= MAX_SECTION_CHARS:
        return [block]
    parts: list[str] = []
    sentences = re.split(r"(?<=[.!?])\s+", block)
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) + 1 > MAX_SECTION_CHARS and current:
            parts.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        parts.append(current.strip())
    return parts


def chunk_pages(
    document_id: str,
    document_name: str,
    pages: list[dict],
    tables: list[dict] | None = None,
) -> list[dict]:
    """Build searchable sections from page dicts {'page_number', 'text', 'ocr_used'}."""
    sections: list[dict] = []

    for page in pages:
        text = clean_text(page.get("text", ""))
        if len(text) < MIN_SECTION_CHARS:
            continue
        page_number = page["page_number"]
        content_type = "ocr" if page.get("ocr_used") else "text"

        # Split by headings so section titles survive where possible.
        blocks: list[tuple[str | None, str]] = []
        current_heading: str | None = None
        current_lines: list[str] = []
        for line in text.split("\n"):
            stripped = line.strip()
            if _looks_like_heading(stripped) and current_lines:
                blocks.append((current_heading, "\n".join(current_lines)))
                current_heading = stripped
                current_lines = []
            elif _looks_like_heading(stripped) and not current_lines:
                current_heading = stripped
            else:
                current_lines.append(line)
        if current_lines:
            blocks.append((current_heading, "\n".join(current_lines)))

        for heading, block in blocks:
            block = clean_text(block)
            if len(block) < MIN_SECTION_CHARS:
                continue
            for part in _split_long(block):
                sections.append(
                    {
                        "id": uuid.uuid4().hex,
                        "document_id": document_id,
                        "document_name": document_name,
                        "page_number": page_number,
                        "section_title": heading,
                        "content": part,
                        "content_type": content_type,
                    }
                )

        # Never lose a page's content to heading splitting: if no section was
        # produced for this page, index the whole page text as one section.
        if not any(s["page_number"] == page_number and s["document_id"] == document_id for s in sections):
            for part in _split_long(text):
                sections.append(
                    {
                        "id": uuid.uuid4().hex,
                        "document_id": document_id,
                        "document_name": document_name,
                        "page_number": page_number,
                        "section_title": None,
                        "content": part,
                        "content_type": content_type,
                    }
                )

    for table in tables or []:
        content = clean_text(table["content"])
        if len(content) < MIN_SECTION_CHARS:
            continue
        sections.append(
            {
                "id": uuid.uuid4().hex,
                "document_id": document_id,
                "document_name": document_name,
                "page_number": table["page_number"],
                "section_title": f"Table {table.get('index', 0) + 1}",
                "content": content,
                "content_type": "table",
            }
        )

    return sections
