
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.mysql_client import get_db
from backend.repositories.document import create_document
from backend.schemas.document import DocumentCreate

router = APIRouter(prefix="/documents", tags=["Documents"])


class IngestRequest(BaseModel):
    title: str
    raw_text: str
    file_path: str | None = None


class IngestResponse(BaseModel):
    document_id: int
    status: str
    message: str


@router.post("/ingest", response_model=IngestResponse, status_code=201)
async def ingest_document(
    payload: IngestRequest,
    db: Session = Depends(get_db),
) -> IngestResponse:
    # TODO: Implement document processing pipeline
    doc_schema = DocumentCreate(title=payload.title, file_path=payload.file_path)
    document = create_document(db, doc_schema)

    return IngestResponse(
        document_id=document.id,
        status="created",
        message=f"Document '{document.title}' created successfully.",
    )

