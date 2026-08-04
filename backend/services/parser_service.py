from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import fitz
from docx import Document as DocxDocument


@dataclass(frozen=True)
class ParsedSection:
    """Một đoạn text lấy từ tài liệu gốc.

    PDF giữ số trang (bắt đầu từ 1); DOCX không có khái niệm trang ổn định
    nên dùng None.
    """

    text: str
    page: int | None


class UnsupportedDocumentTypeError(ValueError):
    """File không phải định dạng mà pipeline hỗ trợ."""


class DocumentParseError(ValueError):
    """File bị hỏng hoặc không thể trích xuất text."""


def parse_document(filename: str, data: bytes) -> list[ParsedSection]:
    """Parse PDF/DOCX từ bytes, không phụ thuộc vào file tạm trên ổ đĩa."""
    suffix = Path(filename).suffix.lower()

    if suffix == ".pdf":
        return _parse_pdf(data)

    if suffix == ".docx":
        return _parse_docx(data)

    raise UnsupportedDocumentTypeError(
        f"Unsupported file type: {suffix or '(no extension)'}. "
        "Only .pdf and .docx are supported."
    )


def _parse_pdf(data: bytes) -> list[ParsedSection]:
    try:
        with fitz.open(stream=data, filetype="pdf") as pdf:
            sections = [
                ParsedSection(
                    text=page.get_text("text").strip(),
                    page=page_index + 1,
                )
                for page_index, page in enumerate(pdf)
                if page.get_text("text").strip()
            ]
    except Exception as exc:
        raise DocumentParseError("Could not parse PDF.") from exc

    if not sections:
        raise DocumentParseError(
            "PDF contains no extractable text. OCR is not supported yet."
        )

    return sections


def _parse_docx(data: bytes) -> list[ParsedSection]:
    try:
        document = DocxDocument(BytesIO(data))
        paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs]
        text = "\n".join(item for item in paragraphs if item)
    except Exception as exc:
        raise DocumentParseError("Could not parse DOCX.") from exc

    if not text:
        raise DocumentParseError("DOCX contains no extractable text.")

    return [ParsedSection(text=text, page=None)]