import fitz
import pytest
from docx import Document

from backend.services.parser_service import (
    UnsupportedDocumentTypeError,
    parse_document,
)


def _make_pdf_bytes() -> bytes:
    document = fitz.open()

    first_page = document.new_page()
    first_page.insert_text((72, 72), "Bang gia can ho 2PN")

    second_page = document.new_page()
    second_page.insert_text((72, 72), "Chinh sach thanh toan")

    data = document.tobytes()
    document.close()
    return data


def test_parse_pdf_keeps_page_numbers():
    sections = parse_document("bang-gia.pdf", _make_pdf_bytes())

    assert len(sections) == 2
    assert sections[0].page == 1
    assert "Bang gia" in sections[0].text
    assert sections[1].page == 2


def test_parse_docx_returns_text_without_page(tmp_path):
    path = tmp_path / "chinh-sach.docx"

    document = Document()
    document.add_paragraph("Chinh sach ban hang")
    document.add_paragraph("Ho tro vay ngan hang")
    document.save(path)

    sections = parse_document(path.name, path.read_bytes())

    assert len(sections) == 1
    assert sections[0].page is None
    assert "Chinh sach ban hang" in sections[0].text


def test_parse_rejects_unsupported_extension():
    with pytest.raises(UnsupportedDocumentTypeError):
        parse_document("bang-gia.xlsx", b"not relevant")