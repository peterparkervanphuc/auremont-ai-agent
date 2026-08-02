from sqlalchemy.orm import Session

from backend.core.enums import DocumentStatus
from backend.models.document import Document
from backend.schemas.document import DocumentCreate


def create_document(db: Session, doc_schema: DocumentCreate) -> Document:
    document = Document(
        title=doc_schema.title,
        file_path=doc_schema.file_path,
        project_id=doc_schema.project_id,
        visibility=doc_schema.visibility,
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

