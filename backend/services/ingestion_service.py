import logging
import re
import uuid
from io import BytesIO
from pathlib import PurePath

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.enums import DocumentCategory, DocumentStatus
from backend.core.gemini_client import embed_documents
from backend.core.minio_client import ensure_bucket, get_minio_client
from backend.models.document import Document
from backend.repositories.conflict_flag import create_conflict
from backend.repositories.document import (
    list_completed_siblings,
    update_document_classification_suggestion,
    update_document_status,
    update_document_storage_path,
)
from backend.services.chunking_service import chunk_sections
from backend.services.document_classification_service import classify_document
from backend.services.parser_service import parse_document
from backend.services.vector_store_service import index_document_chunks
from backend.utils.text import strip_diacritics

logger = logging.getLogger(__name__)


class PromptInjectionError(ValueError):
    """The document contains instructions attempting to manipulate the AI."""


class DocumentIngestionError(RuntimeError):
    """Failure while parsing, storing, embedding or indexing a document."""


SUSPICIOUS_PATTERNS = [
    # Includes both "ignore previous instructions" and "ignore all previous
    # instructions". The latter has two words between ignore and instructions.
    r"ignore\s+(?:(?:all|any|previous|prior)\s+){1,2}instructions",
    r"system\s+prompt",
    r"you\s+are\s+chatgpt",
    r"<\s*system\s*>",
    r"jailbreak",
    r"do\s+not\s+follow\s+(the\s+)?rules",
]


def sanitize_and_scan(raw_text: str) -> str:
    """Basic rule checks before a document enters the knowledge base."""
    cleaned = raw_text.replace("\x00", "").strip()

    if not cleaned:
        raise DocumentIngestionError("Document contains no text.")

    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, cleaned, flags=re.IGNORECASE):
            raise PromptInjectionError("Potential prompt-injection content detected.")

    return cleaned


def ingest_uploaded_document(
    db: Session,
    *,
    document: Document,
    filename: str,
    file_bytes: bytes,
    content_type: str | None,
) -> Document:
    """The complete flow for an uploaded PDF/DOCX file.

    The Document row must exist in the DB first, because document.id is what makes the
    MinIO object key and the Qdrant point IDs stable.
    """
    try:
        update_document_status(db, document.id, DocumentStatus.PROCESSING)

        sections = parse_document(filename, file_bytes)
        raw_text = "\n\n".join(section.text for section in sections)
        sanitize_and_scan(raw_text)

        classification = classify_document(filename, raw_text)
        document = update_document_classification_suggestion(
            db,
            document_id=document.id,
            classification=classification,
            auto_approve=(classification.confidence >= settings.classification_auto_approve_threshold),
        )

        object_key = _store_original_file(
            document_id=document.id,
            filename=filename,
            file_bytes=file_bytes,
            content_type=content_type,
        )
        update_document_storage_path(db, document.id, object_key)

        chunks = chunk_sections(
            sections,
            document_category=document.category,
        )
        if not chunks:
            raise DocumentIngestionError("No chunks were produced.")

        # Batch the chunks so a single Gemini request does not carry too many at once.
        vectors: list[list[float]] = []
        batch_size = 32

        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors.extend(
                embed_documents(
                    [chunk.text for chunk in batch],
                    title=document.title,
                )
            )

        index_document_chunks(
            document_id=document.id,
            title=document.title,
            project_id=document.project_id,
            visibility=document.visibility,
            chunks=chunks,
            vectors=vectors,
            category=document.category,
            review_status=document.review_status,
            legal_status=document.legal_status,
            is_current=document.is_current,
        )

        completed = update_document_status(
            db,
            document.id,
            DocumentStatus.COMPLETED,
        )

        # Runs only after the document is safely COMPLETED, and never propagates:
        # flagging a possible conflict is an Admin convenience, so a failure here
        # must not undo an ingest that already succeeded.
        try:
            flag_conflicts_for(db, completed, raw_text=raw_text)
        except Exception:  # pragma: no cover - advisory step, never fatal
            logger.warning(
                "Skipping the conflict scan for document %s.",
                completed.id,
                exc_info=True,
                extra={"event": "document.conflict_scan.failed", "document_id": completed.id},
            )

        return completed

    except PromptInjectionError:
        update_document_status(db, document.id, DocumentStatus.BLOCKED)
        raise

    except Exception as exc:
        update_document_status(db, document.id, DocumentStatus.FAILED)

        if isinstance(exc, DocumentIngestionError):
            raise

        raise DocumentIngestionError(f"Could not ingest document {document.id}.") from exc


def flag_conflicts_for(
    db: Session,
    document: Document,
    *,
    raw_text: str | None = None,
) -> list[int]:
    """Compare actual business content with older documents of the same project."""
    current_text = raw_text if raw_text is not None else _read_original_text(document)
    created: list[int] = []

    for sibling in list_completed_siblings(db, document.project_id, exclude_id=document.id):
        if not _same_business_scope(document, sibling):
            continue

        same_title = _title_key(sibling.title) == _title_key(document.title)

        # No project on either side means the anchor that normally ties two documents
        # together is missing, so one has to be earned: an overlapping subdivision,
        # building or unit type, or the very same title. Without this, two unrelated
        # unassigned price lists would flag each other and bury the Admin in noise.
        if not document.project_id and not (same_title or _shares_explicit_scope(document, sibling)):
            continue

        is_price_list = document.category == DocumentCategory.PRICE_LIST

        # Reading the sibling's text downloads and re-parses the original from MinIO, so
        # bail out first when no flag can come of it. A price-list conflict is decided by
        # the rows; for every other category the title already decided it and the prices
        # only enrich the description.
        if not is_price_list and not same_title:
            continue

        price_differences = _price_differences(
            _read_original_text(sibling),
            current_text,
        )

        # Price-list conflicts are driven by row content, not filenames. Other
        # categories retain the duplicate-title warning until they have their own
        # domain comparator (legal effect, policy clauses, etc.).
        if is_price_list and not price_differences:
            continue

        conflict = create_conflict(
            db,
            document_id_a=sibling.id,
            document_id_b=document.id,
            description=(
                f"Phát hiện nội dung khác nhau giữa '{sibling.title}' và "
                f"'{document.title}' trong cùng dự án."
                f"{_format_price_differences(price_differences)} "
                "Kiểm tra và chọn bản được ưu tiên."
            ),
        )
        created.append(conflict.id)

    return created


def _title_key(title: str | None) -> str:
    """Normalise a title for comparison: no diacritics, no extra whitespace."""
    if not title:
        return ""
    return " ".join(strip_diacritics(title).split())


_UNIT_CODE_RE = re.compile(
    r"\b(?=[A-Z0-9.-]*[A-Z])(?=[A-Z0-9.-]*\d)"
    r"[A-Z0-9]+(?:[-.][A-Z0-9]+)+\b",
    re.IGNORECASE,
)
_PRICE_RE = re.compile(
    r"(?<!\w)(\d{1,3}(?:[.,]\d{3}){2,}|\d+(?:[.,]\d+)?)\s*"
    r"(tỷ|ty|triệu|trieu|tr|million|billion|vnđ|vnd|đ|đồng|dong)\b",
    re.IGNORECASE,
)


_SCOPE_FIELDS = ("subdivision_names", "building_codes", "unit_types")


def _scope_values(document: Document, field: str) -> set[str]:
    return {strip_diacritics(str(value)).lower() for value in (getattr(document, field) or [])}


def _same_business_scope(left: Document, right: Document) -> bool:
    """Permissive on purpose: an empty field counts as "might overlap".

    Metadata is extracted automatically and is often incomplete, so a missing subdivision
    must not be read as proof that two documents are unrelated. Only a field populated on
    both sides with no value in common rules the pair out.
    """
    if left.category != right.category:
        return False
    for field in _SCOPE_FIELDS:
        left_values = _scope_values(left, field)
        right_values = _scope_values(right, field)
        if left_values and right_values and left_values.isdisjoint(right_values):
            return False
    return True


def _shares_explicit_scope(left: Document, right: Document) -> bool:
    """True when both documents name at least one identical subdivision, building or unit type.

    The strict counterpart to `_same_business_scope`, for documents carrying no project:
    there, "might overlap" would match everything, so real evidence is required.
    """
    return any(_scope_values(left, field) & _scope_values(right, field) for field in _SCOPE_FIELDS)


def _price_facts(text: str) -> dict[str, set[int]]:
    """Extract unit/product identifiers and prices from table-like lines."""
    facts: dict[str, set[int]] = {}
    unkeyed: set[int] = set()
    for line in text.splitlines():
        prices = {_price_to_vnd(match.group(1), match.group(2)) for match in _PRICE_RE.finditer(line)}
        prices.discard(0)
        if not prices:
            continue
        codes = {match.group(0).upper() for match in _UNIT_CODE_RE.finditer(line)}
        if codes:
            for code in codes:
                facts.setdefault(code, set()).update(prices)
        else:
            unkeyed.update(prices)
    if unkeyed:
        facts["__DOCUMENT_PRICES__"] = unkeyed
    return facts


def _price_to_vnd(number: str, unit: str) -> int:
    compact = number.strip()
    normalised_unit = strip_diacritics(unit).lower()
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3}){2,}", compact):
        return int(re.sub(r"[.,]", "", compact))
    value = float(compact.replace(",", "."))
    if normalised_unit in {"ty", "billion"}:
        value *= 1_000_000_000
    elif normalised_unit in {"trieu", "tr", "million"}:
        value *= 1_000_000
    return round(value)


def _price_differences(
    old_text: str,
    new_text: str,
) -> list[tuple[str, set[int], set[int]]]:
    old_facts = _price_facts(old_text)
    new_facts = _price_facts(new_text)
    return [
        (key, old_facts[key], new_facts[key])
        for key in sorted(old_facts.keys() & new_facts.keys())
        if old_facts[key] != new_facts[key]
    ]


def _format_price_differences(
    differences: list[tuple[str, set[int], set[int]]],
) -> str:
    if not differences:
        return ""
    samples = []
    for key, old_prices, new_prices in differences[:5]:
        label = "toàn bảng" if key == "__DOCUMENT_PRICES__" else key
        old_value = "/".join(f"{value:,}" for value in sorted(old_prices))
        new_value = "/".join(f"{value:,}" for value in sorted(new_prices))
        samples.append(f" {label}: {old_value} → {new_value} VNĐ")
    return " Các mức giá thay đổi:" + ";".join(samples) + "."


def _read_original_text(document: Document) -> str:
    if not document.file_path:
        return ""
    response = get_minio_client().get_object(
        settings.minio_bucket_documents,
        document.file_path,
    )
    try:
        data = response.read()
    finally:
        response.close()
        response.release_conn()
    sections = parse_document(document.title, data)
    return "\n\n".join(section.text for section in sections)


def _store_original_file(
    *,
    document_id: int,
    filename: str,
    file_bytes: bytes,
    content_type: str | None,
) -> str:
    """Store the original file in MinIO; the DB keeps only the object key."""
    safe_filename = PurePath(filename).name
    object_key = f"documents/{document_id}/{uuid.uuid4().hex}-{safe_filename}"

    try:
        ensure_bucket(settings.minio_bucket_documents)

        get_minio_client().put_object(
            bucket_name=settings.minio_bucket_documents,
            object_name=object_key,
            data=BytesIO(file_bytes),
            length=len(file_bytes),
            content_type=content_type or "application/octet-stream",
        )
    except Exception as exc:
        raise DocumentIngestionError("Could not store original file in MinIO.") from exc

    return object_key
