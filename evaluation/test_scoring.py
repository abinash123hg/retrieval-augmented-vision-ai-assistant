"""Offline unit tests for the evaluation scoring functions (no Ollama, no backend).

Run with the backend venv, e.g.:
    backend/.venv/Scripts/python.exe -m pytest evaluation/test_scoring.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import evaluate  # noqa: E402


# ----------------------------- numbers_in -----------------------------
def test_numbers_in_normalizes_commas_and_percent():
    assert evaluate.numbers_in("Total 8,450 USD") == {"8450"}
    # '%' is treated as part of the numeric token (comma-insensitive only).
    assert evaluate.numbers_in("growth of 12.5% in 2025") == {"12.5%", "2025"}
    assert evaluate.numbers_in("no numbers here") == set()


def test_content_words_excludes_numeric_tokens():
    # Numbers are checked exactly by numbers_in, so they must not affect overlap.
    assert evaluate.content_words("8450 USD") == {"usd"}
    assert evaluate.content_words("The total is 8,450 USD.") == {"usd"}


# --------------------------- content_words ----------------------------
def test_content_words_drops_stopwords_and_short_tokens():
    words = evaluate.content_words("The total revenue was 500 million dollars")
    assert "revenue" in words and "million" in words and "dollars" in words
    assert "the" not in words and "was" not in words


# ------------------------ answer_is_correct ---------------------------
def test_correct_when_numbers_and_words_present():
    correct, reasons, overlap = evaluate.answer_is_correct(
        "500 million dollars", "Total revenue was 500 million dollars in 2025."
    )
    assert correct is True
    assert reasons == []
    assert overlap >= evaluate.CONTENT_WORD_THRESHOLD


def test_wrong_when_expected_number_missing():
    correct, reasons, _ = evaluate.answer_is_correct(
        "500 million dollars", "Total revenue was 740 million dollars."
    )
    assert correct is False
    assert any("500" in r for r in reasons)


def test_wrong_when_content_word_overlap_below_threshold():
    # Only 1 of 3 content words present -> 33% < 80%.
    correct, reasons, overlap = evaluate.answer_is_correct(
        "currency fluctuation risk", "The report mentions currency only.",
    )
    assert correct is False
    assert overlap < evaluate.CONTENT_WORD_THRESHOLD
    assert any("overlap" in r for r in reasons)


def test_comma_formatting_does_not_break_number_match():
    correct, _, _ = evaluate.answer_is_correct("8450 USD", "The total is 8,450 USD.")
    assert correct is True


def test_forbidden_string_makes_answer_wrong():
    correct, reasons, _ = evaluate.answer_is_correct(
        "500 million dollars",
        "Revenue was 500 million dollars according to my general knowledge.",
        forbidden=["general knowledge"],
    )
    assert correct is False
    assert any("forbidden" in r for r in reasons)


def test_no_expected_numbers_passes_number_check():
    correct, reasons, _ = evaluate.answer_is_correct(
        "Beta Module", "The Beta Module led catalog sales."
    )
    assert correct is True
    assert reasons == []


# --------------------------- has_source_leak --------------------------
def test_detects_evidence_block_and_source_tags():
    assert evaluate.has_source_leak("as stated in the Evidence Block") is True
    assert evaluate.has_source_leak("see [Source 1] for details") is True
    assert evaluate.has_source_leak("Sources used for this answer: report.pdf") is True


def test_detects_citation_bullet_line():
    assert evaluate.has_source_leak("Revenue was 500M.\n* report.pdf - page 2") is True


def test_clean_answer_has_no_leak():
    assert evaluate.has_source_leak("Total revenue was 500 million dollars in 2025.") is False
    assert evaluate.has_source_leak("") is False


# --------------------------- retrieval_hit ----------------------------
def test_retrieval_hit_returns_rank():
    sections = [
        {"document_id": "d1", "page_number": 1},
        {"document_id": "d1", "page_number": 2},
    ]
    assert evaluate.retrieval_hit(sections, "d1", 2) == (True, 2)
    assert evaluate.retrieval_hit(sections, "d1", 9) == (False, 0)
    assert evaluate.retrieval_hit(sections, "d1", None) == (False, 0)


# ---------------------------- citation_hit ----------------------------
class _Src:
    def __init__(self, name, page):
        self.document_name = name
        self.page_number = page


def test_citation_hit_matches_stem_and_page():
    sources = [_Src("annual_report.pdf", 2)]
    assert evaluate.citation_hit(sources, "annual_report.pdf", 2) is True
    assert evaluate.citation_hit(sources, "annual_report.pdf", 3) is False
    assert evaluate.citation_hit(sources, "annual_report.pdf", None) is False


# ------------------------------ scope_for -----------------------------
def test_scope_for_scoped_and_unscoped():
    name_to_id = {"a.pdf": "id-a", "b.pdf": "id-b"}
    q = {"document": "a.pdf", "category": "direct_factual"}
    assert evaluate.scope_for(q, name_to_id) == ["id-a"]
    assert evaluate.scope_for(q, name_to_id, unscoped=True) is None
    multi = {"document": "a.pdf", "category": "multi_document"}
    assert set(evaluate.scope_for(multi, name_to_id)) == {"id-a", "id-b"}


# --------------------------- metric / frac ----------------------------
def test_metric_and_frac_handle_zero_denominator():
    assert evaluate.frac(1, 2) == 0.5
    assert evaluate.frac(1, 0) == 0.0
    assert evaluate.metric(3, 4) == {"correct": 3, "total": 4, "rate": 0.75}
    assert evaluate.metric(0, 0) == {"correct": 0, "total": 0, "rate": 0.0}
