import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import fitz
from docx import Document as DocxDocument

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParsedSection:
    """A block of text extracted from a source document.

    PDFs keep their page number (1-based); DOCX has no stable notion of a page,
    so None is used there.
    """

    text: str
    page: int | None
    # (character offset into `text`, Y position in PDF points measured from the page's
    # TOP) breakpoints, sorted by offset ascending — empty for DOCX, which has no page
    # geometry at all. Lets a downstream chunk look up roughly where on the page its own
    # text starts, so a citation can scroll a PDF viewer to that spot instead of just the
    # top of the page (see chunking_service._estimate_y_position and
    # CitationList.tsx's `withPageAnchor`, which is where this actually gets used).
    #
    # Deliberately a side channel rather than a change to how `text` itself is extracted:
    # `text` still comes from the exact same `page.get_text("text")` call as before, so
    # chunking_service's section-boundary regexes see byte-for-byte what they always have.
    # This is computed from a SEPARATE `page.get_text("blocks")` call and correlated back
    # onto `text` by searching for each block's own content in it — best-effort, since the
    # two extraction modes don't guarantee identical whitespace; a block that can't be
    # located is simply dropped from this list rather than raising.
    block_offsets: tuple[tuple[int, float], ...] = ()


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
            sections = []
            for page_index, page in enumerate(pdf):
                page_text = page.get_text("text").strip()
                if not page_text:
                    continue
                sections.append(
                    ParsedSection(
                        text=page_text,
                        page=page_index + 1,
                        block_offsets=_block_offsets(page, page_text),
                    )
                )
    except Exception as exc:
        logger.exception(
            "PDF parsing failed.",
            extra={"event": "parser.pdf.failed", "size_bytes": len(data)},
        )
        raise DocumentParseError("Could not parse PDF.") from exc

    if not sections:
        raise DocumentParseError("PDF contains no extractable text. OCR is not supported yet.")

    return sections


def _block_offsets(page: "fitz.Page", page_text: str) -> tuple[tuple[int, float], ...]:
    """Best-effort (offset into `page_text`, Y-from-top in PDF points) breakpoints.

    `page.get_text("blocks")` gives each visual block's bounding box; `y0` (top edge,
    increasing downward — verified against this project's own PDFs, not assumed) is what
    a citation later scrolls a viewer to. Matched onto `page_text` by searching for each
    block's own first line: blocks mode and text mode don't promise identical whitespace,
    so a block whose text can't be found is just skipped — that block's chunk falls back
    to page-top on citation, exactly today's behaviour, rather than raising.
    """
    breakpoints: list[tuple[int, float]] = []
    for block in page.get_text("blocks"):
        x0, y0, x1, y1, block_text, block_no, block_type = block
        if block_type != 0:  # 0 = text block; images/other types have no text to anchor
            continue
        first_line = block_text.strip().splitlines()[0].strip() if block_text.strip() else ""
        if not first_line:
            continue
        offset = page_text.find(first_line)
        if offset >= 0:
            breakpoints.append((offset, y0))
    breakpoints.sort(key=lambda item: item[0])
    return tuple(breakpoints)


def _parse_docx(data: bytes) -> list[ParsedSection]:
    try:
        document = DocxDocument(BytesIO(data))
        paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs]
        text = "\n".join(item for item in paragraphs if item)
    except Exception as exc:
        logger.exception(
            "DOCX parsing failed.",
            extra={"event": "parser.docx.failed", "size_bytes": len(data)},
        )
        raise DocumentParseError("Could not parse DOCX.") from exc

    if not text:
        raise DocumentParseError("DOCX contains no extractable text.")

    return [ParsedSection(text=text, page=None)]
