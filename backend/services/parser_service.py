import logging
from collections.abc import Iterator
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import fitz
from docx import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

logger = logging.getLogger(__name__)


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
        f"Unsupported file type: {suffix or '(no extension)'}. Only .pdf and .docx are supported."
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
        logger.exception(
            "PDF parsing failed.",
            extra={"event": "parser.pdf.failed", "size_bytes": len(data)},
        )
        raise DocumentParseError("Could not parse PDF.") from exc

    if not sections:
        raise DocumentParseError("PDF contains no extractable text. OCR is not supported yet.")

    return sections


def _parse_docx(data: bytes) -> list[ParsedSection]:
    """Extract prose AND tables, in the order they appear in the document.

    `document.paragraphs` skips tables entirely. For this corpus that is not a detail:
    discount tiers, payment schedules and price rows in a .docx CSBH live in tables and
    nowhere else, so reading only paragraphs ingests the file "successfully" while every
    figure in it silently disappears — the worst possible failure, because nothing looks
    wrong until a Sale is told the policy has no discount data.
    """
    try:
        document = DocxDocument(BytesIO(data))
        blocks = []
        for item in _iter_block_items(document):
            rendered = _render_table(item) if isinstance(item, Table) else " ".join(item.text.split())
            if rendered:
                blocks.append(rendered)
        text = "\n\n".join(blocks)
    except Exception as exc:
        logger.exception(
            "DOCX parsing failed.",
            extra={"event": "parser.docx.failed", "size_bytes": len(data)},
        )
        raise DocumentParseError("Could not parse DOCX.") from exc

    if not text:
        raise DocumentParseError("DOCX contains no extractable text.")

    return [ParsedSection(text=text, page=None)]


def _iter_block_items(document) -> Iterator[Paragraph | Table]:
    """Walk the document body in reading order.

    python-docx exposes `.paragraphs` and `.tables` as two separate flat lists, which
    loses the interleaving. A discount table has to stay attached to the clause that
    introduces it, otherwise the chunk carrying the numbers has no idea what they apply to.
    """
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _render_table(table: Table) -> str:
    """Render a table as pipe-delimited rows with a header separator.

    This is the shape `chunking_service` already recognises (`TABLE_ROW_RE`), so a Word
    table lands in the same table-aware path as a Markdown one: split only between rows,
    with the column header repeated in every chunk.
    """
    rows: list[str] = []
    for row in table.rows:
        cells = [" ".join(cell.text.split()) for cell in row.cells]
        if not any(cells):
            continue
        rows.append("| " + " | ".join(cells) + " |")

    if not rows:
        return ""

    column_count = rows[0].count("|") - 1
    separator = "| " + " | ".join(["---"] * column_count) + " |"
    return "\n".join([rows[0], separator, *rows[1:]])
