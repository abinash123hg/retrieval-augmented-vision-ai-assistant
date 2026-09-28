"""Downloadable answer reports (PDF via ReportLab)."""

import uuid
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from ..config import get_settings
from ..core.errors import ReportGenerationError
from ..core.logging_config import get_logger
from ..core.security import is_within_directory
from ..models.schemas import ReportRequest

logger = get_logger(__name__)

EVIDENCE_LABELS = {
    "supported": "Supported",
    "partially_supported": "Partially supported",
    "not_found": "Not found",
    "conflicting_sources": "Conflicting sources",
    "low_quality_source": "Low-quality source",
}


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def generate_report(request: ReportRequest) -> tuple[str, str, Path]:
    settings = get_settings()
    report_id = uuid.uuid4().hex
    file_name = f"doculens-report-{report_id[:8]}.pdf"
    path = settings.report_path / file_name

    try:
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("DLTitle", parent=styles["Title"], textColor=colors.HexColor("#1D4ED8"))
        heading_style = ParagraphStyle("DLHeading", parent=styles["Heading2"], textColor=colors.HexColor("#0F172A"), spaceBefore=8)
        body_style = ParagraphStyle("DLBody", parent=styles["BodyText"], fontSize=10, leading=14, textColor=colors.HexColor("#0F172A"))
        meta_style = ParagraphStyle("DLMeta", parent=styles["BodyText"], fontSize=9, textColor=colors.HexColor("#64748B"))

        doc = SimpleDocTemplate(
            str(path), pagesize=A4,
            leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
            title="DocuLens Report",
        )
        story = [
            Paragraph("DocuLens Report", title_style),
            Paragraph(
                f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", meta_style
            ),
            HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E2E8F0"), spaceAfter=10),
            Paragraph("Question", heading_style),
            Paragraph(_escape(request.question), body_style),
            Paragraph("Answer", heading_style),
            Paragraph(_escape(request.answer).replace("\n", "<br/>"), body_style),
            Paragraph(
                f"Evidence status: {EVIDENCE_LABELS.get(request.evidence_status, request.evidence_status)}",
                meta_style,
            ),
            Paragraph("Sources used for this answer", heading_style),
        ]
        if request.sources:
            for source in request.sources:
                location = f"{_escape(source.document_name)} — page {source.page_number}"
                if source.section:
                    location += f" — {_escape(source.section)}"
                story.append(Paragraph(location, body_style))
                story.append(Paragraph(_escape(source.excerpt), meta_style))
                story.append(Spacer(1, 6))
        else:
            story.append(Paragraph("No sources were used for this answer.", meta_style))

        doc.build(story)
    except Exception as exc:
        logger.error("Report generation failed: %s", exc)
        path.unlink(missing_ok=True)
        raise ReportGenerationError() from exc

    return report_id, file_name, path


def report_file(report_id: str) -> Path:
    settings = get_settings()
    if not report_id.isalnum():
        raise ReportGenerationError("This report is no longer available.")
    matches = list(settings.report_path.glob(f"*{report_id[:8]}*.pdf"))
    if not matches:
        raise ReportGenerationError("This report is no longer available.")
    path = matches[0]
    if not is_within_directory(path, settings.report_path):
        raise ReportGenerationError("This report is no longer available.")
    return path
