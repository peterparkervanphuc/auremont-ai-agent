import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.core.deps import require_role
from backend.core.enums import UserRole
from backend.core.mysql_client import get_db
from backend.models.user import User
from backend.repositories.conflict_flag import list_open_conflicts, resolve_conflict
from backend.repositories.document import get_document
from backend.schemas.conflict_flag import ConflictFlagResponse, ConflictResolveRequest
from backend.services.vector_store_service import VectorStoreError, update_document_vector_metadata

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/conflicts", tags=["Admin Conflicts"], dependencies=[Depends(require_role(UserRole.ADMIN))]
)


@router.get("", response_model=list[ConflictFlagResponse])
async def get_conflicts(db: Session = Depends(get_db)) -> list[ConflictFlagResponse]:
    """conflicting documents (e.g. two price-list versions of the same project)."""
    return list_open_conflicts(db)


@router.post("/{conflict_id}/resolve", response_model=ConflictFlagResponse)
async def resolve_conflict_flag(
    conflict_id: int,
    payload: ConflictResolveRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> ConflictFlagResponse:
    """Keep the Admin's chosen document and atomically disable the other one."""
    attempted_vector_ids: set[int] = set()
    previous_vector_metadata: dict[int, dict[str, str | bool]] = {}
    try:
        conflict, kept, superseded, previous_vector_metadata = resolve_conflict(
            db,
            conflict_id,
            keep_document_id=payload.keep_document_id,
            resolved_by=admin.id,
            commit=False,
        )
    except ValueError as exc:
        db.rollback()
        # keep_document_id is not one of the flag's two documents -> bad request
        # payload, not a "not found" condition.
        if "not part of conflict" in str(exc):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if (
            "already been resolved" in str(exc)
            or "not an active completed document" in str(exc)
            or "not eligible to win a conflict" in str(exc)
        ):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Conflict could not be prepared for resolution.",
        ) from exc

    # Phase 1 is strictly fail-closed: write the new review metadata for both
    # endpoints but quarantine both. A timeout can therefore never publish an Admin
    # decision that has not yet committed in MySQL.
    try:
        for document in (superseded, kept):
            attempted_vector_ids.add(document.id)
            update_document_vector_metadata(
                document.id,
                review_status=document.review_status,
                legal_status=document.legal_status,
                category=document.category,
                visibility=document.visibility,
                is_current=False,
            )
    except VectorStoreError as exc:
        # Restore Qdrant while the MySQL row locks are still held. Rolling back first
        # would let a second Admin commit a newer choice that this compensation could
        # then overwrite with stale metadata.
        try:
            _restore_vector_metadata(previous_vector_metadata, attempted_vector_ids)
        finally:
            db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Conflict was not resolved because document retrieval metadata could not be synchronised.",
        ) from exc

    try:
        db.commit()
    except SQLAlchemyError as exc:
        # COMMIT may have reached MySQL even when its acknowledgement was lost. Never
        # reactivate the old state in that ambiguous case; both Qdrant endpoints are
        # already quarantined and an audit/retry can safely reconcile availability.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Conflict endpoints remain quarantined because the MySQL commit outcome could not be confirmed.",
        ) from exc

    # Phase 2 reads the winner again under a fresh row lock. A relation or another
    # conflict may have retired it between phases, so only this fresh committed state
    # is allowed to activate Qdrant.
    try:
        kept = get_document(db, kept.id, for_update=True)
        if kept is None:
            raise ValueError("The selected conflict winner no longer exists.")
        update_document_vector_metadata(
            kept.id,
            review_status=kept.review_status,
            legal_status=kept.legal_status,
            category=kept.category,
            visibility=kept.visibility,
            is_current=kept.is_current,
        )
        db.commit()
    except (VectorStoreError, SQLAlchemyError, ValueError) as exc:
        # The MySQL decision is already committed. Leaving Qdrant quarantined is the
        # safe failure mode; never compensate back to the pre-resolution winner.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Conflict was resolved in MySQL, but the winner remains quarantined until synchronisation is retried.",
        ) from exc

    db.refresh(conflict)
    return conflict


def _restore_vector_metadata(
    previous_vector_metadata: dict[int, dict[str, str | bool]],
    document_ids: set[int],
) -> None:
    """Best-effort compensation after a partial Qdrant update."""
    selected_ids = document_ids & previous_vector_metadata.keys()
    quarantined_ids = sorted(
        document_id for document_id in selected_ids if not bool(previous_vector_metadata[document_id]["is_current"])
    )
    active_ids = sorted(selected_ids - set(quarantined_ids))

    # Do not reactivate any previously-current document unless every previously
    # quarantined document was restored successfully. If a timeout leaves the failed
    # winner active, restoring the old loser too would expose both conflicting copies.
    quarantine_restored = True
    for document_id in quarantined_ids:
        metadata = previous_vector_metadata[document_id]
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
            quarantine_restored = False
            logger.exception(
                "Could not restore vector metadata for document %s after conflict resolution failed.",
                document_id,
                extra={"event": "conflict.resolve.vector_compensation_failed", "document_id": document_id},
            )

    if not quarantine_restored:
        return

    for document_id in active_ids:
        metadata = previous_vector_metadata[document_id]
        try:
            update_document_vector_metadata(
                document_id,
                review_status=str(metadata["review_status"]),
                legal_status=str(metadata["legal_status"]),
                category=str(metadata["category"]),
                visibility=str(metadata["visibility"]),
                is_current=True,
            )
        except VectorStoreError:
            logger.exception(
                "Could not restore vector metadata for document %s after conflict resolution failed.",
                document_id,
                extra={"event": "conflict.resolve.vector_compensation_failed", "document_id": document_id},
            )
