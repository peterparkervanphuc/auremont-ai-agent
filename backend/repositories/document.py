from sqlalchemy.orm import Session

from backend.core.enums import DocumentStatus
from backend.models.document import Document
from backend.schemas.document import DocumentCreate


def create_document(db: Session, doc_schema: DocumentCreate,uploaded_by: int | None = None,) -> Document:
    document = Document(
        title=doc_schema.title,
        file_path=doc_schema.file_path,
        project_id=doc_schema.project_id,
        visibility=doc_schema.visibility,
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
