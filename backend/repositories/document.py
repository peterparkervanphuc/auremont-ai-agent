from sqlalchemy.orm import Session

from backend.models.document import Document
from backend.schemas.document import DocumentCreate


def create_document(db: Session, doc_schema: DocumentCreate) -> Document:
    document = Document(
        title=doc_schema.title,
        file_path=doc_schema.file_path,
        status="pending",
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def update_document_status(db: Session, doc_id: int, status: str) -> Document:
    document = db.query(Document).filter(Document.id == doc_id).first()
    if document is None:
        raise ValueError(f"Document with id={doc_id} not found.")
    document.status = status
    db.commit()
    db.refresh(document)
    return document

