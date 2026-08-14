from sqlalchemy.orm import Session

from backend.core.enums import DocumentReviewStatus, DocumentStatus
from backend.models.document import Document
from backend.schemas.document import (
    DocumentClassificationUpdate,
    DocumentCreate,
)
from backend.utils.time import utcnow

from backend.services.document_classification_service import (
    DocumentClassification,
)

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


def get_document(db: Session, doc_id: int) -> Document | None:
    return db.query(Document).filter(Document.id == doc_id).first()


def list_completed_siblings(db: Session, project_id: str | None, exclude_id: int) -> list[Document]:
    """Other successfully ingested documents of the same project.

    Used by conflict detection to find an older document the new upload may
    contradict. Documents with no project are skipped entirely: without a project
    there is no meaningful "same project" to compare against, and flagging every
    unassigned document against every other would bury Admins in noise.
    """
    if not project_id:
        return []

    return (
        db.query(Document)
        .filter(
            Document.project_id == project_id,
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


def update_document_visibility(db: Session, doc_id: int, visibility: str) -> Document:
    document = get_document(db, doc_id)
    if document is None:
        raise ValueError(f"Document with id={doc_id} not found.")
    document.visibility = visibility
    db.commit()
    db.refresh(document)
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
    """Lấy tài liệu đã upload nhưng Admin chưa xác nhận metadata."""

    return (
        db.query(Document)
        .filter(Document.review_status == DocumentReviewStatus.PENDING)
        .order_by(Document.created_at.desc())
        .all()
    )


def update_document_classification(
    db: Session,
    document_id: int,
    payload: DocumentClassificationUpdate,
    reviewed_by: int,
) -> Document:
    """Admin xác nhận/sửa metadata phân loại của tài liệu."""

    document = get_document(db, document_id)
    if document is None:
        raise ValueError(f"Document with id={document_id} not found.")

    # model_dump chỉ trả field có trong schema update, không ảnh hưởng các field
    # kỹ thuật như title, status, file_path hay uploaded_by.
    for field_name, value in payload.model_dump().items():
        setattr(document, field_name, value)

    document.review_status = DocumentReviewStatus.APPROVED
    document.reviewed_by = reviewed_by
    document.reviewed_at = utcnow()

    db.commit()
    db.refresh(document)
    return document

def update_document_classification_suggestion(
    db: Session,
    document_id: int,
    classification: DocumentClassification,
    *,
    auto_approve: bool = False,
) -> Document:
    """Lưu metadata rule/AI đề xuất; chưa phải phê duyệt của Admin."""

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
