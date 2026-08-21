import logging
import time
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.core.audit import log_event
from backend.core.config import settings
from backend.core.deps import require_role
from backend.core.enums import (
    DocumentCategory,
    DocumentReviewStatus,
    DocumentStatus,
    DocumentVisibility,
    LegalStatus,
    UserRole,
)
from backend.core.minio_client import presigned_get_url
from backend.core.mysql_client import get_db
from backend.models.document import Document
from backend.models.user import User
from backend.repositories.document import (
    create_document,
    delete_document,
    get_document,
    list_documents,
    list_documents_for_metadata_edit,
    update_document_classification,
    update_document_visibility,
)
from backend.schemas.document import (
    DocumentClassificationUpdate,
    DocumentCreate,
    DocumentResponse,
)
from backend.services.cache_service import clear_cache
from backend.services.ingestion_service import (
    DocumentIngestionError,
    PromptInjectionError,
    ingest_uploaded_document,
    reclassify_document,
    reindex_document,
    sanitize_and_scan,
)
from backend.services.vector_store_service import (
    VectorStoreError,
    delete_document_vectors,
    update_document_vector_metadata,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/documents",
    tags=["Documents (Admin)"],
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)

ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".docx"}

# Leading bytes each accepted format must start with. The extension is attacker-chosen —
# renaming an HTML or script file to .pdf passes an extension check — so the content is
# verified before the parsers, which are the code most exposed to a malformed file.
# DOCX is a ZIP container, hence the PK signature.
_MAGIC_BYTES = {
    ".pdf": (b"%PDF-",),
    ".docx": (b"PK", b"PK", b"PK"),
}


def _content_matches_extension(suffix: str, file_bytes: bytes) -> bool:
    signatures = _MAGIC_BYTES.get(suffix)
    if not signatures:
        return False
    return any(file_bytes.startswith(signature) for signature in signatures)


class IngestRequest(BaseModel):
    """Legacy raw-text endpoint; kept so the older flow does not break."""

    title: str
    raw_text: str
    file_path: str | None = None
    project_id: str | None = None


class IngestResponse(BaseModel):
    document_id: int
    status: str
    message: str


class VisibilityUpdateRequest(BaseModel):
    visibility: DocumentVisibility


class ReclassifyRequest(BaseModel):
    """The corrected category. Validated against the enum so a typo cannot create a
    category nothing retrieves under."""

    category: DocumentCategory


@router.post(
    "/upload",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: UploadFile = File(...),
    project_id: str | None = Form(default=None),
    visibility: DocumentVisibility = Form(
        default=DocumentVisibility.INTERNAL,
    ),
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> IngestResponse:
    """Upload PDF/DOCX: parse → scan → MinIO → chunk → Gemini → Qdrant."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File name is required.",
        )

    suffix = Path(file.filename).suffix.lower()

    if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF and DOCX files are supported.",
        )

    file_bytes = await file.read()

    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    if not _content_matches_extension(suffix, file_bytes):
        log_event(
            "document.upload.rejected",
            filename=file.filename,
            reason="content_does_not_match_extension",
            content_type=file.content_type,
            admin_id=admin.id,
        )
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File content does not match its extension.",
        )

    if len(file_bytes) > settings.upload_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(f"File exceeds the maximum allowed size of {settings.upload_max_bytes} bytes."),
        )

    document = create_document(
        db,
        DocumentCreate(
            title=file.filename,
            project_id=project_id,
            visibility=visibility,
        ),
        uploaded_by=admin.id,
    )

    log_event(
        "document.upload",
        document_id=document.id,
        filename=file.filename,
        size_bytes=len(file_bytes),
        content_type=file.content_type,
        project_id=project_id,
        visibility=visibility,
        admin_id=admin.id,
    )

    started = time.perf_counter()
    try:
        document = ingest_uploaded_document(
            db,
            document=document,
            filename=file.filename,
            file_bytes=file_bytes,
            content_type=file.content_type,
        )
    except PromptInjectionError:
        # ingestion_service has already moved the document to BLOCKED.
        log_event(
            "document.ingest.blocked",
            document_id=document.id,
            status=DocumentStatus.BLOCKED,
            reason="prompt_injection",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return IngestResponse(
            document_id=document.id,
            status=DocumentStatus.BLOCKED,
            message="Document blocked due to suspicious content.",
        )
    except DocumentIngestionError as exc:
        # ingestion_service has already moved the document to FAILED.
        log_event(
            "document.ingest.failure",
            document_id=document.id,
            status=DocumentStatus.FAILED,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document ingestion failed. Check server logs.",
        ) from exc
    finally:
        await file.close()

    duplicate_quarantined = document.status == DocumentStatus.BLOCKED
    log_event(
        "document.ingest.duplicate_quarantined" if duplicate_quarantined else "document.ingest.success",
        document_id=document.id,
        status=document.status,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )
    return IngestResponse(
        document_id=document.id,
        status=document.status,
        message=(
            "Document was quarantined because identical content already exists."
            if duplicate_quarantined
            else "Document uploaded and indexed successfully."
        ),
    )


@router.post(
    "/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_document(
    payload: IngestRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> IngestResponse:
    """Legacy raw-text ingest endpoint."""
    try:
        sanitize_and_scan(payload.raw_text)
    except PromptInjectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Chặn file: phát hiện rủi ro",
        ) from exc

    document = create_document(
        db,
        DocumentCreate(
            title=payload.title,
            file_path=payload.file_path,
            project_id=payload.project_id,
        ),
        uploaded_by=admin.id,
    )

    return IngestResponse(
        document_id=document.id,
        status=document.status,
        message=f"Document '{document.title}' created successfully.",
    )


@router.post("/{document_id}/reindex", response_model=IngestResponse)
async def reindex_document_endpoint(
    document_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> IngestResponse:
    """Re-embed a stored document and rewrite its vectors, from the original file.

    Needed after a change to how vectors are built — enabling hybrid retrieval added a
    BM25 vector to every point, and documents ingested before that carry only a dense
    one. Run this over each document, then switch HYBRID_SEARCH_ENABLED on.
    """
    started = time.perf_counter()
    try:
        document = reindex_document(db, document_id=document_id)
    except DocumentIngestionError as exc:
        log_event(
            "document.reindex.failure",
            document_id=document_id,
            admin_id=admin.id,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not re-index document {document_id}. Check server logs.",
        ) from exc

    log_event(
        "document.reindex.success",
        document_id=document.id,
        admin_id=admin.id,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )
    return IngestResponse(
        document_id=document.id,
        status=document.status,
        message="Document re-indexed successfully.",
    )


@router.post("/{document_id}/reclassify", response_model=DocumentResponse)
async def reclassify_document_endpoint(
    document_id: int,
    payload: ReclassifyRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> Document:
    """Correct a document's category, re-chunking and re-scanning it for conflicts.

    The classification-review endpoint deliberately refuses category changes, since the
    category decides how the file is chunked and how conflicts are compared. This is the
    controlled path that does that work — previously the only way to fix a misclassified
    document was to delete it, rename the file and upload it again.
    """
    started = time.perf_counter()
    try:
        document = reclassify_document(
            db,
            document_id=document_id,
            category=payload.category,
            reviewed_by=admin.id,
        )
    except DocumentIngestionError as exc:
        log_event(
            "document.reclassify.failure",
            document_id=document_id,
            to_category=payload.category,
            admin_id=admin.id,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        # The document stays quarantined on every failure path, so this is safe to retry.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    log_event(
        "document.reclassify.success",
        document_id=document.id,
        to_category=payload.category,
        is_current=document.is_current,
        admin_id=admin.id,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )
    # The document's chunks and category both changed, so answers cached from it are stale.
    _clear_answer_cache()
    return document


@router.get("", response_model=list[DocumentResponse])
async def get_documents(
    db: Session = Depends(get_db),
) -> list[Document]:
    return list_documents(db)


@router.get("/{document_id}/view-url")
async def get_document_view_url(
    document_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Temporary signed link (expires after a few minutes) to view the original file —
    the document bucket is private, so the object key cannot be linked to directly."""
    document = get_document(db, document_id)
    if document is None or not document.file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document has no stored file yet.",
        )

    url = presigned_get_url(settings.minio_bucket_documents, document.file_path)
    return {"url": url}


@router.patch(
    "/{document_id}/visibility",
    response_model=DocumentResponse,
)
async def set_document_visibility(
    document_id: int,
    payload: VisibilityUpdateRequest,
    db: Session = Depends(get_db),
) -> DocumentResponse:
    document = get_document(db, document_id, for_update=True)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with id={document_id} not found.",
        )
    if document.status != DocumentStatus.COMPLETED:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document visibility can change only after ingestion completes (status={document.status}).",
        )
    if document.visibility == payload.visibility:
        db.commit()
        db.refresh(document)
        return document

    previous_metadata = _vector_metadata_snapshot(document)
    loosening_access = (
        document.visibility == DocumentVisibility.INTERNAL and payload.visibility == DocumentVisibility.PUBLIC
    )

    if loosening_access:
        # Phase 1 is fail-closed: quarantine the points while holding the row lock,
        # then commit PUBLIC in MySQL. No failure can expose the document early.
        quarantine_attempted = False
        try:
            quarantine_attempted = True
            update_document_vector_metadata(
                document.id,
                review_status=document.review_status,
                legal_status=document.legal_status,
                category=document.category,
                visibility=document.visibility,
                is_current=False,
            )
            update_document_visibility(db, document_id, payload.visibility, commit=False)
            db.commit()
        except (VectorStoreError, SQLAlchemyError, ValueError) as exc:
            try:
                if quarantine_attempted:
                    _restore_document_vector_metadata(document.id, previous_metadata)
            finally:
                db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Document visibility was not changed because retrieval could not be safely quarantined.",
            ) from exc

        # Phase 2 obtains a fresh row lock after the commit. A conflict/relation that
        # ran between phases may have set is_current=false; publishing that fresh value
        # prevents this request from reactivating a newly blocked document.
        try:
            document = get_document(db, document_id, for_update=True)
            if document is None:  # pragma: no cover - deletion also needs the same row lock
                raise ValueError(f"Document with id={document_id} not found.")
            update_document_vector_metadata(
                document.id,
                review_status=document.review_status,
                legal_status=document.legal_status,
                category=document.category,
                visibility=document.visibility,
                is_current=_safe_vector_current(document),
            )
            db.commit()
            db.refresh(document)
            _clear_answer_cache()
            return document
        except (VectorStoreError, SQLAlchemyError, ValueError) as exc:
            # Do not reactivate from a stale snapshot. Qdrant remains quarantined (or
            # the timed-out write already applied the fresh DB state), both fail-safe.
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Visibility changed in MySQL, but retrieval remains quarantined until synchronisation is retried.",
            ) from exc

    # Tightening PUBLIC -> INTERNAL reaches Qdrant before the MySQL commit while the
    # row remains locked. If either operation fails, any partial Qdrant result is more
    # restrictive than the still-public DB state and is therefore safe.
    try:
        document = update_document_visibility(
            db,
            document_id,
            payload.visibility,
            commit=False,
        )
        update_document_vector_metadata(
            document.id,
            review_status=document.review_status,
            legal_status=document.legal_status,
            category=document.category,
            visibility=document.visibility,
            is_current=_safe_vector_current(document),
        )
        db.commit()
        db.refresh(document)
        _clear_answer_cache()
        return document
    except (VectorStoreError, SQLAlchemyError, ValueError) as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document visibility was not fully synchronised; retrieval remains on the more restrictive value.",
        ) from exc


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_document(
    document_id: int,
    db: Session = Depends(get_db),
) -> None:
    """Delete a document from the knowledge base, vectors included.

    Vectors go first, on purpose. Qdrant is what retrieval actually reads, so a row
    deleted from MySQL while its chunks survive means the Agent keeps quoting a price
    list the Admin believes is gone — and cites a `document_id` that no longer resolves.
    Dropping the vectors first makes the failure mode retryable instead: the row stays,
    the Admin sees the document still listed and can press delete again.
    """
    if get_document(db, document_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with id={document_id} not found.",
        )

    try:
        delete_document_vectors(document_id)
    except VectorStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not remove the document's vectors; nothing was deleted. Try again.",
        ) from exc

    try:
        delete_document(db, document_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    # Otherwise the Agent keeps answering from this document out of the semantic cache
    # long after the Admin deleted it, citing a document_id that no longer resolves.
    _clear_answer_cache()


@router.get(
    "/metadata-editable",
    response_model=list[DocumentResponse],
)
async def get_documents_for_metadata_edit(
    db: Session = Depends(get_db),
) -> list[Document]:
    """Ingested documents whose metadata an Admin can still correct.

    Not an approval queue — nothing waits for review to become answerable. This exists so
    legal status, effective dates and version labels can be fixed after ingestion.
    """

    return list_documents_for_metadata_edit(db)


@router.patch(
    "/{document_id}/classification",
    response_model=DocumentResponse,
)
async def update_document_metadata(
    document_id: int,
    payload: DocumentClassificationUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> DocumentResponse:
    """Correct a document's metadata after ingestion.

    Not an approval step — the document already answers. This matters because some of the
    metadata is load-bearing: `legal_status` decides whether the document stays retrievable
    at all, so setting it to expired/repealed here takes it out of retrieval.
    """

    # Phase 1 writes the new metadata with the document quarantined, while holding its row
    # lock. A provider timeout that actually applied the payload therefore cannot leave a
    # half-written state answering.
    try:
        existing = get_document(db, document_id, for_update=True)
        if existing is None:
            raise ValueError(f"Document with id={document_id} not found.")
        document = update_document_classification(
            db,
            document_id=document_id,
            payload=payload,
            reviewed_by=admin.id,
            commit=False,
        )
        update_document_vector_metadata(
            document.id,
            review_status=document.review_status,
            legal_status=document.legal_status,
            category=document.category,
            visibility=document.visibility,
            is_current=False,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        if any(
            marker in str(exc)
            for marker in (
                "already been reviewed",
                "not ready for classification review",
                "requires quarantine, conflict rescan and controlled re-indexing",
                "requires a controlled conflict rescan",
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except (VectorStoreError, SQLAlchemyError) as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document classification was not approved because retrieval metadata could not be synchronised.",
        ) from exc

    # Phase 2 re-locks and refreshes after the commit. A conflict or relation may have
    # quarantined the document between phases; publishing the fresh is_current value
    # cannot undo that newer decision.
    try:
        refreshed = get_document(db, document_id, for_update=True)
        if refreshed is None:  # pragma: no cover - deletion also requires the row lock
            raise ValueError(f"Document with id={document_id} not found.")
        document = refreshed
        update_document_vector_metadata(
            document.id,
            review_status=document.review_status,
            legal_status=document.legal_status,
            category=document.category,
            visibility=document.visibility,
            is_current=_safe_vector_current(document),
        )
        db.commit()
        db.refresh(document)
        # Approval is what makes a document retrievable, so questions answered "we have no
        # information on that" before now must not keep serving from the cache.
        _clear_answer_cache()
        return document
    except (VectorStoreError, SQLAlchemyError, ValueError) as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document was approved in MySQL, but retrieval remains quarantined until synchronisation is retried.",
        ) from exc


def _clear_answer_cache() -> None:
    """Drop every cached answer after the document set behind them changes.

    A question answered (and cached) before the change keeps serving that stale answer
    forever otherwise — quoting a document that has since been deleted, retired by a
    conflict, reclassified, or made public/internal. The cache is keyed by question
    similarity and has no way to know which entries touched THIS document, so the only
    correct move is clearing all of it.

    Best-effort: a failure here never blocks the change that triggered it (see
    clear_cache's own fail-silent contract).
    """
    clear_cache()


def _vector_metadata_snapshot(document: Document) -> dict[str, str | bool]:
    return {
        "review_status": str(document.review_status),
        "legal_status": str(document.legal_status),
        "category": str(document.category),
        "visibility": str(document.visibility),
        "is_current": bool(document.is_current),
    }


def _safe_vector_current(document: Document) -> bool:
    """Clamp cross-store publication to states retrieval is allowed to expose."""
    return bool(
        document.is_current
        and document.status == DocumentStatus.COMPLETED
        and document.review_status != DocumentReviewStatus.REJECTED
        and document.legal_status
        not in {
            LegalStatus.NOT_YET_EFFECTIVE,
            LegalStatus.EXPIRED,
            LegalStatus.REPEALED,
            LegalStatus.REPLACED,
        }
    )


def _restore_document_vector_metadata(
    document_id: int,
    metadata: dict[str, str | bool],
) -> None:
    """Best-effort compensation while the document row remains locked."""
    try:
        update_document_vector_metadata(
            document_id,
            review_status=str(metadata["review_status"]),
            legal_status=str(metadata["legal_status"]),
            category=str(metadata["category"]),
            visibility=str(metadata["visibility"]),
            is_current=bool(metadata["is_current"]),
        )
    except VectorStoreError:
        # The MySQL rollback below leaves the document pending. The audit command
        # reports any Qdrant drift if this best-effort restoration also fails.
        logger.exception(
            "Could not restore vector metadata after classification approval failed.",
            extra={"event": "document.classification.vector_compensation_failed", "document_id": document_id},
        )
