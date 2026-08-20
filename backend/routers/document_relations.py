import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.core.deps import require_role
from backend.core.enums import UserRole
from backend.core.mysql_client import get_db
from backend.models.user import User
from backend.repositories.document_relation import (
    create_document_relation,
    list_document_relations,
    review_document_relation,
)
from backend.schemas.document_relation import (
    DocumentRelationCreate,
    DocumentRelationResponse,
    DocumentRelationReview,
)
from backend.services.vector_store_service import VectorStoreError, update_document_vector_metadata

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/document-relations",
    tags=["Document Relations (Admin)"],
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)


@router.get("", response_model=list[DocumentRelationResponse])
async def get_document_relations(
    pending_only: bool = False,
    db: Session = Depends(get_db),
) -> list[DocumentRelationResponse]:
    return list_document_relations(db, pending_only=pending_only)


@router.post("", response_model=DocumentRelationResponse, status_code=status.HTTP_201_CREATED)
async def add_document_relation(
    payload: DocumentRelationCreate,
    db: Session = Depends(get_db),
) -> DocumentRelationResponse:
    try:
        return create_document_relation(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{relation_id}/review", response_model=DocumentRelationResponse)
async def review_relation(
    relation_id: int,
    payload: DocumentRelationReview,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> DocumentRelationResponse:
    attempted_document_id: int | None = None
    previous_vector_metadata: dict[str, str | bool] | None = None
    try:
        relation, superseded, previous_vector_metadata = review_document_relation(
            db,
            relation_id,
            approve=payload.approve,
            reviewed_by=admin.id,
            commit=False,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Relation review could not be prepared.",
        ) from exc

    if superseded is not None:
        attempted_document_id = superseded.id
        try:
            update_document_vector_metadata(
                superseded.id,
                review_status=superseded.review_status,
                legal_status=superseded.legal_status,
                category=superseded.category,
                visibility=superseded.visibility,
                is_current=False,
            )
        except VectorStoreError as exc:
            try:
                # No MySQL commit has been attempted yet, so restoring the previous
                # active state is valid. Keep the target row locked while doing it.
                if previous_vector_metadata is not None:
                    _restore_document_vector_metadata(attempted_document_id, previous_vector_metadata)
            finally:
                db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Relation was not reviewed because retrieval metadata could not be synchronised.",
            ) from exc

    try:
        db.commit()
    except SQLAlchemyError as exc:
        # COMMIT may have succeeded before the connection lost its acknowledgement.
        # The target is already quarantined; do not compensate it back to current and
        # risk reviving a relation that MySQL actually committed.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The relation target remains quarantined because the MySQL commit outcome could not be confirmed.",
        ) from exc

    db.refresh(relation)
    return relation


def _restore_document_vector_metadata(
    document_id: int,
    metadata: dict[str, str | bool],
) -> None:
    """Best-effort compensation after Qdrant changed but MySQL did not commit."""
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
        logger.exception(
            "Could not restore vector metadata after relation review failed.",
            extra={"event": "document_relation.vector_compensation_failed", "document_id": document_id},
        )
