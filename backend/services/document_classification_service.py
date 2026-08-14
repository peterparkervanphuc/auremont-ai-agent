"""Phân loại sơ bộ tài liệu dự án từ tên file và nội dung.

Đây là lớp rule-based: nhanh, rẻ, có thể test và dễ giải thích.
Kết quả chỉ là đề xuất cho Admin, không tự động approved tài liệu.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime

from backend.core.enums import (
    DocumentCategory,
    LegalStatus,
)
from backend.utils.text import strip_diacritics


@dataclass(frozen=True)
class DocumentClassification:
    category: DocumentCategory
    subcategory: str | None = None

    subdivision_names: list[str] | None = None
    building_codes: list[str] | None = None
    unit_types: list[str] | None = None
    applicable_area: str | None = None

    document_summary: str | None = None
    version_label: str | None = None
    issued_date: date | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    applicable_period: str | None = None

    legal_document_type: str | None = None
    legal_document_number: str | None = None
    legal_issuer: str | None = None
    legal_domain: str | None = None
    legal_status: LegalStatus = LegalStatus.UNKNOWN

    confidence: float = 0.0
    reason: str = ""


_LEGAL_TYPE_PATTERNS = {
    "Luật": r"\bluat\b",
    "Bộ luật": r"\bbo luat\b",
    "Nghị định": r"\bnghi dinh\b",
    "Thông tư": r"\bthong tu\b",
    "Nghị quyết": r"\bnghi quyet\b",
    "Quyết định": r"\bquyet dinh\b",
    "Công văn": r"\bcong van\b",
}

_CATEGORY_RULES: list[tuple[DocumentCategory, tuple[str, ...], float]] = [
    (
        DocumentCategory.LEGAL_DOCUMENT,
        ("nghi dinh", "thong tu", "nghi quyet", "quyet dinh", "cong van", "bo luat", "luat "),
        0.92,
    ),
    (
        DocumentCategory.SALES_POLICY,
        ("chinh sach ban hang", "csbh", "chinh sach gia", "chinh sach kinh doanh"),
        0.9,
    ),
    (
        DocumentCategory.PRICE_LIST,
        ("bang gia", "gia ban", "don gia", "price list"),
        0.88,
    ),
    (
        DocumentCategory.INVENTORY_SNAPSHOT,
        ("gio hang", "bang hang", "ton kho", "danh sach can"),
        0.86,
    ),
    (
        DocumentCategory.PAYMENT_SCHEDULE,
        ("tien do thanh toan", "phuong thuc thanh toan", "lich thanh toan"),
        0.87,
    ),
    (
        DocumentCategory.PROMOTION,
        ("uu dai", "khuyen mai", "chiet khau", "qua tang"),
        0.82,
    ),
    (
        DocumentCategory.FLOOR_PLAN,
        ("mat bang", "floor plan", "so do mat bang"),
        0.84,
    ),
    (
        DocumentCategory.SUBDIVISION_INFO,
        ("phan khu", "tong quan phan khu"),
        0.75,
    ),
    (
        DocumentCategory.BUILDING_INFO,
        ("toa nha", "thong tin toa", "thap "),
        0.72,
    ),
    (
        DocumentCategory.CONTRACT_TEMPLATE,
        ("hop dong mau", "phieu dat coc", "van ban thoa thuan"),
        0.85,
    ),
    (
        DocumentCategory.INTERNAL_GUIDE,
        ("tai lieu noi bo", "huong dan noi bo", "quy trinh noi bo"),
        0.82,
    ),
]

_DOCUMENT_NUMBER_RE = re.compile(
    r"\b(?P<number>\d{1,4}/\d{4}/[A-Z0-9Đ\-]+)\b",
    flags=re.IGNORECASE,
)

_DD_MM_YYYY_RE = re.compile(
    r"\b(?P<day>\d{1,2})[/-](?P<month>\d{1,2})[/-](?P<year>\d{4})\b"
)

_VIETNAMESE_DATE_RE = re.compile(
    r"ngay\s+(?P<day>\d{1,2})\s+thang\s+(?P<month>\d{1,2})\s+nam\s+(?P<year>\d{4})",
    flags=re.IGNORECASE,
)

_EFFECTIVE_RE = re.compile(
    r"(?:co hieu luc(?: thi hanh)?(?: ke tu)?|ap dung tu)"
    r".{0,80}?"
    r"(?P<date>(?:\d{1,2}[/-]\d{1,2}[/-]\d{4})|"
    r"(?:ngay\s+\d{1,2}\s+thang\s+\d{1,2}\s+nam\s+\d{4}))",
    flags=re.IGNORECASE,
)

_EXPIRY_RE = re.compile(
    r"(?:het hieu luc(?: ke tu)?|ap dung den)"
    r".{0,80}?"
    r"(?P<date>(?:\d{1,2}[/-]\d{1,2}[/-]\d{4})|"
    r"(?:ngay\s+\d{1,2}\s+thang\s+\d{1,2}\s+nam\s+\d{4}))",
    flags=re.IGNORECASE,
)

_DATE_RANGE_RE = re.compile(
    r"(?:ap dung tu|co hieu luc(?: thi hanh)?(?: ke tu)?)\s*"
    r"(?P<start>\d{1,2}[/-]\d{1,2}[/-]\d{4})\s*"
    r"(?:den|toi)\s*(?P<end>\d{1,2}[/-]\d{1,2}[/-]\d{4})",
    flags=re.IGNORECASE,
)

_PERIOD_RE = re.compile(
    r"\b(?:thang|dot)\s*(?P<value>\d{1,2}(?:[/-]\d{4})?)\b",
    flags=re.IGNORECASE,
)

_SUBDIVISION_RE = re.compile(
    r"(?:phan khu|subzone)\s*[:\-]?\s*(?P<name>[^\n,.;]{2,80})",
    flags=re.IGNORECASE,
)

_BUILDING_RE = re.compile(
    r"\b(?:toa|thap|block)\s*(?P<code>[A-Z]{1,5}[-.]?\d{1,4}(?:[-.]\d{1,4})?)\b",
    flags=re.IGNORECASE,
)

_UNIT_TYPE_RE = re.compile(
    r"\b(?P<unit>\dPN\+?|studio|penthouse|shophouse|duplex)(?!\w)",
    flags=re.IGNORECASE,
)


def classify_document(
    filename: str,
    raw_text: str,
) -> DocumentClassification:
    """Trả về metadata đề xuất từ tên file và phần đầu nội dung."""

    source = f"{filename}\n{raw_text[:12000]}"
    normalized = strip_diacritics(source).lower()

    category, confidence, reason = _detect_category(normalized)
    # Patterns use unaccented Vietnamese, so run them against the normalised text.
    subdivisions = _unique(_find_subdivisions(normalized))
    buildings = _unique(_find_matches(_BUILDING_RE, normalized, "code"))
    unit_types = _unique(_find_matches(_UNIT_TYPE_RE, normalized, "unit"))

    if category == DocumentCategory.LEGAL_DOCUMENT:
        return _classify_legal_document(
            source=source,
            normalized=normalized,
            subdivisions=subdivisions,
            buildings=buildings,
            unit_types=unit_types,
            confidence=confidence,
            reason=reason,
        )

    issued_date = _first_date(source)
    effective_date = _effective_date(source)
    expiry_date = _expiry_date(source)

    return DocumentClassification(
        category=category,
        subdivision_names=subdivisions or None,
        building_codes=buildings or None,
        unit_types=unit_types or None,
        document_summary=_summary(raw_text),
        issued_date=issued_date,
        effective_date=effective_date,
        expiry_date=expiry_date,
        applicable_period=_applicable_period(normalized),
        confidence=confidence,
        reason=reason,
    )


def _detect_category(
    normalized_text: str,
) -> tuple[DocumentCategory, float, str]:
    for category, keywords, confidence in _CATEGORY_RULES:
        matched = [keyword for keyword in keywords if keyword in normalized_text]
        if matched:
            return (
                category,
                confidence,
                f"Nhận diện từ từ khóa: {', '.join(matched)}.",
            )

    return (
        DocumentCategory.OTHER,
        0.3,
        "Không tìm thấy từ khóa nhận diện loại tài liệu.",
    )


def _classify_legal_document(
    *,
    source: str,
    normalized: str,
    subdivisions: list[str],
    buildings: list[str],
    unit_types: list[str],
    confidence: float,
    reason: str,
) -> DocumentClassification:
    legal_type = _legal_document_type(normalized)
    document_number = _document_number(source)
    effective_date = _effective_date(source)
    expiry_date = _expiry_date(source)

    if legal_type and document_number:
        confidence = max(confidence, 0.97)
        reason = (
            f"{reason} Tìm thấy loại văn bản '{legal_type}' "
            f"và số hiệu '{document_number}'."
        )

    legal_status = LegalStatus.EFFECTIVE if effective_date else LegalStatus.UNKNOWN

    return DocumentClassification(
        category=DocumentCategory.LEGAL_DOCUMENT,
        subdivision_names=subdivisions or None,
        building_codes=buildings or None,
        unit_types=unit_types or None,
        document_summary=_summary(source),
        issued_date=_first_date(source),
        effective_date=effective_date,
        expiry_date=expiry_date,
        legal_document_type=legal_type,
        legal_document_number=document_number,
        legal_issuer=_legal_issuer(normalized),
        legal_domain=_legal_domain(normalized),
        legal_status=legal_status,
        confidence=confidence,
        reason=reason,
    )


def _legal_document_type(normalized: str) -> str | None:
    """Use the earliest type mention, normally the document heading.

    A decree about a law contains both "nghi dinh" and "luat". Dictionary
    insertion order would incorrectly return Luật whenever it appears first in
    `_LEGAL_TYPE_PATTERNS`, even if Nghị định is the actual document title.
    """
    matches = [
        (match.start(), document_type)
        for document_type, pattern in _LEGAL_TYPE_PATTERNS.items()
        if (match := re.search(pattern, normalized)) is not None
    ]
    return min(matches)[1] if matches else None


def _document_number(source: str) -> str | None:
    match = _DOCUMENT_NUMBER_RE.search(source)
    return match.group("number").upper() if match else None


def _legal_issuer(normalized: str) -> str | None:
    if "quoc hoi" in normalized:
        return "Quốc hội"
    if "chinh phu" in normalized:
        return "Chính phủ"
    if "thu tuong chinh phu" in normalized:
        return "Thủ tướng Chính phủ"
    if "bo xay dung" in normalized:
        return "Bộ Xây dựng"
    if "bo tai nguyen va moi truong" in normalized:
        return "Bộ Tài nguyên và Môi trường"
    return None


def _legal_domain(normalized: str) -> str | None:
    if "kinh doanh bat dong san" in normalized:
        return "Kinh doanh bất động sản"
    if "nha o" in normalized:
        return "Nhà ở"
    if "dat dai" in normalized:
        return "Đất đai"
    if "xay dung" in normalized:
        return "Xây dựng"
    return None


def _first_date(source: str) -> date | None:
    dates = _all_dates(source)
    return dates[0] if dates else None


def _effective_date(source: str) -> date | None:
    match = _EFFECTIVE_RE.search(strip_diacritics(source))
    return _parse_date(match.group("date")) if match else None


def _expiry_date(source: str) -> date | None:
    normalized = strip_diacritics(source)
    range_match = _DATE_RANGE_RE.search(normalized)
    if range_match:
        return _parse_date(range_match.group("end"))

    match = _EXPIRY_RE.search(normalized)
    return _parse_date(match.group("date")) if match else None


def _all_dates(source: str) -> list[date]:
    values: list[date] = []

    for match in _DD_MM_YYYY_RE.finditer(source):
        parsed = _date_from_parts(match.group("day"), match.group("month"), match.group("year"))
        if parsed is not None:
            values.append(parsed)

    normalized = strip_diacritics(source)
    for match in _VIETNAMESE_DATE_RE.finditer(normalized):
        parsed = _date_from_parts(match.group("day"), match.group("month"), match.group("year"))
        if parsed is not None:
            values.append(parsed)

    return values


def _parse_date(value: str) -> date | None:
    values = _all_dates(value)
    return values[0] if values else None


def _date_from_parts(
    day: str,
    month: str,
    year: str,
) -> date | None:
    try:
        return datetime(
            year=int(year),
            month=int(month),
            day=int(day),
        ).date()
    except ValueError:
        return None


def _find_subdivisions(source: str) -> list[str]:
    return [
        _display_name(match.group("name").strip(" -:"))
        for match in _SUBDIVISION_RE.finditer(source)
    ]


def _find_matches(
    pattern: re.Pattern[str],
    source: str,
    group: str,
) -> list[str]:
    return [match.group(group).upper() for match in pattern.finditer(source)]


def _applicable_period(normalized: str) -> str | None:
    match = _PERIOD_RE.search(normalized)
    return match.group("value") if match else None


def _summary(raw_text: str) -> str | None:
    cleaned = " ".join(raw_text.split())
    if not cleaned:
        return None
    return cleaned[:500]


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _display_name(value: str) -> str:
    """Make a normalised free-text name readable while preserving abbreviations."""
    return " ".join(word if word.isupper() else word.capitalize() for word in value.split())
