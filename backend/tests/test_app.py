"""Consolidated backend test suite.

Merges the former per-module tests (answer/verification/citation, file service,
health, OCR preprocessing, PDF extraction, retrieval, vector store, docker) into
a single file. The temporary data-store environment is configured BEFORE the app
is imported so get_settings() resolves to an isolated temp dir, and an autouse
fixture resets the registry + index around every test. The report tests are gone
along with the report feature.
"""

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="doculens-test-")
os.environ["UPLOAD_DIR"] = os.path.join(_TMP, "uploads")
os.environ["PROCESSED_DIR"] = os.path.join(_TMP, "processed")
os.environ["INDEX_DIR"] = os.path.join(_TMP, "indexes")
os.environ["MAX_FILE_SIZE_MB"] = "1"

from pathlib import Path  # noqa: E402

import fitz  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
import yaml  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from app import ollama_service, pdf_service, rag_service, routes, vector_store  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.main import FileTooLargeError, InvalidFileError, app  # noqa: E402

get_settings.cache_clear()
get_settings().ensure_dirs()

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_state():
    pdf_service.clear_all()
    vector_store.clear()
    yield
    pdf_service.clear_all()
    vector_store.clear()


# ===========================================================================
# Answer generation, verification and citation
# ===========================================================================
SECTIONS = [
    {
        "document_name": "annual_report.pdf",
        "document_id": "d1",
        "page_number": 2,
        "section_title": "Revenue",
        "content": "Total revenue was 500 million dollars in 2025.",
        "content_type": "text",
        "score": 0.81,
    },
    {
        "document_name": "annual_report.pdf",
        "document_id": "d1",
        "page_number": 3,
        "section_title": None,
        "content": "Operating costs reached 310 million dollars.",
        "content_type": "ocr",
        "score": 0.55,
    },
]


def test_refusal_detected():
    status, passed, warnings = rag_service.verify(rag_service.REFUSAL_SENTENCE, [])
    assert status == "not_found"
    assert passed


def test_empty_answer_is_rejected():
    status, _, _ = rag_service.verify("   ", SECTIONS)
    assert status == "not_found"


def test_grounded_numbers_pass_as_supported():
    status, passed, warnings = rag_service.verify(
        "Total revenue was 500 million dollars in 2025 (annual_report.pdf, page 2).",
        SECTIONS,
    )
    assert status == "supported"
    assert passed
    assert not any("rejected" in w for w in warnings)


def test_invented_number_rejects_the_answer():
    status, passed, warnings = rag_service.verify(
        "Total revenue was 740 million dollars.", SECTIONS
    )
    assert status == "not_found", "unsupported numbers must force the refusal path"
    assert passed
    assert any("740" in w for w in warnings)


def test_number_with_comma_formatting_is_matched():
    sections = [
        {
            "document_name": "invoice.png",
            "document_id": "d2",
            "page_number": 1,
            "section_title": None,
            "content": "Consulting services total 8450 USD",
            "content_type": "ocr",
            "score": 0.7,
        }
    ]
    status, _, _ = rag_service.verify("The total is 8,450 USD.", sections)
    assert status == "supported"


def test_text_answer_without_numbers_is_supported():
    status, _, _ = rag_service.verify(
        "The report describes the company's revenue performance.", SECTIONS
    )
    assert status == "supported"


def test_ocr_evidence_warning_is_internal():
    _, _, warnings = rag_service.verify(
        "Operating costs reached 310 million dollars.", SECTIONS
    )
    assert any("OCR" in w for w in warnings)


def test_citations_capped_at_two_and_deduped_per_page():
    many = [
        {**SECTIONS[0], "section_title": "A"},
        {**SECTIONS[0], "section_title": "B"},  # same page -> deduped
        SECTIONS[1],
        {**SECTIONS[1], "page_number": 4, "content": "Extra page content here."},
    ]
    sources = rag_service.build_sources(many)
    assert len(sources) == 2
    assert sources[0].page_number == 2
    assert sources[1].page_number == 3


def test_parse_strips_answer_label_and_sources_block():
    raw = (
        "Answer:\nThe total revenue was 500 million dollars.\n\n"
        "Sources used for this answer\n* annual_report.pdf – Page 2"
    )
    answer = rag_service._parse_response(raw)
    assert answer == "The total revenue was 500 million dollars."


def test_parse_tolerates_plain_text():
    assert rag_service._parse_response("Short reply only.") == "Short reply only."


def test_parse_strips_leading_citation_bullet():
    assert (
        rag_service._parse_response("* Beta Module was sold 800 units.")
        == "Beta Module was sold 800 units."
    )


def test_parse_strips_evidence_block_reference():
    assert (
        rag_service._parse_response(
            "Beta Module was sold 800 units, as stated in the Evidence Block from [Source 1]."
        )
        == "Beta Module was sold 800 units."
    )


def test_system_prompt_contains_exact_refusal_sentence():
    assert rag_service.REFUSAL_SENTENCE in rag_service.SYSTEM_PROMPT


def test_system_prompt_has_no_source_display_rules():
    # Rules 13 & 14 (display a sources list) were removed so citations stay server-side.
    assert "Display sources exactly" not in rag_service.SYSTEM_PROMPT
    assert "Sources used for this answer" not in rag_service.SYSTEM_PROMPT


def test_summarize_flags_truncation_for_long_documents(monkeypatch):
    monkeypatch.setattr(rag_service.ollama_service, "ensure_models_available", lambda: None)
    captured = {}

    def fake_generate(prompt, system=None):
        captured["prompt"] = prompt
        return "A summary."

    monkeypatch.setattr(rag_service.ollama_service, "generate_answer", fake_generate)
    long_text = "word " * 5000  # ~25k chars, well over the 12000 budget
    processed = {"pages": [{"page_number": 1, "text": long_text}]}
    summary, truncated = rag_service.summarize_document(processed, "short")
    assert summary == "A summary."
    assert truncated is True
    # Only the budgeted prefix reaches the model, not the full text.
    assert len(captured["prompt"]) < len(long_text)


def test_summarize_short_document_is_not_truncated(monkeypatch):
    monkeypatch.setattr(rag_service.ollama_service, "ensure_models_available", lambda: None)
    monkeypatch.setattr(rag_service.ollama_service, "generate_answer", lambda prompt, system=None: "Short.")
    processed = {"pages": [{"page_number": 1, "text": "A brief note."}]}
    summary, truncated = rag_service.summarize_document(processed, "short")
    assert summary == "Short."
    assert truncated is False


def test_summarize_empty_document_reports_no_text(monkeypatch):
    monkeypatch.setattr(rag_service.ollama_service, "ensure_models_available", lambda: None)
    summary, truncated = rag_service.summarize_document({"pages": []}, "short")
    assert "no readable text" in summary.lower()
    assert truncated is False


# ===========================================================================
# File service: upload validation, registry, deletion, crash recovery
# ===========================================================================
PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< >>\nendobj\ntrailer\n<<>>\n%%EOF\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def test_save_valid_pdf():
    document_id, path = pdf_service.save_upload("report.pdf", PDF_BYTES)
    assert path.exists()
    doc = pdf_service.get_document(document_id)
    assert doc.file_name == "report.pdf"
    assert doc.file_type == "pdf"
    assert doc.processing_status == "waiting"


def test_save_valid_png():
    document_id, _ = pdf_service.save_upload("scan.png", PNG_BYTES)
    assert pdf_service.get_document(document_id).file_type == "image"


def test_reject_unsupported_extension():
    with pytest.raises(InvalidFileError):
        pdf_service.save_upload("notes.txt", b"hello")


def test_reject_empty_file():
    with pytest.raises(InvalidFileError):
        pdf_service.save_upload("empty.pdf", b"")


def test_reject_oversized_file():
    with pytest.raises(FileTooLargeError):
        pdf_service.save_upload("big.pdf", PDF_BYTES + b"x" * (2 * 1024 * 1024))


def test_filename_is_sanitized():
    document_id, path = pdf_service.save_upload("../../etc/passwd.pdf", PDF_BYTES)
    doc = pdf_service.get_document(document_id)
    assert "/" not in doc.file_name and "\\" not in doc.file_name
    assert pdf_service.is_within_directory(path, get_settings().upload_path)


def test_list_and_delete():
    document_id, _ = pdf_service.save_upload("a.pdf", PDF_BYTES)
    assert any(d.id == document_id for d in pdf_service.list_documents())
    pdf_service.delete_document(document_id)
    assert not any(d.id == document_id for d in pdf_service.list_documents())
    with pytest.raises(Exception):
        pdf_service.get_document(document_id)


def test_recover_interrupted_documents_marks_stale_as_failed():
    doc_id, _ = pdf_service.save_upload("stuck.pdf", PDF_BYTES)
    # Simulate a crash mid-pipeline: leave the document in "processing".
    pdf_service.update_document(doc_id, processing_status="processing")

    recovered = pdf_service.recover_interrupted_documents()
    assert recovered >= 1
    doc = pdf_service.get_document(doc_id)
    assert doc.processing_status == "failed"
    assert "interrupted" in (doc.error_message or "").lower()


def test_recover_leaves_finished_documents_untouched():
    doc_id, _ = pdf_service.save_upload("done.pdf", PDF_BYTES)
    pdf_service.update_document(doc_id, processing_status="ready")
    pdf_service.recover_interrupted_documents()
    assert pdf_service.get_document(doc_id).processing_status == "ready"


# ===========================================================================
# Health endpoint
# ===========================================================================
def test_health_reports_ok(monkeypatch):
    monkeypatch.setattr(ollama_service, "check_ollama_connection", lambda: True)
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["ollama"] is True
    assert body["chat_model"] == "qwen2.5:3b"
    assert body["embedding_model"] == "nomic-embed-text:latest"


def test_health_reports_ollama_down(monkeypatch):
    monkeypatch.setattr(ollama_service, "check_ollama_connection", lambda: False)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["ollama"] is False


def test_health_route_module_exists():
    assert routes.router is not None


# ===========================================================================
# OCR image preprocessing (offline: no Ollama, no Tesseract run)
# ===========================================================================
def _solid(value: int, size=(200, 120)) -> Image.Image:
    return Image.fromarray(np.full((size[1], size[0]), value, dtype=np.uint8), mode="L")


def test_preprocess_returns_grayscale_binary_image():
    rgb = Image.new("RGB", (300, 200), (200, 190, 170))
    out = pdf_service.preprocess(rgb)
    assert out.mode == "L"
    values = set(np.unique(np.asarray(out)))
    assert values <= {0, 255}, f"expected pure black/white, got {values}"


def test_auto_invert_flips_dark_page_to_light():
    dark = _solid(20)
    out = pdf_service.auto_invert(dark)
    assert np.asarray(out, dtype=np.float32).mean() > 127.5


def test_auto_invert_leaves_light_page_alone():
    light = _solid(230)
    out = pdf_service.auto_invert(light)
    assert np.asarray(out, dtype=np.float32).mean() > 127.5
    assert np.array_equal(np.asarray(out), np.asarray(light))


def test_upscale_enlarges_small_scan():
    small = _solid(240, size=(200, 120))
    out = pdf_service.upscale(small)
    assert min(out.size) >= pdf_service.MIN_SIDE
    assert max(out.size) <= pdf_service.MAX_SIDE


def test_upscale_leaves_large_scan_unchanged():
    large = _solid(240, size=(2000, 1500))
    out = pdf_service.upscale(large)
    assert out.size == large.size


def test_binarize_separates_ink_from_sepia_paper():
    arr = np.full((120, 200), 200, dtype=np.uint8)  # sepia-ish paper
    arr[40:80, 40:160] = 60  # dark ink block
    img = Image.fromarray(arr, mode="L")
    out = np.asarray(pdf_service.binarize(img))
    assert out[10, 10] == 255  # paper -> white
    assert out[60, 60] == 0  # ink -> black


def test_pad_adds_white_border():
    img = _solid(240, size=(100, 100))
    out = pdf_service.pad(img)
    assert out.size == (100 + 2 * pdf_service.PAD, 100 + 2 * pdf_service.PAD)
    corner = np.asarray(out)[0, 0]
    assert corner == 255


def test_otsu_threshold_between_two_modes():
    arr = np.concatenate(
        [np.full(5000, 60, dtype=np.uint8), np.full(5000, 200, dtype=np.uint8)]
    )
    t = pdf_service._otsu_threshold(arr)
    # Threshold must sit at/above the ink mode and below the paper mode so that
    # `arr > t` maps ink->0 and paper->255.
    assert 60 <= t < 200


# ===========================================================================
# PDF / image extraction
# ===========================================================================
def _make_text_pdf(path, pages_text: list[str]) -> None:
    document = fitz.open()
    for text in pages_text:
        page = document.new_page()
        page.insert_text((72, 72), text, fontsize=12)
    document.save(path)
    document.close()


def test_extract_native_pdf_text(tmp_path):
    pdf_path = tmp_path / "native.pdf"
    _make_text_pdf(
        pdf_path,
        ["DocuLens annual report. Total revenue was 500 million dollars in 2025.", "Second page content about expenses and risks."],
    )
    result = pdf_service.extract_pdf(pdf_path)
    assert result.page_count == 2
    assert result.failed_pages == 0
    assert "revenue" in result.pages[0].text.lower()
    assert result.pages[0].page_number == 1
    assert result.pages[1].page_number == 2
    assert not result.pages[0].ocr_used


def test_extract_invalid_pdf_raises(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.4 this is not a real pdf")
    with pytest.raises(ValueError):
        pdf_service.extract_pdf(bad)


@pytest.mark.skipif(not pdf_service.is_available(), reason="Tesseract not installed")
def test_extract_image_uses_ocr(tmp_path):
    image_path = tmp_path / "scan.png"
    image = Image.new("RGB", (900, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.text((40, 120), "Invoice total 12345", fill="black")
    image.save(image_path)

    result = pdf_service.extract_image(image_path)
    assert result.ocr_pages == 1
    assert result.pages[0].ocr_used
    assert "12345" in result.pages[0].text.replace(" ", "")


@pytest.mark.skipif(not pdf_service.is_available(), reason="Tesseract not installed")
def test_scanned_pdf_page_falls_back_to_ocr(tmp_path):
    # Build a PDF whose only page is an image (no selectable text).
    image_path = tmp_path / "page.png"
    image = Image.new("RGB", (900, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.text((40, 120), "Scanned contract page 9876", fill="black")
    image.save(image_path)

    pdf_path = tmp_path / "scanned.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_image(page.rect, filename=str(image_path))
    document.save(pdf_path)
    document.close()

    result = pdf_service.extract_pdf(pdf_path)
    assert result.ocr_pages == 1
    assert result.pages[0].ocr_used
    assert "9876" in result.pages[0].text


# ===========================================================================
# Retrieval: chunking, dense+lexical rerank, context building, isolation
# ===========================================================================
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
    sections = rag_service.chunk_pages("doc1", "annual_report.pdf", pages)
    vector_store.add_sections(sections, fake_embed_many([s["content"] for s in sections]))
    return sections


def test_chunking_attaches_metadata():
    pages = [
        {"page_number": 7, "text": "Invoice summary. The invoice total was 1200 dollars for consulting services rendered in March.", "ocr_used": True},
    ]
    sections = rag_service.chunk_pages("d", "invoice.png", pages)
    assert sections
    for section in sections:
        assert section["document_name"] == "invoice.png"
        assert section["page_number"] == 7
        assert section["content_type"] == "ocr"


def test_short_page_content_is_never_lost():
    pages = [
        {"page_number": 1, "text": "INVOICE 2025-041\nConsulting services total 8450 USD\nDue date: 15 October 2025", "ocr_used": True},
    ]
    sections = rag_service.chunk_pages("d2", "invoice.png", pages)
    assert sections, "page content must not be dropped by heading splitting"
    assert "8450" in " ".join(s["content"] for s in sections)


def test_very_short_page_is_still_indexed():
    # A page below MIN_SECTION_CHARS must not be dropped before the whole-page
    # fallback runs; otherwise short receipts/stubs become unsearchable.
    pages = [{"page_number": 1, "text": "Total 8450 USD", "ocr_used": True}]
    sections = rag_service.chunk_pages("d3", "stub.png", pages)
    assert sections, "a short but non-empty page must still produce a section"
    assert "8450" in " ".join(s["content"] for s in sections)


def test_empty_page_produces_no_section():
    pages = [{"page_number": 1, "text": "   \n  \n", "ocr_used": False}]
    assert rag_service.chunk_pages("d4", "blank.png", pages) == []


def test_retrieval_returns_relevant_page(monkeypatch):
    monkeypatch.setattr(rag_service, "embed_query", fake_embed)
    _seed()
    results = rag_service.retrieve("What was the total revenue?", min_score=0.3)
    assert results
    top = results[0]
    assert "revenue" in top["content"].lower()
    assert top["document_name"] == "annual_report.pdf"
    assert isinstance(top["page_number"], int)
    assert top["score"] >= 0.3


def test_retrieval_filters_by_document(monkeypatch):
    monkeypatch.setattr(rag_service, "embed_query", fake_embed)
    _seed()
    results = rag_service.retrieve("risk", document_ids=["other-doc"], min_score=0.1)
    assert results == []


def test_retrieval_empty_index(monkeypatch):
    monkeypatch.setattr(rag_service, "embed_query", fake_embed)
    assert rag_service.retrieve("anything", min_score=0.1) == []


def test_build_context_includes_source_headers(monkeypatch):
    monkeypatch.setattr(rag_service, "embed_query", fake_embed)
    _seed()
    results = rag_service.retrieve("risk factors", min_score=0.3)
    context = rag_service.build_context(results)
    assert "[Source 1]" in context
    assert "annual_report.pdf" in context
    assert "page" in context


def test_remove_document_clears_its_sections(monkeypatch):
    monkeypatch.setattr(rag_service, "embed_query", fake_embed)
    _seed()
    vector_store.remove_document("doc1")
    assert rag_service.retrieve("revenue", min_score=0.1) == []


def test_reranker_promotes_discriminative_term_over_high_dense_score():
    """Second stage must outrank name-heavy chunks that dense similarity favored.

    Mirrors the real failure with synthetic data: a repeated name appears in MANY
    chunks (low IDF), while the discriminative term 'university' appears in one
    fact-bearing chunk (high IDF) that dense cosine ranked below the name-heavy
    contact/summary chunks. A real reranker promotes the fact-bearing chunk.
    """
    question = "Which university is Jordan Lee studying at?"
    sections = [
        {"content": "Jordan Lee Email Location Springfield", "score": 0.73, "page_number": 11},
        {"content": "Jordan Lee is a motivated student and developer", "score": 0.70, "page_number": 10},
        {"content": "Jordan Lee GitHub LinkedIn profile links", "score": 0.67, "page_number": 11},
        {"content": "Jordan Lee professional highlights and summary", "score": 0.65, "page_number": 1},
        {"content": "Jordan Lee career objectives and future direction", "score": 0.64, "page_number": 10},
        {"content": "Northfield University of Science and Technology", "score": 0.58, "page_number": 2},
    ]
    reranked = rag_service._rerank(question, sections)
    assert reranked[0]["page_number"] == 2
    # the original dense score is preserved on the section (only order changes)
    assert reranked[0]["score"] == 0.58


def test_reranker_keeps_dense_order_without_lexical_signal():
    """No shared query terms -> fall back to the dense ordering (no spurious reshuffle)."""
    sections = [
        {"content": "alpha beta", "score": 0.9, "page_number": 1},
        {"content": "gamma delta", "score": 0.5, "page_number": 2},
    ]
    reranked = rag_service._rerank("zzz qqq", sections)
    assert [s["page_number"] for s in reranked] == [1, 2]


def test_retrieve_reranks_between_search_and_context(monkeypatch):
    """Full path Query -> FAISS -> rerank -> context keeps the relevant page first."""
    monkeypatch.setattr(rag_service, "embed_query", fake_embed)
    _seed()
    results = rag_service.retrieve("What was the total revenue?", min_score=0.3)
    assert results
    assert "revenue" in results[0]["content"].lower()
    context = rag_service.build_context(results)
    assert "[Source 1]" in context


# ===========================================================================
# Vector store persistence
# ===========================================================================
def _embed(text: str) -> list[float]:
    vec = np.zeros(4, dtype="float32")
    for i, kw in enumerate(["revenue", "risk", "policy", "invoice"]):
        if kw in text.lower():
            vec[i] = 1.0
    if not vec.any():
        vec[0] = 0.01
    return vec.tolist()


def test_persist_leaves_no_temp_files_and_reloads():
    sections = [
        {
            "document_id": "d1",
            "document_name": "annual_report.pdf",
            "page_number": 2,
            "section_title": "Revenue",
            "content": "Total revenue was 500 million dollars.",
            "content_type": "text",
            "score": 0.8,
        }
    ]
    vector_store.add_sections(sections, [_embed(s["content"]) for s in sections])

    index_dir = get_settings().index_path
    leftovers = list(index_dir.glob("*.tmp"))
    assert leftovers == [], f"atomic persist must not leave temp files: {leftovers}"
    assert (index_dir / "sections.faiss").is_file()
    assert (index_dir / "sections_meta.json").is_file()

    # Force a cold reload from disk and confirm the section is retrievable.
    vector_store._index = None
    vector_store._meta = None
    vector_store._dimension = None
    results = vector_store.search(_embed("revenue"), k=3)
    assert results
    assert results[0][0]["document_name"] == "annual_report.pdf"


# ===========================================================================
# Docker: guard against a compose build context with no Dockerfile
# ===========================================================================
REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"


def _build_contexts(compose: dict) -> list[Path]:
    contexts = []
    for service in compose.get("services", {}).values():
        build = service.get("build")
        if not build:
            continue
        # build may be a string path or a mapping with a `context` key.
        ctx = build if isinstance(build, str) else build.get("context", ".")
        contexts.append((REPO_ROOT / ctx).resolve())
    return contexts


def test_compose_file_exists():
    assert COMPOSE_FILE.is_file(), "docker-compose.yml missing from repo root"


def test_every_build_context_has_a_dockerfile():
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    contexts = _build_contexts(compose)
    assert contexts, "expected at least one service with a build context"
    for ctx in contexts:
        dockerfile = ctx / "Dockerfile"
        assert dockerfile.is_file(), f"build context {ctx} has no Dockerfile"


def test_backend_dockerfile_exposes_the_app():
    dockerfile = (REPO_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    # The compose command runs `uvicorn app.main:app`, so the image must install
    # deps, copy the app package, and provide tesseract for OCR.
    assert "requirements.txt" in dockerfile
    assert "COPY app" in dockerfile
    assert "tesseract-ocr" in dockerfile
