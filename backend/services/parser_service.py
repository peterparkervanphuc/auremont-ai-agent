from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import fitz
from docx import Document as DocxDocument


@dataclass(frozen=True)
class ParsedSection:
    """A block of text extracted from a source document.

    PDFs keep their page number (1-based); DOCX has no stable notion of a page,
    so None is used there.
    """

    text: str
    page: int | None


class UnsupportedDocumentTypeError(ValueError):
    """The file is not in a format the pipeline supports."""


class DocumentParseError(ValueError):
    """The file is corrupt or no text could be extracted from it."""


def parse_document(filename: str, data: bytes) -> list[ParsedSection]:
    """Parse PDF/DOCX straight from bytes, with no dependency on a temp file on disk."""
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
