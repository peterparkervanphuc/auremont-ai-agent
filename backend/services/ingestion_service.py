import re
import uuid
from io import BytesIO
from pathlib import PurePath

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.enums import DocumentStatus
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
            raise PromptInjectionError(
                "Potential prompt-injection content detected."
            )

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
            auto_approve=(
                classification.confidence
                >= settings.classification_auto_approve_threshold
            ),
        )

        object_key = _store_original_file(
            document_id=document.id,
            filename=filename,
            file_bytes=file_bytes,
            content_type=content_type,
        )
        update_document_storage_path(db, document.id, object_key)

        chunks = chunk_sections(sections)
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
            flag_conflicts_for(db, completed)
        except Exception as exc:  # pragma: no cover - advisory step, never fatal
            print(f"Conflict detection skipped for document {completed.id}: {exc}")

        return completed

    except PromptInjectionError:
        update_document_status(db, document.id, DocumentStatus.BLOCKED)
        raise

    except Exception as exc:
        update_document_status(db, document.id, DocumentStatus.FAILED)

        if isinstance(exc, DocumentIngestionError):
            raise

        raise DocumentIngestionError(
            f"Could not ingest document {document.id}."
        ) from exc


def flag_conflicts_for(db: Session, document: Document) -> list[int]:
    """Flag older documents of the same project that the new upload may contradict.

    Implements the README §5.4 row "Hai tài liệu mâu thuẫn nội dung": two price-list
    versions of one project cannot both be authoritative, so an Admin has to decide
    which one wins (Tab 3 → keep new / delete old).

    Matching is on the **normalised title** rather than the document body. Comparing
    full text would need another LLM pass on every upload — too slow and too costly
    for something that only raises an advisory flag — while in practice the repeated
    upload of "Bảng giá Ocean Park 3" is exactly the case this needs to catch.
    Diacritics are stripped so "Bang gia" and "Bảng giá" are treated as the same title.

    Returns the ids of the conflict flags created (empty when nothing conflicts).
    """
    title_key = _title_key(document.title)
    if not title_key:
        return []

    created: list[int] = []
    for sibling in list_completed_siblings(db, document.project_id, exclude_id=document.id):
        if _title_key(sibling.title) != title_key:
            continue

        conflict = create_conflict(
            db,
            document_id_a=sibling.id,
            document_id_b=document.id,
            description=(
                f"Hai tài liệu cùng dự án có tiêu đề trùng nhau: '{sibling.title}'. "
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


def _store_original_file(
    *,
    document_id: int,
    filename: str,
    file_bytes: bytes,
    content_type: str | None,
) -> str:
    """Store the original file in MinIO; the DB keeps only the object key."""
    safe_filename = PurePath(filename).name
    object_key = (
        f"documents/{document_id}/"
        f"{uuid.uuid4().hex}-{safe_filename}"
    )

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
        raise DocumentIngestionError(
            "Could not store original file in MinIO."
        ) from exc

    return object_key
