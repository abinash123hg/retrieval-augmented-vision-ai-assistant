import fitz
import pytest
from PIL import Image, ImageDraw

from app.services import ocr_service, pdf_service


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


@pytest.mark.skipif(not ocr_service.is_available(), reason="Tesseract not installed")
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


@pytest.mark.skipif(not ocr_service.is_available(), reason="Tesseract not installed")
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
