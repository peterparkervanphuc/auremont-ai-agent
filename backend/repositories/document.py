from sqlalchemy.orm import Session

from backend.core.enums import DocumentReviewStatus, DocumentStatus, LegalStatus
from backend.models.document import Document
from backend.schemas.document import (
    DocumentClassificationUpdate,
    DocumentCreate,
)
from backend.services.document_classification_service import (
    DocumentClassification,
)
from backend.utils.time import utcnow


def create_document(
    db: Session,
    doc_schema: DocumentCreate,
    uploaded_by: int | None = None,
) -> Document:
    document = Document(
        title=doc_schema.title,
        file_path=doc_schema.file_path,
        project_id=doc_schema.project_id,
        visibility=doc_schema.visibility,
        category=doc_schema.category,
        subcategory=doc_schema.subcategory,
        subdivision_names=doc_schema.subdivision_names,
        building_codes=doc_schema.building_codes,
        unit_types=doc_schema.unit_types,
        applicable_area=doc_schema.applicable_area,
        version_label=doc_schema.version_label,
        issued_date=doc_schema.issued_date,
        effective_date=doc_schema.effective_date,
        expiry_date=doc_schema.expiry_date,
        applicable_period=doc_schema.applicable_period,
        legal_document_type=doc_schema.legal_document_type,
        legal_document_number=doc_schema.legal_document_number,
        legal_issuer=doc_schema.legal_issuer,
        legal_domain=doc_schema.legal_domain,
        legal_status=doc_schema.legal_status,
        uploaded_by=uploaded_by,
        status=DocumentStatus.PENDING,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def list_documents(db: Session) -> list[Document]:
    return db.query(Document).order_by(Document.created_at.desc()).all()


def get_document(
    db: Session,
    doc_id: int,
    *,
    for_update: bool = False,
) -> Document | None:
    query = db.query(Document).filter(Document.id == doc_id)
    if for_update:
        # A locking read under MySQL is current, but SQLAlchemy can otherwise hand
        # back an older instance already present in the identity map. Refresh it so
        # decisions made after waiting for the row lock use the committed state.
        query = query.populate_existing().with_for_update()
    return query.first()


def list_completed_siblings(db: Session, project_id: str | None, exclude_id: int) -> list[Document]:
    """Other successfully ingested documents that the new upload may contradict.

    With a project, "sibling" means the same project. Without one it means the other
    documents that also carry no project — a company-wide policy is only comparable to
    another company-wide policy, never to one scoped to a single project.

    Returning `[]` for a project-less document (the previous behaviour) meant those files
    silently left the conflict checks altogether, and the upload form makes the project
    optional. Two identically named price lists uploaded with no project raised nothing at
    all. The caller compensates for the missing project anchor by demanding explicit
    overlapping scope instead — see `_shares_explicit_scope` in ingestion_service.
    """
    scope = Document.project_id == project_id if project_id else Document.project_id.is_(None)

    return (
        db.query(Document)
        .filter(
            scope,
            Document.id != exclude_id,
            Document.status == DocumentStatus.COMPLETED,
        )
        .order_by(Document.created_at.desc())
        .all()
    )


def delete_document(db: Session, doc_id: int) -> None:
    document = get_document(db, doc_id)
    if document is None:
        raise ValueError(f"Document with id={doc_id} not found.")
    db.delete(document)
    db.commit()


def update_document_status(db: Session, doc_id: int, status: str) -> Document:
    document = get_document(db, doc_id)
    if document is None:
        raise ValueError(f"Document with id={doc_id} not found.")
    document.status = status
    db.commit()
    db.refresh(document)
    return document


def update_document_visibility(
    db: Session,
    doc_id: int,
    visibility: str,
    *,
    commit: bool = True,
) -> Document:
    document = get_document(db, doc_id, for_update=not commit)
    if document is None:
        raise ValueError(f"Document with id={doc_id} not found.")
    document.visibility = visibility
    if commit:
        db.commit()
        db.refresh(document)
    else:
        db.flush()
    return document


def update_document_storage_path(
    db: Session,
    doc_id: int,
    file_path: str,
) -> Document:
    document = get_document(db, doc_id)
    if document is None:
        raise ValueError(f"Document with id={doc_id} not found.")

    document.file_path = file_path
    db.commit()
    db.refresh(document)
    return document


def list_documents_pending_review(db: Session) -> list[Document]:
    """Documents uploaded but still awaiting an Admin decision on their metadata."""

    return (
        db.query(Document)
        .filter(
            Document.review_status == DocumentReviewStatus.PENDING,
            Document.status == DocumentStatus.COMPLETED,
        )
        .order_by(Document.created_at.desc())
        .all()
    )


def update_document_classification(
    db: Session,
    document_id: int,
    payload: DocumentClassificationUpdate,
    reviewed_by: int,
    *,
    commit: bool = True,
) -> Document:
    """Record the Admin's confirmed or corrected classification metadata."""

    document = get_document(db, document_id, for_update=True)
    if document is None:
        raise ValueError(f"Document with id={document_id} not found.")
    if document.review_status != DocumentReviewStatus.PENDING:
        raise ValueError(f"Document {document_id} classification has already been reviewed.")
    if document.status != DocumentStatus.COMPLETED:
        raise ValueError(f"Document {document_id} is not ready for classification review (status={document.status}).")

    updates = payload.model_dump(exclude_unset=True)
    if payload.category != document.category:
        raise ValueError("Changing document category requires quarantine, conflict rescan and controlled re-indexing.")

    scope_fields = ("subdivision_names", "building_codes", "unit_types")
    changed_scope_fields = [
        field_name
        for field_name in scope_fields
        if field_name in updates
        and _normalised_string_set(updates[field_name]) != _normalised_string_set(getattr(document, field_name))
    ]
    if changed_scope_fields:
        raise ValueError(
            "Changing conflict-scope metadata requires a controlled conflict rescan: "
            f"{', '.join(changed_scope_fields)}."
        )

    # PATCH semantics: omitted optional fields retain the classifier suggestion instead
    # of being silently overwritten with None/default values.
    for field_name, value in updates.items():
        setattr(document, field_name, value)

    if document.legal_status in {
        LegalStatus.NOT_YET_EFFECTIVE,
        LegalStatus.EXPIRED,
        LegalStatus.REPEALED,
        LegalStatus.REPLACED,
    }:
        document.is_current = False

    document.review_status = DocumentReviewStatus.APPROVED
    document.reviewed_by = reviewed_by
    document.reviewed_at = utcnow()

    if commit:
        db.commit()
        db.refresh(document)
    else:
        db.flush()
    return document


def _normalised_string_set(values: list[str] | None) -> frozenset[str]:
    return frozenset(" ".join(value.split()).casefold() for value in (values or []) if value.strip())


def update_document_classification_suggestion(
    db: Session,
    document_id: int,
    classification: DocumentClassification,
    *,
    auto_approve: bool = False,
) -> Document:
    """Store the rule/AI suggestion. This is not approval; an Admin still has to decide."""

    document = get_document(db, document_id)
    if document is None:
        raise ValueError(f"Document with id={document_id} not found.")

    document.category = classification.category
    document.subcategory = classification.subcategory
    document.subdivision_names = classification.subdivision_names
    document.building_codes = classification.building_codes
    document.unit_types = classification.unit_types
    document.applicable_area = classification.applicable_area

    document.document_summary = classification.document_summary
    document.version_label = classification.version_label
    document.issued_date = classification.issued_date
    document.effective_date = classification.effective_date
    document.expiry_date = classification.expiry_date
    document.applicable_period = classification.applicable_period

    document.legal_document_type = classification.legal_document_type
    document.legal_document_number = classification.legal_document_number
    document.legal_issuer = classification.legal_issuer
    document.legal_domain = classification.legal_domain
    document.legal_status = classification.legal_status

    document.classification_confidence = classification.confidence
    document.classification_reason = classification.reason
    document.classified_at = utcnow()

    if auto_approve:
        document.review_status = DocumentReviewStatus.APPROVED
        # This approval is made by the configured system rule, not an Admin.
        document.reviewed_by = None
        document.reviewed_at = utcnow()

    # Không đổi review_status: file vẫn phải chờ Admin duyệt.
    db.commit()
    db.refresh(document)
    return document
