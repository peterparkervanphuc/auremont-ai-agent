import re
from dataclasses import dataclass

from backend.services.parser_service import ParsedSection


SECTION_BOUNDARY_RE = re.compile(
    r"\n\s*\n|(?=\n(?:[IVXLCDM]+|\d+)\.\s+)"
)


@dataclass(frozen=True)
class DocumentChunk:
    """Một đoạn văn bản sẵn sàng để embedding và lưu Qdrant."""

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


# Regex nhận diện thêm các cấp tiêu đề
ROMAN_HEADING_RE = re.compile(r"^[IVXLCDM]+\.\s+[^\n]+$")
NUMBER_HEADING_RE = re.compile(r"^\d+\.\s+[^\n]+$")
ALPHA_HEADING_RE = re.compile(r"^[a-z]\.\s+[^\n]+$", re.IGNORECASE)

def _split_text(
    text: str,
    *,
    chunk_chars: int,
    overlap_chars: int,
) -> list[str]:
    """Tách text và quản lý Breadcrumb Ngữ cảnh 3 cấp (I. -> 1. -> a.)."""
    if not text or not text.strip():
        return []

    blocks = [
        block.strip()
        for block in SECTION_BOUNDARY_RE.split(text)
        if block.strip()
    ]

    result: list[str] = []
    current = ""
    
    # Bộ lưu trữ ngữ cảnh 3 cấp
    roman_header = ""
    number_header = ""
    active_header = ""

    for block in blocks:
        # Cấp 1: Mục La Mã (I., II.)
        if ROMAN_HEADING_RE.match(block):
            if current:
                result.append(current)
                current = ""
            roman_header = block
            number_header = ""  # Reset cấp nhỏ hơn khi sang Mục La Mã mới
            continue

        # Cấp 2: Mục số (1., 2.)
        if NUMBER_HEADING_RE.match(block):
            # Nếu block mục số quá ngắn (chỉ có tiêu đề), gán làm header cấp 2
            lines = block.split("\n")
            number_header = lines[0]

        # Tạo chuỗi Active Header đầy đủ dạng Breadcrumb
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
    """Thêm block vào chunk hiện tại; tự chia nhỏ khi cần."""
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

        # Chunk hiện tại đã kín: ghi nó rồi mở chunk mới.
        if available <= 0:
            result.append(current)
            current = ""
            continue

        piece, remaining = _take_prefix(remaining, available)
        current = f"{current}{separator}{piece}" if current else piece

        # Còn text chưa đưa vào được thì đóng chunk hiện tại.
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
    """Tạo chunk mới, lặp lại heading và overlap trong giới hạn cho phép."""
    header = active_header.strip()

    # Heading quá dài vẫn không được làm chunk vượt giới hạn.
    if len(header) >= chunk_chars:
        return header[:chunk_chars]

    overlap_budget = chunk_chars - len(header) - 2
    overlap = _tail(previous_chunk, min(overlap_chars, overlap_budget))

    if header and overlap:
        return f"{header}\n{overlap}"

    return header or overlap


def _take_prefix(text: str, limit: int) -> tuple[str, str]:
    """Lấy phần đầu không quá limit, ưu tiên cắt ở newline hoặc khoảng trắng."""
    if len(text) <= limit:
        return text, ""

    newline_boundary = text.rfind("\n", 0, limit + 1)
    space_boundary = text.rfind(" ", 0, limit + 1)
    boundary = max(newline_boundary, space_boundary)

    # Một từ hoặc một dòng quá dài: bắt buộc cắt cứng để tránh vòng lặp vô hạn.
    if boundary <= 0:
        boundary = limit

    prefix = text[:boundary].strip()
    remainder = text[boundary:].strip()

    # Phòng trường hợp boundary rơi vào whitespace đầu chuỗi.
    if not prefix:
        prefix = text[:limit].strip()
        remainder = text[limit:].strip()

    return prefix, remainder


def _tail(text: str, limit: int) -> str:
    """Lấy phần cuối làm overlap, ưu tiên bắt đầu tại ranh giới từ."""
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