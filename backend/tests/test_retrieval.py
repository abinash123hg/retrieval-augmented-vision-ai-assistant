import numpy as np

from app.services import chunk_service, retrieval_service, vector_store

KEYWORDS = ["revenue", "risk", "policy", "invoice", "profit"]


def fake_embed(text: str) -> list[float]:
    """Deterministic keyword-bag embedding for tests (no Ollama needed)."""
    vector = np.zeros(len(KEYWORDS), dtype="float32")
    lowered = text.lower()
    for i, keyword in enumerate(KEYWORDS):
        if keyword in lowered:
            vector[i] = 1.0
    if not vector.any():
        vector[0] = 0.01
    return vector.tolist()


def fake_embed_many(texts: list[str]) -> list[list[float]]:
    return [fake_embed(t) for t in texts]


def _seed():
    pages = [
        {"page_number": 1, "text": "Company overview. This annual report describes the business, its markets and its overall revenue performance for the fiscal year.", "ocr_used": False},
        {"page_number": 2, "text": "Revenue. Total revenue was 500 million dollars, up from 420 million dollars in the previous year.", "ocr_used": False},
        {"page_number": 3, "text": "Risk factors. The main risk is currency fluctuation, followed by supply chain disruption and changing policy regulation.", "ocr_used": False},
    ]
    sections = chunk_service.chunk_pages("doc1", "annual_report.pdf", pages)
    vector_store.add_sections(sections, fake_embed_many([s["content"] for s in sections]))
    return sections


def test_chunking_attaches_metadata():
    pages = [
        {"page_number": 7, "text": "Invoice summary. The invoice total was 1200 dollars for consulting services rendered in March.", "ocr_used": True},
    ]
    sections = chunk_service.chunk_pages("d", "invoice.png", pages)
    assert sections
    for section in sections:
        assert section["document_name"] == "invoice.png"
        assert section["page_number"] == 7
        assert section["content_type"] == "ocr"


def test_short_page_content_is_never_lost():
    pages = [
        {"page_number": 1, "text": "INVOICE 2025-041\nConsulting services total 8450 USD\nDue date: 15 October 2025", "ocr_used": True},
    ]
    sections = chunk_service.chunk_pages("d2", "invoice.png", pages)
    assert sections, "page content must not be dropped by heading splitting"
    assert "8450" in " ".join(s["content"] for s in sections)


def test_retrieval_returns_relevant_page(monkeypatch):
    monkeypatch.setattr(retrieval_service.embedding_service, "embed_query", fake_embed)
    _seed()
    results = retrieval_service.retrieve("What was the total revenue?", min_score=0.3)
    assert results
    top = results[0]
    assert "revenue" in top["content"].lower()
    assert top["document_name"] == "annual_report.pdf"
    assert isinstance(top["page_number"], int)
    assert top["score"] >= 0.3


def test_retrieval_filters_by_document(monkeypatch):
    monkeypatch.setattr(retrieval_service.embedding_service, "embed_query", fake_embed)
    _seed()
    results = retrieval_service.retrieve("risk", document_ids=["other-doc"], min_score=0.1)
    assert results == []


def test_retrieval_empty_index(monkeypatch):
    monkeypatch.setattr(retrieval_service.embedding_service, "embed_query", fake_embed)
    assert retrieval_service.retrieve("anything", min_score=0.1) == []


def test_build_context_includes_source_headers(monkeypatch):
    monkeypatch.setattr(retrieval_service.embedding_service, "embed_query", fake_embed)
    _seed()
    results = retrieval_service.retrieve("risk factors", min_score=0.3)
    context = retrieval_service.build_context(results)
    assert "[Source 1]" in context
    assert "annual_report.pdf" in context
    assert "page" in context


def test_remove_document_clears_its_sections(monkeypatch):
    monkeypatch.setattr(retrieval_service.embedding_service, "embed_query", fake_embed)
    _seed()
    vector_store.remove_document("doc1")
    assert retrieval_service.retrieve("revenue", min_score=0.1) == []
