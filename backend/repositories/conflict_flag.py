from sqlalchemy.orm import Session

from backend.core.enums import ConflictStatus, DocumentStatus
from backend.models.conflict_flag import ConflictFlag
from backend.models.document import Document
from backend.utils.time import utcnow


def create_conflict(db: Session, document_id_a: int, document_id_b: int, description: str | None) -> ConflictFlag:
    conflict = ConflictFlag(
        document_id_a=document_id_a,
        document_id_b=document_id_b,
        description=description,
        status=ConflictStatus.OPEN,
    )
    db.add(conflict)
    db.commit()
    db.refresh(conflict)
    return conflict


def list_open_conflicts(db: Session) -> list[ConflictFlag]:
    return db.query(ConflictFlag).filter(ConflictFlag.status == ConflictStatus.OPEN).all()


def resolve_conflict(
    db: Session,
    conflict_id: int,
    keep_document_id: int,
    resolved_by: int | None = None,
) -> tuple[ConflictFlag, Document | None]:
    """Close a conflict flag: keep one document, disable the other.

    `keep_document_id` must be one of the flag's two documents — otherwise the
    Admin's decision would be applied to the wrong document.

    Returns the flag together with the document that lost, so the caller can push
    `is_current=False` into that document's Qdrant payload. Retrieval reads Qdrant,
    not MySQL, so without that follow-up the "losing" document keeps answering.
    """
    conflict = db.query(ConflictFlag).filter(ConflictFlag.id == conflict_id).first()
    if conflict is None:
        raise ValueError(f"ConflictFlag with id={conflict_id} not found.")

    pair = (conflict.document_id_a, conflict.document_id_b)
    if keep_document_id not in pair:
        raise ValueError(f"keep_document_id={keep_document_id} is not part of conflict {conflict_id} {pair}.")

    superseded_id = conflict.document_id_b if keep_document_id == conflict.document_id_a else conflict.document_id_a

    # "Delete the old document / prefer the new one": mark it BLOCKED rather than
    # DELETE. The flag row still references this document via a foreign key, so a
    # hard delete would violate the constraint; BLOCKED both removes it from the
    # knowledge base and preserves the audit trail.
    #
    # `is_current` has to come down too. BLOCKED alone is invisible to retrieval:
    # rag_service filters on visibility/review_status/is_current and never looks at
    # `status`, so a document rejected here would go on grounding answers as if the
    # Admin had never decided anything.
    superseded = db.query(Document).filter(Document.id == superseded_id).first()
    if superseded is not None:
        superseded.status = DocumentStatus.BLOCKED
        superseded.is_current = False

    conflict.status = ConflictStatus.RESOLVED
    conflict.resolved_at = utcnow()
    conflict.resolved_by = resolved_by

    db.commit()
    db.refresh(conflict)
    if superseded is not None:
        db.refresh(superseded)
    return conflict, superseded
