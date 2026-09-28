"""Basic table extraction from PDFs using pdfplumber.

Tables are converted to markdown-like text and stored as separate sections
with their page numbers. Failures on a page are logged and skipped.
"""

from pathlib import Path

from ..core.logging_config import get_logger

logger = get_logger(__name__)


def _table_to_text(table: list[list]) -> str:
    rows = []
    for row in table:
        cells = [(c or "").replace("\n", " ").strip() for c in row]
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def extract_tables(path: Path) -> list[dict]:
    """Return [{'page_number': int, 'content': str, 'index': int}, ...]."""
    tables_found: list[dict] = []
    try:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            for page_index, page in enumerate(pdf.pages):
                page_number = page_index + 1
                try:
                    for table_index, table in enumerate(page.extract_tables()):
                        text = _table_to_text(table)
                        if len(text.strip()) > 20:
                            tables_found.append(
                                {
                                    "page_number": page_number,
                                    "content": text,
                                    "index": table_index,
                                }
                            )
                except Exception as exc:
                    logger.warning("Table extraction failed on page %s: %s", page_number, exc)
    except Exception as exc:
        logger.warning("pdfplumber could not open %s: %s", path.name, exc)
    return tables_found
