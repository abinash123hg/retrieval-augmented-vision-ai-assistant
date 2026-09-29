from app.services import answer_service, citation_service, verification_service

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
    status, passed, warnings = verification_service.verify(
        verification_service.REFUSAL_SENTENCE, []
    )
    assert status == "not_found"
    assert passed


def test_empty_answer_is_rejected():
    status, _, _ = verification_service.verify("   ", SECTIONS)
    assert status == "not_found"


def test_grounded_numbers_pass_as_supported():
    status, passed, warnings = verification_service.verify(
        "Total revenue was 500 million dollars in 2025 (annual_report.pdf, page 2).",
        SECTIONS,
    )
    assert status == "supported"
    assert passed
    assert not any("rejected" in w for w in warnings)


def test_invented_number_rejects_the_answer():
    status, passed, warnings = verification_service.verify(
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
    status, _, _ = verification_service.verify("The total is 8,450 USD.", sections)
    assert status == "supported"


def test_text_answer_without_numbers_is_supported():
    status, _, _ = verification_service.verify(
        "The report describes the company's revenue performance.", SECTIONS
    )
    assert status == "supported"


def test_ocr_evidence_warning_is_internal():
    _, _, warnings = verification_service.verify(
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
    sources = citation_service.build_sources(many)
    assert len(sources) == 2
    assert sources[0].page_number == 2
    assert sources[1].page_number == 3


def test_parse_strips_answer_label_and_sources_block():
    raw = (
        "Answer:\nThe total revenue was 500 million dollars.\n\n"
        "Sources used for this answer\n* annual_report.pdf – Page 2"
    )
    answer = answer_service._parse_response(raw)
    assert answer == "The total revenue was 500 million dollars."


def test_parse_tolerates_plain_text():
    assert answer_service._parse_response("Short reply only.") == "Short reply only."


def test_system_prompt_contains_exact_refusal_sentence():
    assert verification_service.REFUSAL_SENTENCE in answer_service.SYSTEM_PROMPT
