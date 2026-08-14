from sqlalchemy.orm import Session

from backend.core.enums import DocumentRelationType, DocumentReviewStatus, LegalStatus
from backend.models.document import Document
from backend.models.document_relation import DocumentRelation
from backend.schemas.document_relation import DocumentRelationCreate
from backend.utils.time import utcnow


def create_document_relation(db: Session, payload: DocumentRelationCreate) -> DocumentRelation:
    if payload.source_document_id == payload.target_document_id:
        raise ValueError("A document cannot have a relation with itself.")

    ids = {payload.source_document_id, payload.target_document_id}
    found = {row.id for row in db.query(Document.id).filter(Document.id.in_(ids)).all()}
    if found != ids:
        raise ValueError("One or both documents do not exist.")

    relation = DocumentRelation(**payload.model_dump())
    db.add(relation)
    db.commit()
    db.refresh(relation)
    return relation


def list_document_relations(
    db: Session,
    *,
    pending_only: bool = False,
) -> list[DocumentRelation]:
    query = db.query(DocumentRelation)
    if pending_only:
        query = query.filter(DocumentRelation.review_status == DocumentReviewStatus.PENDING)
    return query.order_by(DocumentRelation.created_at.desc()).all()


def review_document_relation(
    db: Session,
    relation_id: int,
    *,
    approve: bool,
    reviewed_by: int,
) -> tuple[DocumentRelation, Document | None]:
    relation = db.query(DocumentRelation).filter(DocumentRelation.id == relation_id).first()
    if relation is None:
        raise ValueError(f"DocumentRelation with id={relation_id} not found.")
    if relation.review_status != DocumentReviewStatus.PENDING:
        raise ValueError("This relation has already been reviewed.")

    relation.review_status = (
        DocumentReviewStatus.APPROVED if approve else DocumentReviewStatus.REJECTED
    )
    relation.reviewed_by = reviewed_by
    relation.reviewed_at = utcnow()

    superseded: Document | None = None
    inactive_relations = {
        DocumentRelationType.REPLACES,
        DocumentRelationType.SUPERSEDES,
        DocumentRelationType.REPEALS,
    }
    if approve and relation.relation_type in inactive_relations:
        superseded = db.query(Document).filter(Document.id == relation.target_document_id).first()
        if superseded is not None:
            superseded.is_current = False
            if relation.relation_type == DocumentRelationType.REPEALS:
                superseded.legal_status = LegalStatus.REPEALED
            elif superseded.category == "legal_document":
                superseded.legal_status = LegalStatus.REPLACED

    db.commit()
    db.refresh(relation)
    if superseded is not None:
        db.refresh(superseded)
    return relation, superseded
