import pytest

from app.core.errors import FileTooLargeError, InvalidFileError
from app.services import file_service

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< >>\nendobj\ntrailer\n<<>>\n%%EOF\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def test_save_valid_pdf():
    document_id, path = file_service.save_upload("report.pdf", PDF_BYTES)
    assert path.exists()
    doc = file_service.get_document(document_id)
    assert doc.file_name == "report.pdf"
    assert doc.file_type == "pdf"
    assert doc.processing_status == "waiting"


def test_save_valid_png():
    document_id, _ = file_service.save_upload("scan.png", PNG_BYTES)
    assert file_service.get_document(document_id).file_type == "image"


def test_reject_unsupported_extension():
    with pytest.raises(InvalidFileError):
        file_service.save_upload("notes.txt", b"hello")


def test_reject_empty_file():
    with pytest.raises(InvalidFileError):
        file_service.save_upload("empty.pdf", b"")


def test_reject_oversized_file():
    with pytest.raises(FileTooLargeError):
        file_service.save_upload("big.pdf", PDF_BYTES + b"x" * (2 * 1024 * 1024))


def test_filename_is_sanitized():
    document_id, path = file_service.save_upload("../../etc/passwd.pdf", PDF_BYTES)
    doc = file_service.get_document(document_id)
    assert "/" not in doc.file_name and "\\" not in doc.file_name
    from app.config import get_settings
    from app.core.security import is_within_directory

    assert is_within_directory(path, get_settings().upload_path)


def test_list_and_delete():
    document_id, _ = file_service.save_upload("a.pdf", PDF_BYTES)
    assert any(d.id == document_id for d in file_service.list_documents())
    file_service.delete_document(document_id)
    assert not any(d.id == document_id for d in file_service.list_documents())
    with pytest.raises(Exception):
        file_service.get_document(document_id)
