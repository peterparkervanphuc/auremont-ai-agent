import re
from dataclasses import dataclass

from backend.services.parser_service import ParsedSection

# PDFs in MinIO are primarily sales policies and legal documents.  Their text is
# extracted line-by-line, often without useful blank paragraphs, so section-aware
# boundaries are more reliable than a fixed character window.
SECTION_BOUNDARY_RE = re.compile(
    r"\n\s*\n|(?=\n\s*(?:CHƯƠNG\s+[IVXLCDM0-9]+\b|ĐIỀU\s+\d+\b|"
    r"[IVXLCDM]+\.\s+|\d+\.\s+|[a-zđ]\.\s+))",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class DocumentChunk:
    """A block of text ready to be embedded and stored in Qdrant."""

    index: int
    text: str
    page: int | None


def chunk_sections(
    sections: list[ParsedSection],
    *,
    chunk_chars: int = 3200,
    overlap_chars: int = 400,
) -> list[DocumentChunk]:
    if chunk_chars <= 0:
        raise ValueError("chunk_chars must be greater than 0")

    if overlap_chars < 0 or overlap_chars >= chunk_chars:
        raise ValueError("overlap_chars must be >= 0 and smaller than chunk_chars")

    chunks: list[DocumentChunk] = []

    for section in sections:
        for text in _split_text(
            section.text,
            chunk_chars=chunk_chars,
            overlap_chars=overlap_chars,
        ):
            chunks.append(
                DocumentChunk(
                    index=len(chunks),
                    text=text,
                    page=section.page,
                )
            )

    return chunks


# Regexes recognising the additional heading levels
ROMAN_HEADING_RE = re.compile(r"^[IVXLCDM]+\.\s+[^\n]+$", re.IGNORECASE)
NUMBER_HEADING_RE = re.compile(r"^\d+\.\s+[^\n]+$")
ALPHA_HEADING_RE = re.compile(r"^[a-zđ]\.\s+[^\n]+$", re.IGNORECASE)
CHAPTER_HEADING_RE = re.compile(r"^CHƯƠNG\s+[IVXLCDM0-9]+\b[^\n]*$", re.IGNORECASE)
ARTICLE_HEADING_RE = re.compile(r"^ĐIỀU\s+\d+\b[^\n]*$", re.IGNORECASE)
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
BULLET_RE = re.compile(r"^\s*(?:[-•*]|\(?[a-zđ]\)|\d+\))\s+", re.IGNORECASE)


def _split_text(
    text: str,
    *,
    chunk_chars: int,
    overlap_chars: int,
) -> list[str]:
    """Split text while maintaining a 3-level context breadcrumb (I. -> 1. -> a.)."""
    if not text or not text.strip():
        return []

    text = _normalise_extracted_text(text)
    raw_blocks = [block.strip() for block in SECTION_BOUNDARY_RE.split(text) if block.strip()]
    blocks = [item for block in raw_blocks for item in _separate_inline_headings(block)]

    result: list[str] = []
    current = ""

    # Storage for the 3-level context
    roman_header = ""
    number_header = ""
    active_header = ""

    for block in blocks:
        # Level 1: Roman numeral sections (I., II.)
        if ROMAN_HEADING_RE.match(block) or CHAPTER_HEADING_RE.match(block):
            if current:
                result.append(current)
                current = ""
            roman_header = block
            number_header = ""  # Reset the lower level when entering a new Roman section
            continue

        # Level 2: numbered sections (1., 2.)
        if NUMBER_HEADING_RE.match(block) or ARTICLE_HEADING_RE.match(block):
            # Start a fresh chunk under the new clause.  Otherwise a large
            # preceding section could consume the context and leave the next
            # chunk with a discount/payment value but no clause label.
            if current:
                result.append(current)
                current = ""
            number_header = block
            continue

        if ALPHA_HEADING_RE.match(block):
            if current:
                result.append(current)
                current = ""
            # Keep the numeric level and add the nested legal/policy clause.
            number_header = f"{number_header} > {block}" if number_header else block
            continue

        # Build the full active header as a breadcrumb
        headers = [h for h in (roman_header, number_header) if h]
        active_header = " > ".join(headers) if headers else ""

        for logical_block in _split_logical_block(block):
            current = _append_block(
                result=result,
                current=current,
                block=logical_block,
                active_header=active_header,
                chunk_chars=chunk_chars,
                overlap_chars=overlap_chars,
            )

    if not current:
        trailing_headers = [header for header in (roman_header, number_header) if header]
        trailing_header = " > ".join(trailing_headers)

        if trailing_header:
            current = trailing_header[:chunk_chars]

    if current:
        result.append(current)

    return result


def _append_block(
    *,
    result: list[str],
    current: str,
    block: str,
    active_header: str,
    chunk_chars: int,
    overlap_chars: int,
) -> str:
    """Append a block to the current chunk, splitting it further when needed."""
    remaining = block.strip()

    while remaining:
        if not current:
            current = _start_chunk(
                active_header=active_header,
                previous_chunk=result[-1] if result else "",
                chunk_chars=chunk_chars,
                overlap_chars=overlap_chars,
            )

        separator = "\n\n" if current else ""
        available = chunk_chars - len(current) - len(separator)

        # The current chunk is full: flush it and open a new one.
        if available <= 0:
            result.append(current)
            current = ""
            continue

        piece, remaining = _take_prefix(remaining, available)
        current = f"{current}{separator}{piece}" if current else piece

        # Text still does not fit, so close the current chunk.
        if remaining:
            result.append(current)
            current = ""

    return current


def _start_chunk(
    *,
    active_header: str,
    previous_chunk: str,
    chunk_chars: int,
    overlap_chars: int,
) -> str:
    """Start a new chunk, repeating the heading and overlap within the allowed limit."""
    header = active_header.strip()

    # An over-long heading must still not push the chunk past its limit.
    if len(header) >= chunk_chars:
        return header[:chunk_chars]

    overlap_budget = chunk_chars - len(header) - 2
    overlap = _tail(previous_chunk, min(overlap_chars, overlap_budget))

    if header and overlap:
        return f"{header}\n{overlap}"

    return header or overlap


def _take_prefix(text: str, limit: int) -> tuple[str, str]:
    """Take a prefix at a semantic boundary before falling back to a word cut."""
    if len(text) <= limit:
        return text, ""

    # Do not cut a bullet/list item or an extracted table row in half.  This is
    # especially important for discount and payment-schedule tables in CSBH PDFs.
    newline_boundary = text.rfind("\n", 0, limit + 1)
    sentence_boundary = max(
        text.rfind(". ", 0, limit + 1),
        text.rfind("; ", 0, limit + 1),
        text.rfind(": ", 0, limit + 1),
    )
    space_boundary = text.rfind(" ", 0, limit + 1)
    boundary = max(newline_boundary, sentence_boundary + 1, space_boundary)

    # A single over-long word or line: force a hard cut to avoid an infinite loop.
    if boundary <= 0:
        boundary = limit

    prefix = text[:boundary].strip()
    remainder = text[boundary:].strip()

    # Guard against the boundary landing on leading whitespace.
    if not prefix:
        prefix = text[:limit].strip()
        remainder = text[limit:].strip()

    return prefix, remainder


def _normalise_extracted_text(text: str) -> str:
    """Make PDF extraction stable without flattening legal/article structure.

    Some PDFs use non-breaking spaces and produce several empty lines around a
    page header/footer.  We retain all meaningful lines (including legal numbers
    and tables) while collapsing that extraction noise.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_logical_block(block: str) -> list[str]:
    """Keep tables and lists intact as units before character-level splitting.

    A policy PDF usually contains discount/payment tables and nested bullet terms.
    Treating each row/item as a unit gives retrieval a complete business rule
    instead of an orphan amount, while `_append_block` still enforces the size cap.
    """
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if not lines:
        return []

    groups: list[list[str]] = []
    current: list[str] = []
    current_kind = "text"

    for line in lines:
        kind = "table" if TABLE_ROW_RE.match(line) else "bullet" if BULLET_RE.match(line) else "text"
        # Consecutive rows/items stay together.  A new row/item after prose starts
        # a fresh logical unit so it can never be split in the middle by default.
        if current and kind != current_kind and (kind != "text" or current_kind != "text"):
            groups.append(current)
            current = []
        current.append(line)
        current_kind = kind

    if current:
        groups.append(current)

    return ["\n".join(group) for group in groups]


def _separate_inline_headings(block: str) -> list[str]:
    """Split a PDF block when its heading and body share the same paragraph.

    PyMuPDF commonly returns `I. ...` followed by its body on the next line,
    without a blank paragraph.  Splitting it here lets the heading become a
    breadcrumb instead of embedding it only in the first chunk of a section.
    """
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if not lines:
        return []

    parts: list[str] = []
    body: list[str] = []
    for line in lines:
        if _is_heading_line(line):
            if body:
                parts.append("\n".join(body))
                body = []
            parts.append(line)
        else:
            body.append(line)
    if body:
        parts.append("\n".join(body))
    return parts


def _is_heading_line(line: str) -> bool:
    if CHAPTER_HEADING_RE.match(line) or ARTICLE_HEADING_RE.match(line):
        return True
    if ROMAN_HEADING_RE.match(line):
        return True
    # Numeric/alpha clauses are headings only when they are short labels.  A
    # full legal sentence beginning with "1." remains content, not a breadcrumb.
    return len(line) <= 100 and (NUMBER_HEADING_RE.match(line) is not None or ALPHA_HEADING_RE.match(line) is not None)


def _tail(text: str, limit: int) -> str:
    """Take a suffix to use as overlap, preferring to start at a word boundary."""
    if limit <= 0 or not text:
        return ""

    if len(text) <= limit:
        return text.strip()

    tail = text[-limit:]
    first_space = tail.find(" ")
    first_newline = tail.find("\n")
    boundaries = [item for item in (first_space, first_newline) if item >= 0]

    if boundaries:
        tail = tail[min(boundaries) + 1 :]

    return tail.strip()
