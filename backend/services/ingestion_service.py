import hashlib
import logging
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.enums import DocumentCategory, DocumentReviewStatus, DocumentStatus, LegalStatus
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
from backend.services.parser_service import ParsedSection, parse_document
from backend.services.vector_store_service import (
    index_document_chunks,
    update_document_vector_metadata,
)
from backend.utils.text import strip_diacritics
from backend.utils.time import utcnow

logger = logging.getLogger(__name__)


class PromptInjectionError(ValueError):
    """The document contains instructions attempting to manipulate the AI."""


class DocumentIngestionError(RuntimeError):
    """Failure while parsing, storing, embedding or indexing a document."""


@dataclass(frozen=True)
class ConflictScanOutcome:
    """The two materially different reasons a new document must stay quarantined."""

    conflict_ids: tuple[int, ...] = ()
    duplicate_document_ids: tuple[int, ...] = ()


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
    vector_write_attempted = False
    try:
        update_document_status(db, document.id, DocumentStatus.PROCESSING)

        parsed_sections = parse_document(filename, file_bytes)
        sections = [
            ParsedSection(text=cleaned, page=section.page)
            for section in parsed_sections
            if (cleaned := section.text.replace("\x00", "").strip())
        ]
        raw_text = sanitize_and_scan("\n\n".join(section.text for section in sections))

        classification = classify_document(filename, raw_text)
        document = update_document_classification_suggestion(
            db,
            document_id=document.id,
            classification=classification,
            auto_approve=(
                not classification.requires_admin_review
                and classification.confidence >= settings.classification_auto_approve_threshold
            ),
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

        # Keep new vectors quarantined until the conflict scan succeeds. This stops an
        # auto-approved document from answering between Qdrant upsert and conflict
        # detection (or after a failed scan).
        vector_write_attempted = True
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
            is_current=False,
        )

        # Serialize the compare-and-activate section for one project/category. Without
        # this, two concurrent uploads can both scan while the other is PROCESSING,
        # both see no completed sibling, and both become retrievable.
        with _conflict_scope_lock(db, document):
            # Keep the flags in this transaction. A later sibling read can still fail;
            # committing each flag inside the scan would leave an OPEN conflict pointing
            # at a document that the outer handler subsequently marks FAILED.
            scan = scan_conflicts_for(db, document, raw_text=raw_text, commit=False)
            has_duplicate = bool(scan.duplicate_document_ids)
            document.is_current = (
                not scan.conflict_ids
                and not has_duplicate
                and document.legal_status
                not in {
                    LegalStatus.NOT_YET_EFFECTIVE,
                    LegalStatus.EXPIRED,
                    LegalStatus.REPEALED,
                    LegalStatus.REPLACED,
                }
            )

            if has_duplicate:
                # A byte/format-normalised duplicate is not a contradiction, so it
                # must not create an OPEN flag. It also must not become a second live
                # source that crowds retrieval/citations with the same content.
                document.review_status = DocumentReviewStatus.REJECTED
                document.reviewed_by = None
                document.reviewed_at = utcnow()
                duplicate_ids = ", ".join(str(document_id) for document_id in scan.duplicate_document_ids)
                document.classification_reason = (
                    f"{document.classification_reason or ''} Exact duplicate of document(s): {duplicate_ids}."
                ).strip()

            document.status = DocumentStatus.BLOCKED if has_duplicate else DocumentStatus.COMPLETED
            document_id = document.id
            final_vector_metadata = {
                "review_status": document.review_status,
                "legal_status": document.legal_status,
                "category": document.category,
                "visibility": document.visibility,
                "is_current": document.is_current,
            }
            db.commit()

            if final_vector_metadata["is_current"] or has_duplicate:
                # Commit the authoritative DB state while Qdrant is still quarantined,
                # then publish the final retrieval metadata under the same scope lock.
                # Duplicates need this sync too because their review status changed to
                # REJECTED after the initial Qdrant write.
                try:
                    update_document_vector_metadata(
                        document_id,
                        **final_vector_metadata,
                    )
                except Exception:
                    # The clean/duplicate decision is already committed. A timed-out
                    # set_payload may or may not have applied, but either outcome is
                    # safe: clean content is authorised, while duplicate points were
                    # already indexed with is_current=false. Do not rewrite MySQL to
                    # FAILED and create a fail-open cross-store contradiction. The
                    # metadata audit will retry/report any availability drift.
                    logger.exception(
                        "Final vector metadata sync is pending for document %s.",
                        document_id,
                        extra={
                            "event": "document.vector_metadata.sync_pending",
                            "document_id": document_id,
                        },
                    )

        return document

    except PromptInjectionError:
        db.rollback()
        document.is_current = False
        db.commit()
        update_document_status(db, document.id, DocumentStatus.BLOCKED)
        raise

    except Exception as exc:
        db.rollback()
        document.is_current = False
        db.commit()
        failed = update_document_status(db, document.id, DocumentStatus.FAILED)

        if vector_write_attempted:
            # set_payload may have reached Qdrant even when the client observed a
            # timeout. Reassert the quarantine so FAILED documents cannot answer.
            try:
                update_document_vector_metadata(
                    failed.id,
                    review_status=failed.review_status,
                    legal_status=failed.legal_status,
                    category=failed.category,
                    visibility=failed.visibility,
                    is_current=False,
                )
            except Exception:  # pragma: no cover - best-effort safety cleanup
                logger.exception(
                    "Could not quarantine vectors for failed document %s.",
                    failed.id,
                    extra={"event": "document.vector_quarantine.failed", "document_id": failed.id},
                )

        if isinstance(exc, DocumentIngestionError):
            raise

        raise DocumentIngestionError(f"Could not ingest document {document.id}.") from exc


def flag_conflicts_for(
    db: Session,
    document: Document,
    *,
    raw_text: str | None = None,
    commit: bool = True,
) -> list[int]:
    """Compatibility wrapper returning only flags created/found by the scan."""
    return list(
        scan_conflicts_for(
            db,
            document,
            raw_text=raw_text,
            commit=commit,
        ).conflict_ids
    )


def scan_conflicts_for(
    db: Session,
    document: Document,
    *,
    raw_text: str | None = None,
    commit: bool = True,
) -> ConflictScanOutcome:
    """Compare actual business content with older documents of the same scope.

    Price lists use unit/price rows. Other categories compare measurable business
    facts (discounts, dates, monetary amounts, deadlines, etc.) and retain a
    same-title fallback for meaningful text changes. Duplicate content is returned as
    a separate quarantine outcome rather than a conflict.
    """
    current_text = raw_text if raw_text is not None else _read_original_text(document)
    current_content_key = _content_key(current_text)
    if not current_content_key:
        raise DocumentIngestionError(f"Document {document.id} has no comparable parsed content.")
    candidates: list[
        tuple[
            Document,
            list[tuple[str, set[int], set[int]]],
            list[tuple[str, set[str], set[str]]],
        ]
    ] = []

    for sibling in list_completed_siblings(db, document.project_id, exclude_id=document.id):
        if not _same_business_scope(document, sibling):
            continue

        same_title = _title_key(sibling.title) == _title_key(document.title)
        same_identity = same_title or _shares_legal_identity(document, sibling)
        is_price_list = document.category == DocumentCategory.PRICE_LIST
        sibling_text = _read_original_text(sibling)
        sibling_content_key = _content_key(sibling_text)

        # Missing source text is not proof that the new document is conflict-free.
        # Fail closed so the ingestion handler keeps its vectors quarantined until the
        # older corpus entry is repaired or deliberately retired.
        if not sibling_content_key:
            raise DocumentIngestionError(
                f"Cannot verify conflicts because completed document {sibling.id} has no parsed source content."
            )

        # Equal normalised content is a duplicate upload, not a conflict.
        if current_content_key == sibling_content_key:
            # Exact content is a distinct outcome from both "clean" and "conflict".
            # Return before writing any deferred flags so an identical upload is
            # blocked without leaving misleading OPEN conflicts behind.
            return ConflictScanOutcome(duplicate_document_ids=(sibling.id,))
        if _meaningful_content_key(current_text) == _meaningful_content_key(sibling_text):
            return ConflictScanOutcome(duplicate_document_ids=(sibling.id,))

        price_differences: list[tuple[str, set[int], set[int]]] = []
        fact_differences = [
            *_business_fact_differences(sibling_text, current_text),
            *_textual_clause_differences(sibling_text, current_text),
        ]
        has_shared_price_scope = False
        if is_price_list:
            old_price_facts = _price_facts(sibling_text)
            new_price_facts = _price_facts(current_text)
            price_differences = _price_differences_from_facts(old_price_facts, new_price_facts)
            has_shared_price_scope = bool((old_price_facts.keys() & new_price_facts.keys()) - {"__DOCUMENT_PRICES__"})

        # Shared fact/polarity anchors compare differently named documents. The
        # same-title or same-legal-number fallback catches prose-only changes. Price
        # lists also inspect their VAT/eligibility footnotes instead of stopping after
        # seeing identical numeric rows.
        if not price_differences and not fact_differences:
            if not same_identity:
                continue
            if _meaningful_content_key(sibling_text) == _meaningful_content_key(current_text):
                return ConflictScanOutcome(duplicate_document_ids=(sibling.id,))

        # Without a project ID, require positive evidence that the documents concern
        # the same thing. Shared metadata/title is sufficient; otherwise a shared unit
        # code or fact anchor discovered in the content must provide the link.
        if not document.project_id and not (
            same_identity
            or _shares_explicit_scope(document, sibling)
            or _has_content_scope_evidence(has_shared_price_scope, fact_differences)
        ):
            continue

        candidates.append((sibling, price_differences, fact_differences))

    created: list[int] = []
    for sibling, price_differences, fact_differences in candidates:
        conflict = create_conflict(
            db,
            document_id_a=sibling.id,
            document_id_b=document.id,
            description=(
                f"Phát hiện nội dung khác nhau giữa '{sibling.title}' và "
                f"'{document.title}' trong cùng phạm vi áp dụng."
                f"{_format_price_differences(price_differences)}"
                f"{_format_fact_differences(fact_differences)} "
                "Kiểm tra và chọn bản được ưu tiên."
            ),
            commit=False,
        )
        created.append(conflict.id)

    if commit:
        db.commit()

    return ConflictScanOutcome(conflict_ids=tuple(created))


@contextmanager
def _conflict_scope_lock(db: Session, document: Document) -> Iterator[None]:
    """Use a MySQL advisory lock to serialize conflict scans for one scope.

    SQLite is used by unit tests and has no cross-connection advisory lock. Production
    MySQL holds this named lock on a dedicated connection, independent of commits made
    by the ingestion session, until the compare-and-activate section has finished.
    """
    bind = db.get_bind()
    if bind.dialect.name != "mysql":
        yield
        return

    scope = f"{document.project_id or '__global__'}:{document.category}"
    digest = hashlib.sha256(scope.encode("utf-8")).hexdigest()[:40]
    lock_name = f"salesmate-ingest:{digest}"

    # Every preceding ingestion write is committed at this point. End any read
    # transaction created by refresh/classification before waiting: under MySQL
    # REPEATABLE READ it could otherwise keep a snapshot from before another upload
    # committed while this request waited for GET_LOCK.
    db.rollback()
    db.expire_all()
    # Reserve the Session's DB connection first. If every concurrent upload acquired
    # a dedicated advisory-lock connection and only then asked the pool for its scan
    # connection, the pool could starve with all named locks held.
    db.connection()

    with bind.connect() as lock_connection:
        acquired = lock_connection.execute(
            text("SELECT GET_LOCK(:lock_name, :timeout_seconds)"),
            {"lock_name": lock_name, "timeout_seconds": 30},
        ).scalar()
        if acquired != 1:
            raise DocumentIngestionError("Timed out waiting for the document conflict-scan lock.")
        try:
            yield
        finally:
            try:
                lock_connection.execute(
                    text("SELECT RELEASE_LOCK(:lock_name)"),
                    {"lock_name": lock_name},
                )
            except Exception:  # pragma: no cover - connection cleanup only
                logger.exception(
                    "Could not release ingestion conflict lock %s.",
                    lock_name,
                    extra={"event": "document.conflict_lock.release_failed"},
                )
                # GET_LOCK belongs to the physical connection. Never return a
                # connection whose lock release is uncertain back to the pool.
                lock_connection.invalidate()


def _title_key(title: str | None) -> str:
    """Normalise a title while ignoring file format, version and period suffixes."""
    if not title:
        return ""
    normalised = strip_diacritics(PurePath(title).stem)
    normalised = re.sub(r"[^a-z0-9]+", " ", normalised)
    normalised = re.sub(
        r"\b(?:v|ver|version|phien\s+ban)\s*\d+(?:\s+\d+){0,2}\b",
        " ",
        normalised,
    )
    normalised = re.sub(r"\b(?:thang|dot|ky)\s+\d{1,4}(?:\s+20\d{2})?\b", " ", normalised)
    normalised = re.sub(r"\b(?:quy|q)\s*[1-4](?:\s+20\d{2})?\b", " ", normalised)
    return " ".join(normalised.split())


def _content_key(text: str) -> str:
    """Collapse formatting differences before deciding whether content changed."""
    return " ".join(strip_diacritics(text.replace("\x00", "")).split())


def _meaningful_content_key(text: str) -> str:
    """Ignore layout punctuation while retaining operators that can change meaning."""
    normalised = text.replace("\x00", "").translate(str.maketrans({"≤": "<=", "≥": ">=", "≠": "!="}))
    normalised = strip_diacritics(normalised)
    normalised = re.sub(r"[^a-z0-9%<>=+!]+", " ", normalised)
    normalised = re.sub(r"\s*([%<>=+!])\s*", r"\1", normalised)
    return " ".join(normalised.split())


_UNIT_CODE_RE = re.compile(
    r"\b(?:"
    r"(?=[A-Z0-9.-]*[A-Z])(?=[A-Z0-9.-]*\d)[A-Z0-9]+(?:[-.][A-Z0-9]+)+"
    r"|(?:[A-Z]{2,3}\d{1,4}|[A-Z]\d{2,4})"
    r")\b",
    re.IGNORECASE,
)
_NON_UNIT_CODE_RE = re.compile(
    r"^(?:DOT|THANG|NAM|QUY|PN|CSBH|VND|TANG|LOAI|STT|GIA|MA|CAN|KY|LAN)\d+$",
    re.IGNORECASE,
)
_PRICE_RE = re.compile(
    r"(?<!\w)(\d{1,3}(?:[.,]\d{3}){2,}|\d+(?:[.,]\d+)?)\s*"
    r"(tỷ|ty|triệu|trieu|tr|million|billion|vnđ|vnd|đ|đồng|dong)\b",
    re.IGNORECASE,
)
_COMPOUND_PRICE_RE = re.compile(
    r"(?<!\w)(?P<billions>\d+(?:[.,]\d+)?)\s*(?:tỷ|ty|billion)\s*"
    r"(?P<millions>\d+(?:[.,]\d+)?)\s*(?:triệu|trieu|tr|million)\b",
    re.IGNORECASE,
)
_BARE_GROUPED_VND_RE = re.compile(r"(?<!\w)(\d{1,3}(?:[.,]\d{3})+)(?!\w)")
_VND_TABLE_CONTEXT_RE = re.compile(
    r"(?:gia|don\s+gia).{0,40}\b(?:vnd|dong)\b|\b(?:vnd|dong)\b.{0,40}(?:gia|don\s+gia)",
    re.IGNORECASE,
)
_FACT_VALUE_RE = re.compile(
    r"(?P<date>\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b)"
    r"|(?P<percent>(?<!\w)\d+(?:[.,]\d+)?\s*(?:%|phan\s+tram))"
    r"|(?P<money>(?<!\w)(?:\d{1,3}(?:[.,]\d{3}){2,}|\d+(?:[.,]\d+)?)\s*"
    r"(?:ty|trieu|tr|million|billion|vnd|dong)\b)"
    r"|(?P<measure>(?<!\w)\d+(?:[.,]\d+)?\s*"
    r"(?:ngay|thang|nam|dot|ky|lan|m2|m²|can|suat)\b)",
    re.IGNORECASE,
)
_NORMALIZED_MONEY_RE = re.compile(
    r"(\d{1,3}(?:[.,]\d{3}){2,}|\d+(?:[.,]\d+)?)\s*"
    r"(ty|trieu|tr|million|billion|vnd|dong)",
    re.IGNORECASE,
)


_SCOPE_FIELDS = ("subdivision_names", "building_codes", "unit_types")


def _scope_values(document: Document, field: str) -> set[str]:
    return {key for value in (getattr(document, field) or []) if (key := _metadata_key(str(value)))}


def _metadata_key(value: str | None) -> str:
    if not value:
        return ""
    normalised = strip_diacritics(value)
    return " ".join(re.sub(r"[^a-z0-9+]+", " ", normalised).split())


def _same_business_scope(left: Document, right: Document) -> bool:
    """Compare scope using location before the narrower unit-type hint.

    Subdivision and building are strong location boundaries: populated, disjoint values
    prove that two documents concern different places. A shared building, however, keeps
    the documents comparable even when their extracted unit-type lists differ; that
    difference can itself represent a price list adding or removing a product type.
    Missing metadata remains "unknown", not proof of separation.
    """
    if left.category != right.category:
        return False

    for field in ("subdivision_names", "building_codes"):
        left_values = _scope_values(left, field)
        right_values = _scope_values(right, field)
        if left_values and right_values and not left_values & right_values:
            return False

    shares_location = any(
        _scope_values(left, field) & _scope_values(right, field) for field in ("subdivision_names", "building_codes")
    )
    if shares_location:
        return True

    left_unit_types = _scope_values(left, "unit_types")
    right_unit_types = _scope_values(right, "unit_types")
    if left_unit_types and right_unit_types and not left_unit_types & right_unit_types:
        return False
    return True


def _shares_explicit_scope(left: Document, right: Document) -> bool:
    """True when both documents name at least one identical subdivision, building or unit type.

    The strict counterpart to `_same_business_scope`, for documents carrying no project:
    there, "might overlap" would match everything, so real evidence is required.
    """
    return any(_scope_values(left, field) & _scope_values(right, field) for field in _SCOPE_FIELDS)


def _shares_legal_identity(left: Document, right: Document) -> bool:
    """A legal document number is a stronger identity anchor than its upload title."""
    if left.category != DocumentCategory.LEGAL_DOCUMENT or right.category != DocumentCategory.LEGAL_DOCUMENT:
        return False
    left_number = _metadata_key(left.legal_document_number)
    right_number = _metadata_key(right.legal_document_number)
    return bool(left_number and right_number and left_number == right_number)


def _business_fact_differences(
    old_text: str,
    new_text: str,
) -> list[tuple[str, set[str], set[str]]]:
    """Find shared policy clauses/table rows whose measurable values changed.

    The anchor is the normalised line with the measurable value replaced by a token.
    This deliberately requires the surrounding wording to agree; two unrelated numbers
    in the same project are not enough to raise a conflict.
    """
    old_facts = _business_facts(old_text)
    new_facts = _business_facts(new_text)
    return [
        (anchor, old_facts[anchor], new_facts[anchor])
        for anchor in sorted(old_facts.keys() & new_facts.keys())
        if old_facts[anchor] != new_facts[anchor]
    ]


_CLAUSE_POLARITY_RE = re.compile(r"\b(?:khong|chua|da)\b", re.IGNORECASE)
_NEGATIVE_CLAUSE_RE = re.compile(r"\b(?:khong|chua)\b", re.IGNORECASE)
_BUSINESS_CLAUSE_RE = re.compile(
    r"\b(?:khach|gia|vat|chiet\s+khau|thanh\s+toan|dat\s+coc|qua\s+tang|uu\s+dai|"
    r"ap\s+dung|ho\s+tro|lai\s+suat|ban\s+giao|so\s+huu|duoc|phai|bao\s+gom|gom)\b",
    re.IGNORECASE,
)


def _textual_clause_differences(
    old_text: str,
    new_text: str,
) -> list[tuple[str, set[str], set[str]]]:
    """Detect affirmative/negative changes in otherwise identical business clauses."""
    old_facts = _textual_clause_facts(old_text)
    new_facts = _textual_clause_facts(new_text)
    return [
        (f"text:{anchor}", old_facts[anchor], new_facts[anchor])
        for anchor in sorted(old_facts.keys() & new_facts.keys())
        if old_facts[anchor] != new_facts[anchor]
    ]


def _textual_clause_facts(text: str) -> dict[str, set[str]]:
    facts: dict[str, set[str]] = {}
    for raw_line in text.splitlines():
        line = " ".join(strip_diacritics(raw_line).split())
        if not _BUSINESS_CLAUSE_RE.search(line):
            continue
        polarity = "negative" if _NEGATIVE_CLAUSE_RE.search(line) else "affirmative"
        anchor = _CLAUSE_POLARITY_RE.sub(" ", line)
        anchor = " ".join(re.sub(r"[^a-z0-9]+", " ", anchor).split())
        if len(anchor.split()) < 3:
            continue
        facts.setdefault(anchor, set()).add(polarity)
    return facts


def _business_facts(text: str) -> dict[str, set[str]]:
    facts: dict[str, set[str]] = {}
    for raw_line in text.splitlines():
        line = " ".join(strip_diacritics(raw_line).split())
        values: list[str] = []

        def replace_value(match: re.Match[str]) -> str:
            slot = len(values)
            values.append(_normalise_fact_value(match))
            return f" <value{slot}> "

        anchor = _FACT_VALUE_RE.sub(replace_value, line)
        if not values:
            continue

        anchor = " ".join(re.sub(r"[^a-z0-9<>]+", " ", anchor).split())
        # A bare table value or a generic heading is too weak an anchor. Require some
        # actual business wording/code around the value placeholder.
        words = [word for word in anchor.split() if not word.startswith("<value")]
        if not words or len(" ".join(words)) < 3:
            continue
        for slot, value in enumerate(values):
            facts.setdefault(f"{anchor} [slot {slot}]", set()).add(value)
    return facts


def _normalise_fact_value(match: re.Match[str]) -> str:
    value = " ".join(match.group(0).lower().split())
    if match.lastgroup == "money":
        money = _NORMALIZED_MONEY_RE.fullmatch(value)
        if money:
            return f"{_price_to_vnd(money.group(1), money.group(2)):,} VND"
    if match.lastgroup == "percent":
        number = re.search(r"\d+(?:[.,]\d+)?", value)
        if number:
            return f"{float(number.group(0).replace(',', '.')):g}%"
    if match.lastgroup == "date":
        parts = re.split(r"[/-]", value)
        if len(parts) == 3:
            year = int(parts[2])
            if year < 100:
                year += 2000
            return f"{int(parts[0]):02d}/{int(parts[1]):02d}/{year:04d}"
    return value.replace(",", ".")


def _has_content_scope_evidence(
    has_shared_price_scope: bool,
    fact_differences: list[tuple[str, set[str], set[str]]],
) -> bool:
    # Unkeyed prices do not tie two project-less documents together. A shared unit
    # code present on both sides or a shared policy anchor does. A unit appearing on
    # only one side is a meaningful change only after title/metadata/project already
    # tied the documents together; by itself it must not join unrelated global files.
    return bool(fact_differences or has_shared_price_scope)


def _price_facts(text: str) -> dict[str, set[int]]:
    """Extract unit/product identifiers and prices from table-like lines."""
    facts: dict[str, set[int]] = {}
    unkeyed: set[int] = set()
    # Extracted tables commonly put the unit only in a header such as
    # "| Mã căn | Giá bán (VNĐ) |". Rows then contain a bare grouped number.
    vnd_table_context = _VND_TABLE_CONTEXT_RE.search(strip_diacritics(text)) is not None
    for line in text.splitlines():
        prices = _line_prices(line, vnd_table_context=vnd_table_context)
        prices.discard(0)
        if not prices:
            continue
        codes = set()
        for match in _UNIT_CODE_RE.finditer(line):
            raw_code = match.group(0).upper()
            compact_code = re.sub(r"[^A-Z0-9]", "", raw_code)
            if _NON_UNIT_CODE_RE.fullmatch(compact_code):
                continue
            codes.add(re.sub(r"[-.]+", "-", raw_code))
        if codes:
            for code in codes:
                facts.setdefault(code, set()).update(prices)
        else:
            unkeyed.update(prices)
    if unkeyed:
        facts["__DOCUMENT_PRICES__"] = unkeyed
    return facts


def _line_prices(line: str, *, vnd_table_context: bool) -> set[int]:
    prices: set[int] = set()
    compound_spans: list[tuple[int, int]] = []
    for match in _COMPOUND_PRICE_RE.finditer(line):
        compound_spans.append(match.span())
        prices.add(_price_to_vnd(match.group("billions"), "ty") + _price_to_vnd(match.group("millions"), "trieu"))

    for match in _PRICE_RE.finditer(line):
        if any(start <= match.start() and match.end() <= end for start, end in compound_spans):
            continue
        prices.add(_price_to_vnd(match.group(1), match.group(2)))

    if not prices and vnd_table_context:
        prices.update(_price_to_vnd(match.group(1), "VND") for match in _BARE_GROUPED_VND_RE.finditer(line))
    return prices


def _price_to_vnd(number: str, unit: str) -> int:
    compact = number.strip()
    normalised_unit = strip_diacritics(unit).lower()
    if normalised_unit in {"vnd", "dong", "d"} and re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", compact):
        return int(re.sub(r"[.,]", "", compact))
    if normalised_unit in {"trieu", "tr", "million"} and re.fullmatch(r"\d{1,3}(?:\.\d{3})+", compact):
        return int(compact.replace(".", "")) * 1_000_000
    if normalised_unit in {"ty", "billion"} and re.fullmatch(r"\d{1,3}(?:\.\d{3}){2,}", compact):
        return int(compact.replace(".", "")) * 1_000_000_000
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
    return _price_differences_from_facts(old_facts, new_facts)


def _price_differences_from_facts(
    old_facts: dict[str, set[int]],
    new_facts: dict[str, set[int]],
) -> list[tuple[str, set[int], set[int]]]:
    return [
        (key, old_facts.get(key, set()), new_facts.get(key, set()))
        for key in sorted(old_facts.keys() | new_facts.keys())
        if old_facts.get(key, set()) != new_facts.get(key, set())
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


def _format_fact_differences(
    differences: list[tuple[str, set[str], set[str]]],
) -> str:
    if not differences:
        return ""
    samples = []
    for anchor, old_values, new_values in differences[:5]:
        label = re.sub(r"<value\d+>", "…", anchor)[:100]
        old_value = "/".join(sorted(old_values))
        new_value = "/".join(sorted(new_values))
        samples.append(f" {label}: {old_value} → {new_value}")
    return " Các điều khoản thay đổi:" + ";".join(samples) + "."


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
