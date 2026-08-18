from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.deps import require_role
from backend.core.enums import UserRole
from backend.core.mysql_client import get_db
from backend.models.user import User
from backend.repositories.conflict_flag import list_open_conflicts, resolve_conflict
from backend.schemas.conflict_flag import ConflictFlagResponse, ConflictResolveRequest
from backend.services.vector_store_service import VectorStoreError, update_document_vector_metadata

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
    """Delete the old document / prefer the new one — the document not kept is removed from the store."""
    try:
        conflict, superseded = resolve_conflict(
            db,
            conflict_id,
            keep_document_id=payload.keep_document_id,
            resolved_by=admin.id,
        )
        if superseded is not None:
            # Mirror the decision into Qdrant. Until this lands, retrieval still reads
            # the rejected document — the Admin's choice would be cosmetic.
            update_document_vector_metadata(
                superseded.id,
                review_status=superseded.review_status,
                legal_status=superseded.legal_status,
                category=superseded.category,
                is_current=False,
            )
        return conflict
    except ValueError as exc:
        # keep_document_id is not one of the flag's two documents -> bad request
        # payload, not a "not found" condition.
        if "not part of conflict" in str(exc):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except VectorStoreError as exc:
        # The MySQL decision is already committed. Say so plainly rather than reporting
        # success: until the payload is synced the rejected document still answers.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Conflict was resolved but the rejected document is still active in the vector store.",
        ) from exc
