import re
from dataclasses import dataclass

from backend.services.parser_service import ParsedSection

SECTION_BOUNDARY_RE = re.compile(
    r"\n\s*\n|(?=\n(?:[IVXLCDM]+|\d+)\.\s+)"
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
        raise ValueError(
            "overlap_chars must be >= 0 and smaller than chunk_chars"
        )

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
ROMAN_HEADING_RE = re.compile(r"^[IVXLCDM]+\.\s+[^\n]+$")
NUMBER_HEADING_RE = re.compile(r"^\d+\.\s+[^\n]+$")
ALPHA_HEADING_RE = re.compile(r"^[a-z]\.\s+[^\n]+$", re.IGNORECASE)

def _split_text(
    text: str,
    *,
    chunk_chars: int,
    overlap_chars: int,
) -> list[str]:
    """Split text while maintaining a 3-level context breadcrumb (I. -> 1. -> a.)."""
    if not text or not text.strip():
        return []

    blocks = [
        block.strip()
        for block in SECTION_BOUNDARY_RE.split(text)
        if block.strip()
    ]

    result: list[str] = []
    current = ""

    # Storage for the 3-level context
    roman_header = ""
    number_header = ""
    active_header = ""

    for block in blocks:
        # Level 1: Roman numeral sections (I., II.)
        if ROMAN_HEADING_RE.match(block):
            if current:
                result.append(current)
                current = ""
            roman_header = block
            number_header = ""  # Reset the lower level when entering a new Roman section
            continue

        # Level 2: numbered sections (1., 2.)
        if NUMBER_HEADING_RE.match(block):
            # If the numbered block is very short (heading only), use it as the level-2 header
            lines = block.split("\n")
            number_header = lines[0]

        # Build the full active header as a breadcrumb
        headers = [h for h in (roman_header, number_header) if h]
        active_header = " > ".join(headers) if headers else ""

        current = _append_block(
            result=result,
            current=current,
            block=block,
            active_header=active_header,
            chunk_chars=chunk_chars,
            overlap_chars=overlap_chars,
        )

    if not current:
        trailing_headers = [
            header
            for header in (roman_header, number_header)
            if header
        ]
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
    """Take a prefix no longer than limit, preferring to cut at a newline or space."""
    if len(text) <= limit:
        return text, ""

    newline_boundary = text.rfind("\n", 0, limit + 1)
    space_boundary = text.rfind(" ", 0, limit + 1)
    boundary = max(newline_boundary, space_boundary)

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
