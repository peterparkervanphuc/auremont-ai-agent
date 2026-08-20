from datetime import datetime

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from backend.core.enums import (
    ConflictStatus,
    DocumentRelationType,
    DocumentReviewStatus,
    DocumentStatus,
    LegalStatus,
)
from backend.models.conflict_flag import ConflictFlag
from backend.models.document import Document
from backend.models.document_relation import DocumentRelation
from backend.utils.time import utcnow


def create_conflict(
    db: Session,
    document_id_a: int,
    document_id_b: int,
    description: str | None,
    *,
    commit: bool = True,
) -> ConflictFlag:
    """Create one open flag per document pair.

    Conflict scans may be retried, and a document can be scanned manually after
    ingestion. Returning the existing open flag keeps those retries idempotent even
    without a schema migration for a canonical pair key.
    """
    existing = (
        db.query(ConflictFlag)
        .filter(
            ConflictFlag.status == ConflictStatus.OPEN,
            or_(
                and_(
                    ConflictFlag.document_id_a == document_id_a,
                    ConflictFlag.document_id_b == document_id_b,
                ),
                and_(
                    ConflictFlag.document_id_a == document_id_b,
                    ConflictFlag.document_id_b == document_id_a,
                ),
            ),
        )
        .first()
    )
    if existing is not None:
        return existing

    conflict = ConflictFlag(
        document_id_a=document_id_a,
        document_id_b=document_id_b,
        description=description,
        status=ConflictStatus.OPEN,
    )
    db.add(conflict)
    if commit:
        db.commit()
        db.refresh(conflict)
    else:
        # Assign the primary key and make the row visible to later pair checks in
        # the same scan, while keeping it part of the caller's transaction.
        db.flush()
    return conflict


def list_open_conflicts(db: Session) -> list[ConflictFlag]:
    return db.query(ConflictFlag).filter(ConflictFlag.status == ConflictStatus.OPEN).all()


def resolve_conflict(
    db: Session,
    conflict_id: int,
    keep_document_id: int,
    resolved_by: int | None = None,
    *,
    commit: bool = True,
) -> tuple[ConflictFlag, Document, Document, dict[int, dict[str, str | bool]]]:
    """Close a conflict flag: keep one document, disable the other.

    `keep_document_id` must be one of the flag's two documents — otherwise the
    Admin's decision would be applied to the wrong document.

    The chosen document becomes current and approved because this endpoint records an
    authenticated Admin decision. The caller may pass ``commit=False`` to synchronise
    both Qdrant payloads before committing the MySQL transaction.
    """
    seed = db.query(ConflictFlag).filter(ConflictFlag.id == conflict_id).first()
    if seed is None:
        raise ValueError(f"ConflictFlag with id={conflict_id} not found.")

    # Lock every adjacent flag in deterministic order before locking documents. A
    # triangle (A-B, A-C, B-C) could otherwise deadlock when one transaction held
    # document A while waiting for a flag row held by another transaction.
    seed_pair = (seed.document_id_a, seed.document_id_b)
    related_flags = (
        db.query(ConflictFlag)
        .filter(
            or_(
                ConflictFlag.document_id_a.in_(seed_pair),
                ConflictFlag.document_id_b.in_(seed_pair),
            )
        )
        .order_by(ConflictFlag.id)
        .populate_existing()
        .with_for_update()
        .all()
    )
    conflict = next((flag for flag in related_flags if flag.id == conflict_id), None)
    if conflict is None:
        raise ValueError(f"ConflictFlag with id={conflict_id} not found.")
    if conflict.status != ConflictStatus.OPEN:
        raise ValueError(f"ConflictFlag with id={conflict_id} has already been resolved.")

    pair = (conflict.document_id_a, conflict.document_id_b)
    if keep_document_id not in pair:
        raise ValueError(f"keep_document_id={keep_document_id} is not part of conflict {conflict_id} {pair}.")

    superseded_id = conflict.document_id_b if keep_document_id == conflict.document_id_a else conflict.document_id_a
    retirement_relations = (
        db.query(DocumentRelation)
        .filter(
            DocumentRelation.target_document_id.in_(pair),
            DocumentRelation.relation_type.in_(
                [
                    DocumentRelationType.REPLACES,
                    DocumentRelationType.SUPERSEDES,
                    DocumentRelationType.REPEALS,
                ]
            ),
        )
        .order_by(DocumentRelation.id)
        .populate_existing()
        .with_for_update()
        .all()
    )
    # Lock pending relations too. A concurrent review may be holding a PENDING row
    # while it retires the target; filtering APPROVED before waiting would use a stale
    # result and let this resolver reactivate the just-retired document.
    retired_document_ids = {
        relation.target_document_id
        for relation in retirement_relations
        if relation.review_status == DocumentReviewStatus.APPROVED
    }
    documents = (
        db.query(Document)
        .filter(Document.id.in_(sorted(pair)))
        .order_by(Document.id)
        .populate_existing()
        .with_for_update()
        .all()
    )
    documents_by_id = {document.id: document for document in documents}
    kept = documents_by_id.get(keep_document_id)
    superseded = documents_by_id.get(superseded_id)
    if kept is None or superseded is None:
        raise ValueError("One or both documents in this conflict no longer exist.")
    if kept.id in retired_document_ids or kept.legal_status in {
        LegalStatus.NOT_YET_EFFECTIVE,
        LegalStatus.EXPIRED,
        LegalStatus.REPEALED,
        LegalStatus.REPLACED,
    }:
        raise ValueError(f"Document {keep_document_id} is retired and not eligible to win a conflict.")
    if kept.status != DocumentStatus.COMPLETED:
        raise ValueError(f"Document {keep_document_id} is not an active completed document.")

    previous_vector_metadata = {
        document.id: {
            "review_status": str(document.review_status),
            "legal_status": str(document.legal_status),
            "category": str(document.category),
            "visibility": str(document.visibility),
            "is_current": bool(document.is_current),
        }
        for document in documents
    }

    # "Delete the old document / prefer the new one": mark it BLOCKED rather than
    # DELETE. The flag row still references this document via a foreign key, so a
    # hard delete would violate the constraint; BLOCKED both removes it from the
    # knowledge base and preserves the audit trail.
    #
    # `is_current` has to come down too. BLOCKED alone is invisible to retrieval:
    # rag_service filters on visibility/review_status/is_current and never looks at
    # `status`, so a document rejected here would go on grounding answers as if the
    # Admin had never decided anything.
    superseded.status = DocumentStatus.BLOCKED
    superseded.is_current = False

    resolved_at = utcnow()
    conflict.status = ConflictStatus.RESOLVED
    conflict.resolved_at = resolved_at
    conflict.resolved_by = resolved_by

    # A previous decision may already have blocked the other endpoint of a related
    # edge. Neither document can ever be selected again, so leaving that edge OPEN
    # creates an unresolvable warning in the Admin queue.
    _resolve_open_conflicts_between_blocked_documents(
        db,
        newly_blocked_document_id=superseded.id,
        resolving_conflict_id=conflict.id,
        resolved_by=resolved_by,
        resolved_at=resolved_at,
    )

    # A document can contradict more than one sibling. Resolving one edge in that
    # graph must not activate it while another OPEN edge still needs an Admin choice.
    has_other_open_conflict = (
        db.query(ConflictFlag.id)
        .filter(
            ConflictFlag.id != conflict_id,
            ConflictFlag.status == ConflictStatus.OPEN,
            or_(
                ConflictFlag.document_id_a == kept.id,
                ConflictFlag.document_id_b == kept.id,
            ),
        )
        .with_for_update()
        .first()
        is not None
    )
    kept.is_current = not has_other_open_conflict
    if kept.review_status != DocumentReviewStatus.APPROVED:
        kept.review_status = DocumentReviewStatus.APPROVED
        kept.reviewed_by = resolved_by
        kept.reviewed_at = utcnow()

    if commit:
        db.commit()
        db.refresh(conflict)
        db.refresh(kept)
        db.refresh(superseded)
    else:
        db.flush()
    return conflict, kept, superseded, previous_vector_metadata


def _resolve_open_conflicts_between_blocked_documents(
    db: Session,
    *,
    newly_blocked_document_id: int,
    resolving_conflict_id: int,
    resolved_by: int | None,
    resolved_at: datetime,
) -> None:
    """Close stale graph edges after both endpoints have become BLOCKED."""
    related = (
        db.query(ConflictFlag)
        .filter(
            ConflictFlag.id != resolving_conflict_id,
            ConflictFlag.status == ConflictStatus.OPEN,
            or_(
                ConflictFlag.document_id_a == newly_blocked_document_id,
                ConflictFlag.document_id_b == newly_blocked_document_id,
            ),
        )
        .order_by(ConflictFlag.id)
        .populate_existing()
        .with_for_update()
        .all()
    )
    if not related:
        return

    other_ids = {
        flag.document_id_b if flag.document_id_a == newly_blocked_document_id else flag.document_id_a
        for flag in related
    }
    blocked_other_ids = {
        document_id
        for (document_id,) in db.query(Document.id)
        .filter(
            Document.id.in_(other_ids),
            Document.status == DocumentStatus.BLOCKED,
        )
        # This must be a locking/current read under MySQL REPEATABLE READ. A
        # concurrent resolution may have blocked the other endpoint after this
        # transaction's initial snapshot but before it acquired the shared edge.
        .order_by(Document.id)
        .with_for_update()
        .all()
    }

    for flag in related:
        other_id = flag.document_id_b if flag.document_id_a == newly_blocked_document_id else flag.document_id_a
        if other_id in blocked_other_ids:
            flag.status = ConflictStatus.RESOLVED
            flag.resolved_at = resolved_at
            flag.resolved_by = resolved_by
