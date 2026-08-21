"""Provisional classification of an uploaded document from its filename and content.

Rule-based on purpose: fast, free, testable and explainable. The result is only a
suggestion for the Admin — nothing here approves a document for retrieval, because a
misclassified price list that auto-approved would go straight into customer-facing answers.
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
    # Confidence expresses how strong the rule match is; approval eligibility is a
    # separate safety decision. This prevents a low configured threshold from making
    # body-only or contradictory evidence customer-facing without an Admin review.
    requires_admin_review: bool = False


# Ceiling for a category detected from body text alone. Deliberately below the default
# `classification_auto_approve_threshold` (0.9) so such a document waits for an Admin.
_BODY_ONLY_MAX_CONFIDENCE = 0.85

_SEPARATOR_RE = re.compile(r"[^a-z0-9]+")
_CAMEL_CASE_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_OPENING_TEXT_LENGTH = 1500

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
        (
            "tong quan du an",
            "gioi thieu du an",
            "thong tin du an",
            "tong quan phan khu",
            "gioi thieu phan khu",
            "thong tin phan khu",
            "phan khu",
            "tong quan",
            "gioi thieu",
        ),
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

# Only explicit document-title phrases may contradict a filename classification. Generic
# words such as "tong quan", "phan khu" or "uu dai" are intentionally excluded: they are
# common section headings inside otherwise unrelated documents.
_STRONG_BODY_HEADING_KEYWORDS: dict[DocumentCategory, tuple[str, ...]] = {
    DocumentCategory.SALES_POLICY: (
        "chinh sach ban hang",
        "chinh sach kinh doanh",
        "csbh",
    ),
    DocumentCategory.PRICE_LIST: ("bang gia", "price list"),
    DocumentCategory.INVENTORY_SNAPSHOT: (
        "gio hang",
        "bang hang",
        "ton kho",
        "danh sach can",
    ),
    DocumentCategory.PAYMENT_SCHEDULE: (
        "tien do thanh toan",
        "phuong thuc thanh toan",
        "lich thanh toan",
    ),
    DocumentCategory.PROMOTION: ("uu dai", "khuyen mai"),
    DocumentCategory.FLOOR_PLAN: ("mat bang", "floor plan", "so do mat bang"),
    DocumentCategory.SUBDIVISION_INFO: (
        "tong quan du an",
        "gioi thieu du an",
        "thong tin du an",
        "tong quan phan khu",
        "gioi thieu phan khu",
        "thong tin phan khu",
    ),
    DocumentCategory.BUILDING_INFO: ("toa nha", "thong tin toa"),
    DocumentCategory.CONTRACT_TEMPLATE: (
        "hop dong mau",
        "phieu dat coc",
        "van ban thoa thuan",
    ),
    DocumentCategory.INTERNAL_GUIDE: (
        "tai lieu noi bo",
        "huong dan noi bo",
        "quy trinh noi bo",
    ),
}

_DOCUMENT_NUMBER_RE = re.compile(
    r"\b(?P<number>\d{1,4}/\d{4}/[A-Z0-9Đ\-]+)\b",
    flags=re.IGNORECASE,
)

_DD_MM_YYYY_RE = re.compile(r"\b(?P<day>\d{1,2})[/-](?P<month>\d{1,2})[/-](?P<year>\d{4})\b")

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
    r"(?:ap dung|thoi gian ap dung|co hieu luc(?: thi hanh)?)(?:\s+ke)?\s+tu\s*"
    r"(?P<start>\d{1,2}[/-]\d{1,2}[/-]\d{4})\s*"
    r"(?:den|toi)\s*(?P<end>\d{1,2}[/-]\d{1,2}[/-]\d{4})",
    flags=re.IGNORECASE,
)

_ISSUED_DATE_RE = re.compile(
    r"(?:"
    r"ngay\s+(?:ban hanh|phat hanh|cap nhat|ky)"
    r"|(?:ban hanh|phat hanh|cap nhat|ky)(?:\s+(?:vao|tu))?\s+ngay"
    r")"
    r"[\s|:#=-]{0,30}"
    r"(?P<date>(?:\d{1,2}[/-]\d{1,2}[/-]\d{4})|"
    r"(?:ngay\s+\d{1,2}\s+thang\s+\d{1,2}\s+nam\s+\d{4}))",
    flags=re.IGNORECASE,
)

_PLACE_AND_DATE_RE = re.compile(
    r"(?:ha noi|hai phong|da nang|thanh pho ho chi minh|tp\.?\s*hcm)\s*,?\s*"
    r"(?P<date>ngay\s+\d{1,2}\s+thang\s+\d{1,2}\s+nam\s+\d{4})",
    flags=re.IGNORECASE,
)

_EXPLICIT_VERSION_RE = re.compile(
    r"\b(?:phien ban|version|ver)\b[\s|:#=-]{0,20}"
    r"(?P<version>v?\s*\d+(?:\.\d+){0,2})\b",
    flags=re.IGNORECASE,
)

_FILENAME_VERSION_RE = re.compile(
    r"(?:^|\s)(?P<version>v\s*\d+(?:\.\d+){0,2})(?=\s|$)",
    flags=re.IGNORECASE,
)

_MONTH_PERIOD_RE = re.compile(
    r"\b(?:thang|t)\s*[:#-]?\s*(?P<month>0?[1-9]|1[0-2])"
    r"(?:\s*(?:[/.-]|nam\s+)\s*|\s+)(?P<year>20\d{2})\b",
    flags=re.IGNORECASE,
)

_APPLICABLE_MONTH_RE = re.compile(
    r"\b(?:ky\s+)?ap dung\s*[:#-]\s*(?P<month>0?[1-9]|1[0-2])"
    r"\s*[/.-]\s*(?P<year>20\d{2})\b",
    flags=re.IGNORECASE,
)

_SALES_ROUND_RE = re.compile(
    r"\bdot(?:\s+mo\s+ban)?\s*[:#-]?\s*(?:dot\s*)?(?P<round>\d{1,3})\b",
    flags=re.IGNORECASE,
)

_EXPLICIT_SALES_ROUND_RE = re.compile(
    r"\bdot\s+(?:mo\s+ban|ap\s+dung)\b"
    r"[ \t|:#=-]{0,20}(?:dot\s*)?(?P<round>\d{1,3})\b",
    flags=re.IGNORECASE,
)

_QUARTER_PERIOD_RE = re.compile(
    r"\bq(?P<quarter>[1-4])\s*[/.-]?\s*(?P<year>20\d{2})\b",
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
    """Propose document metadata from the filename and the opening of the content."""

    source = f"{filename}\n{raw_text[:12000]}"
    normalized = strip_diacritics(source).lower()
    normalized_body = strip_diacritics(raw_text[:12000]).lower()
    # Real filenames separate words with _ . or -, so "Bang_gia_Beverly.pdf" would never
    # contain the keyword "bang gia". Flatten every separator to a space first.
    # Split CamelCase before `strip_diacritics`: that helper lowercases its input,
    # which would otherwise turn `ThongTinDuAn` into one opaque token first.
    filename_words = _CAMEL_CASE_BOUNDARY_RE.sub(" ", filename)
    normalized_filename = _SEPARATOR_RE.sub(" ", strip_diacritics(filename_words)).strip()

    category, confidence, reason, requires_admin_review = _detect_category(
        normalized_filename,
        normalized_body,
    )
    # Patterns use unaccented Vietnamese, so run them against the normalised text.
    subdivisions = _unique(_find_subdivisions(normalized))
    buildings = _unique(_find_matches(_BUILDING_RE, normalized, "code"))
    unit_types = _unique(_find_matches(_UNIT_TYPE_RE, normalized, "unit"))
    version_label = _version_label(normalized_filename, normalized_body)
    issued_date = _issued_date(raw_text)
    applicable_period = _applicable_period(normalized_filename, normalized_body)

    if category == DocumentCategory.LEGAL_DOCUMENT:
        return _classify_legal_document(
            raw_text=raw_text,
            normalized=normalized,
            subdivisions=subdivisions,
            buildings=buildings,
            unit_types=unit_types,
            version_label=version_label,
            issued_date=issued_date,
            applicable_period=applicable_period,
            confidence=confidence,
            reason=reason,
            requires_admin_review=requires_admin_review,
        )

    effective_date = _effective_date(raw_text)
    expiry_date = _expiry_date(raw_text)

    return DocumentClassification(
        category=category,
        subdivision_names=subdivisions or None,
        building_codes=buildings or None,
        unit_types=unit_types or None,
        document_summary=_summary(raw_text),
        version_label=version_label,
        issued_date=issued_date,
        effective_date=effective_date,
        expiry_date=expiry_date,
        applicable_period=applicable_period,
        confidence=confidence,
        reason=reason,
        requires_admin_review=requires_admin_review,
    )


def _detect_category(
    normalized_filename: str,
    normalized_body: str,
) -> tuple[DocumentCategory, float, str, bool]:
    """Classify from the filename first, then use weighted evidence from the body.

    Filename evidence wins by default. A different body category may override it only when
    its score is higher and the opening contains an explicit title for that category but
    not for the filename category. This keeps ``Bang_Gia_The_Zurich_v1.pdf`` a price list
    when policy phrases occur in later sections, while still correcting a genuinely
    misleading filename. Legal terms additionally need a legal heading/number; prose such
    as "theo Luật ..." or "theo quyết định của Chủ đầu tư" is not a legal-document
    signature.
    """
    filename_best: tuple[int, float, DocumentCategory, list[str]] | None = None

    for category, keywords, confidence in _CATEGORY_RULES:
        matched = [keyword for keyword in keywords if _contains_keyword(normalized_filename, keyword)]
        if not matched:
            continue
        candidate = (
            len(matched),
            confidence,
            category,
            matched,
        )
        if filename_best is None or candidate[:2] > filename_best[:2]:
            filename_best = candidate

    opening = normalized_body[:_OPENING_TEXT_LENGTH]
    heading = _opening_heading(normalized_body)
    body_candidates: list[tuple[int, float, DocumentCategory, list[str]]] = []
    body_best: tuple[int, float, DocumentCategory, list[str]] | None = None

    for category, keywords, confidence in _CATEGORY_RULES:
        matched = [keyword for keyword in keywords if _contains_keyword(normalized_body, keyword)]
        if category == DocumentCategory.LEGAL_DOCUMENT and not _looks_like_legal_document(normalized_body):
            continue

        # "Chính sách giá" is commonly only a section inside a project introduction.
        # Treat it as category evidence only when it is part of the document heading, not
        # when it appears as section IV of a project overview.
        if category == DocumentCategory.SALES_POLICY and "chinh sach gia" in matched:
            if not _contains_keyword(heading, "chinh sach gia"):
                matched.remove("chinh sach gia")

        if not matched:
            continue

        opening_matches = [keyword for keyword in matched if _contains_keyword(opening, keyword)]
        candidate = (
            len(matched) + (2 * len(opening_matches)),
            confidence,
            category,
            matched,
        )
        body_candidates.append(candidate)
        if body_best is None or candidate[:2] > body_best[:2]:
            body_best = candidate

    if filename_best is not None:
        filename_score, filename_confidence, filename_category, filename_matched = filename_best

        filename_has_strong_heading = _has_strong_category_heading(
            filename_category,
            normalized_body,
        )
        contradictions = [
            candidate
            for candidate in body_candidates
            if candidate[2] != filename_category
            and candidate[0] >= 3
            and candidate[0] > filename_score
            and _has_strong_category_heading(candidate[2], normalized_body)
            and not filename_has_strong_heading
        ]
        if contradictions:
            _body_score, body_confidence, body_category, body_matched = max(
                contradictions,
                key=lambda candidate: candidate[:2],
            )
            return (
                body_category,
                min(body_confidence, _BODY_ONLY_MAX_CONFIDENCE),
                "Tên file gợi ý "
                f"'{filename_category.value}', nhưng tiêu đề mở đầu cho thấy rõ "
                f"'{body_category.value}' qua: {', '.join(body_matched)}. "
                "Cần Admin xác nhận.",
                True,
            )

        # Approval eligibility is independent of the configurable confidence
        # threshold. Otherwise lowering that threshold could publish an unconfirmed
        # filename-only guess that merely happened to score below the default 0.9.
        if not filename_has_strong_heading:
            return (
                filename_category,
                min(filename_confidence, _BODY_ONLY_MAX_CONFIDENCE),
                f"Nhận diện từ tên file '{filename_category.value}' qua: "
                f"{', '.join(filename_matched)}, nhưng phần mở đầu chưa xác nhận loại tài liệu. "
                "Cần Admin xác nhận.",
                True,
            )

        return (
            filename_category,
            filename_confidence,
            f"Nhận diện từ từ khóa trong tên file: {', '.join(filename_matched)}.",
            False,
        )

    if body_best is None:
        return (
            DocumentCategory.OTHER,
            0.3,
            "Không tìm thấy từ khóa nhận diện loại tài liệu.",
            True,
        )

    _score, confidence, category, matched = body_best
    keywords_found = ", ".join(matched)

    # Body-only evidence stays under the auto-approve bar so an Admin looks at it. A
    # keyword appearing somewhere in the text must not be enough to push a document
    # straight into the knowledge base unreviewed.
    return (
        category,
        min(confidence, _BODY_ONLY_MAX_CONFIDENCE),
        f"Nhận diện từ từ khóa trong nội dung: {keywords_found}. Cần Admin xác nhận.",
        True,
    )


def _contains_keyword(source: str, keyword: str) -> bool:
    """Match a normalised keyword on word boundaries, not inside another word."""
    expression = rf"(?<![a-z0-9]){re.escape(keyword.strip())}(?![a-z0-9])"
    return re.search(expression, source) is not None


def _opening_heading(normalized_body: str) -> str:
    """Return the first few non-empty lines where a parsed title normally lives."""
    lines = [line.strip(" \t|:-") for line in normalized_body.splitlines() if line.strip(" \t|:-")]
    return " ".join(lines[:3])


def _has_strong_category_heading(
    category: DocumentCategory,
    normalized_body: str,
) -> bool:
    """Return whether the opening explicitly presents itself as ``category``."""
    lines = [line.strip(" \t|:-") for line in normalized_body.splitlines() if line.strip(" \t|:-")]
    if category == DocumentCategory.LEGAL_DOCUMENT:
        return any(re.match(pattern, line) for line in lines[:3] for pattern in _LEGAL_TYPE_PATTERNS.values())

    return any(
        _line_starts_with_heading_keyword(line, keyword)
        for line in lines[:3]
        for keyword in _STRONG_BODY_HEADING_KEYWORDS.get(category, ())
    )


def _line_starts_with_heading_keyword(line: str, keyword: str) -> bool:
    """Match a title phrase at line start, allowing a leading section number."""
    section_prefix = r"(?:(?:[ivxlcdm]+|\d+)[.)\s:-]+)?"
    expression = rf"^{section_prefix}{re.escape(keyword.strip())}(?![a-z0-9])"
    return re.search(expression, line) is not None


def _looks_like_legal_document(normalized_body: str) -> bool:
    """Require a legal-document signature, not a passing reference to legislation."""
    lines = [line.strip(" \t|:-") for line in normalized_body.splitlines() if line.strip(" \t|:-")]
    first_line = lines[0] if lines else ""

    if any(re.match(pattern, first_line) for pattern in _LEGAL_TYPE_PATTERNS.values()):
        return True

    opening = normalized_body[:1000]
    has_legal_term = any(re.search(pattern, opening) for pattern in _LEGAL_TYPE_PATTERNS.values())
    has_document_number = re.search(r"\b\d{1,4}/\d{4}/[a-z0-9-]+\b", opening) is not None
    return has_legal_term and has_document_number


def _classify_legal_document(
    *,
    raw_text: str,
    normalized: str,
    subdivisions: list[str],
    buildings: list[str],
    unit_types: list[str],
    version_label: str | None,
    issued_date: date | None,
    applicable_period: str | None,
    confidence: float,
    reason: str,
    requires_admin_review: bool,
) -> DocumentClassification:
    legal_type = _legal_document_type(normalized)
    document_number = _document_number(raw_text)
    effective_date = _effective_date(raw_text)
    expiry_date = _expiry_date(raw_text)

    if legal_type and document_number and not requires_admin_review:
        confidence = max(confidence, 0.97)
        reason = f"{reason} Tìm thấy loại văn bản '{legal_type}' và số hiệu '{document_number}'."

    today = date.today()
    if expiry_date and expiry_date < today:
        legal_status = LegalStatus.EXPIRED
    elif effective_date and effective_date > today:
        legal_status = LegalStatus.NOT_YET_EFFECTIVE
    elif effective_date:
        legal_status = LegalStatus.EFFECTIVE
    else:
        legal_status = LegalStatus.UNKNOWN

    return DocumentClassification(
        category=DocumentCategory.LEGAL_DOCUMENT,
        subdivision_names=subdivisions or None,
        building_codes=buildings or None,
        unit_types=unit_types or None,
        document_summary=_summary(raw_text),
        version_label=version_label,
        issued_date=issued_date,
        effective_date=effective_date,
        expiry_date=expiry_date,
        applicable_period=applicable_period,
        legal_document_type=legal_type,
        legal_document_number=document_number,
        legal_issuer=_legal_issuer(normalized),
        legal_domain=_legal_domain(normalized),
        legal_status=legal_status,
        confidence=confidence,
        reason=reason,
        requires_admin_review=requires_admin_review,
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
    if "thu tuong chinh phu" in normalized:
        return "Thủ tướng Chính phủ"
    if "chinh phu" in normalized:
        return "Chính phủ"
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


def _issued_date(source: str) -> date | None:
    """Extract only a labelled/formal issue date.

    The first date in a sales document is often an instalment deadline or a warranty
    date. Treating it as the issue date produced values such as 31/01/2028 for a 2026
    Zurich price list. Returning ``None`` is safer when the document does not identify an
    issue date explicitly.
    """
    normalized = strip_diacritics(source)

    match = _ISSUED_DATE_RE.search(normalized)
    if match:
        return _parse_date(match.group("date"))

    place_match = _PLACE_AND_DATE_RE.search(normalized)
    return _parse_date(place_match.group("date")) if place_match else None


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
    values: list[str] = []
    for match in _SUBDIVISION_RE.finditer(source):
        value = _clean_subdivision_name(match.group("name"))
        if value:
            values.append(value)
    return values


def _clean_subdivision_name(value: str) -> str | None:
    """Remove table/project suffixes and reject generic product-type phrases."""
    cleaned = value.strip(" \t|:-")
    cleaned = re.split(r"\s+-\s+vinhomes\b", cleaned, maxsplit=1)[0].strip(" \t|:-")
    key = " ".join(strip_diacritics(cleaned).split())
    if not key:
        return None

    generic_prefixes = (
        "cao tang",
        "thap tang",
        "cao tang va thap tang",
        "vinhomes ocean park",
        "cac phan khu",
    )
    if key.startswith(generic_prefixes):
        return None
    return _display_name(cleaned)


def _find_matches(
    pattern: re.Pattern[str],
    source: str,
    group: str,
) -> list[str]:
    return [match.group(group).upper() for match in pattern.finditer(source)]


def _version_label(normalized_filename: str, normalized_body: str) -> str | None:
    match = _EXPLICIT_VERSION_RE.search(normalized_body)
    if match is None:
        match = _FILENAME_VERSION_RE.search(normalized_filename)
    if match is None:
        return None

    value = re.sub(r"\s+", "", match.group("version")).lower()
    return value.upper() if value.startswith("v") else f"V{value}"


def _applicable_period(normalized_filename: str, normalized_body: str) -> str | None:
    """Return a canonical month, sales round or quarter from body/name metadata."""
    # An explicit document label is more authoritative than month mentions in payment or
    # delivery prose later in the body (for example "Đợt mở bán: Đợt 2" before 12/2026).
    for source in (normalized_body, normalized_filename):
        match = _EXPLICIT_SALES_ROUND_RE.search(source)
        if match:
            return f"Đợt {int(match.group('round'))}"

    for source in (normalized_body, normalized_filename):
        match = _MONTH_PERIOD_RE.search(source) or _APPLICABLE_MONTH_RE.search(source)
        if match:
            return f"{int(match.group('month')):02d}/{match.group('year')}"

    for source in (normalized_body, normalized_filename):
        match = _SALES_ROUND_RE.search(source)
        if match:
            return f"Đợt {int(match.group('round'))}"

    for source in (normalized_body, normalized_filename):
        match = _QUARTER_PERIOD_RE.search(source)
        if match:
            return f"Q{match.group('quarter')}/{match.group('year')}"

    return None


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
