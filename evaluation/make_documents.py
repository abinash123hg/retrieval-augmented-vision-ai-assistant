"""Generate the synthetic evaluation document `maintenance_manual.pdf`.

This is a fixture generator for the evaluation set — the content is entirely
fictional (a made-up company, a reserved `.example` support address, no real
person or patient data). It exists so the evaluation corpus has more than the
original 3 tiny samples and reaches >= 30 groundable questions. Ground-truth
answers for the questions in questions.json are taken verbatim from the text
written here, so nothing is fabricated: the expected answer is literally the
string in the document.

Run:  python evaluation/make_documents.py
"""
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate

OUT = Path(__file__).resolve().parent / "documents" / "maintenance_manual.pdf"

PAGES = [
    [
        "Meridian Labs - Equipment Maintenance Manual",
        "Document ID: MM-2025-07",
        "Revision: 3",
        "Issue date: 12 March 2025",
        "The pressure valve must be replaced after 4500 operating hours.",
        "The inspection interval is every 90 days.",
    ],
    [
        "Spare Parts and Costs",
        "Filter Cartridge, part number FC-101, costs 45 USD.",
        "Seal Ring, part number SR-202, costs 18 USD.",
        "Pressure Valve, part number PV-303, costs 320 USD.",
        "The recommended spare-parts budget for 2025 is 3800 USD.",
    ],
    [
        "Warranty and Support",
        "The warranty period is 24 months from the issue date.",
        "Support is available on weekdays only.",
        "The service hotline operates from 9 AM to 5 PM.",
        "Support email: support@meridianlabs.example",
    ],
]


def build() -> None:
    styles = getSampleStyleSheet()
    title = styles["Title"]
    body = styles["Normal"]
    doc = SimpleDocTemplate(
        str(OUT), pagesize=letter, topMargin=inch, bottomMargin=inch
    )
    story = []
    for i, page_lines in enumerate(PAGES):
        if i > 0:
            story.append(PageBreak())
        for j, line in enumerate(page_lines):
            story.append(Paragraph(line, title if j == 0 else body))
    doc.build(story)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    build()
