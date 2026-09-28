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
        verification_service.REFUSAL_SENTENCE, "Not found", []
    )
    assert status == "not_found"
    assert passed


def test_supported_answer_with_matching_numbers():
    status, passed, warnings = verification_service.verify(
        "Total revenue was 500 million dollars in 2025 (annual_report.pdf, page 2).",
        "Supported",
        SECTIONS,
    )
    assert status == "supported"
    assert passed
    assert not any("not found in the retrieved evidence" in w for w in warnings)


def test_invented_number_is_flagged():
    status, passed, warnings = verification_service.verify(
        "Total revenue was 740 million dollars.", "Supported", SECTIONS
    )
    assert status == "partially_supported"
    assert any("740" in w for w in warnings)


def test_status_mapping():
    assert verification_service.map_evidence_status("Supported") == "supported"
    assert verification_service.map_evidence_status("Partially supported") == "partially_supported"
    assert verification_service.map_evidence_status("Not found") == "not_found"
    assert verification_service.map_evidence_status("Conflicting sources") == "conflicting_sources"
    assert verification_service.map_evidence_status("Low-quality source") == "low_quality_source"


def test_conflict_warning_added():
    status, passed, warnings = verification_service.verify(
        "One report says 500 million, the other says 480 million.",
        "Conflicting sources",
        SECTIONS,
    )
    assert status == "conflicting_sources"
    assert any("conflicting" in w.lower() for w in warnings)


def test_ocr_evidence_warning():
    _, _, warnings = verification_service.verify(
        "Operating costs reached 310 million dollars.", "Supported", SECTIONS
    )
    assert any("OCR" in w for w in warnings)


def test_citations_only_from_sections():
    sources = citation_service.build_sources(SECTIONS)
    assert len(sources) == 2
    assert sources[0].document_name == "annual_report.pdf"
    assert sources[0].page_number == 2
    assert sources[0].section == "Revenue"
    assert sources[0].excerpt


def test_parse_model_response():
    raw = """Answer:
The total revenue was 500 million dollars (annual_report.pdf, page 2).

Evidence status:
Supported

Sources:
- annual_report.pdf, page 2, Revenue"""
    answer, status = answer_service._parse_response(raw)
    assert answer.startswith("The total revenue was 500")
    assert status.lower() == "supported"


def test_parse_tolerates_missing_sections():
    answer, status = answer_service._parse_response("Answer:\nShort reply only.")
    assert answer == "Short reply only."
    assert status == ""
