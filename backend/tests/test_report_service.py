import pytest

from app.core.errors import ReportNotFoundError
from app.models.schemas import ReportRequest, SourceOut
from app.services import report_service


def _request() -> ReportRequest:
    return ReportRequest(
        question="What was the total revenue?",
        answer="Total revenue was 500 million dollars in 2025.",
        evidence_status="supported",
        sources=[
            SourceOut(
                document_name="annual_report.pdf",
                page_number=2,
                section="Revenue",
                excerpt="Total revenue was 500 million dollars in 2025.",
                score=0.81,
            )
        ],
    )


def test_generated_report_is_retrievable_by_full_id():
    report_id, file_name, path = report_service.generate_report(_request())
    assert path.is_file()
    assert report_id in file_name
    assert report_service.report_file(report_id) == path


def test_report_file_rejects_unknown_id():
    with pytest.raises(ReportNotFoundError):
        report_service.report_file("0" * 32)


def test_report_file_rejects_malformed_id():
    # 8-char prefixes used to collide via a glob; they must now be rejected.
    with pytest.raises(ReportNotFoundError):
        report_service.report_file("abcd1234")


def test_report_file_rejects_path_traversal():
    with pytest.raises(ReportNotFoundError):
        report_service.report_file("../../etc/passwd".ljust(32, "0"))
