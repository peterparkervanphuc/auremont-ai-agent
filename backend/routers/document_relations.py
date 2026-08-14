from fastapi import APIRouter, Depends, HTTPException, status
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
    try:
        relation, superseded = review_document_relation(
            db,
            relation_id,
            approve=payload.approve,
            reviewed_by=admin.id,
        )
        if superseded is not None:
            update_document_vector_metadata(
                superseded.id,
                review_status=superseded.review_status,
                legal_status=superseded.legal_status,
                category=superseded.category,
                is_current=False,
            )
        return relation
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except VectorStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Relation was reviewed but vector metadata could not be synced.",
        ) from exc
