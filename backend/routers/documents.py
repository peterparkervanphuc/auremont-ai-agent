from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.deps import require_role
from backend.core.enums import DocumentVisibility, UserRole
from backend.core.mysql_client import get_db
from backend.repositories.document import (
    create_document,
    delete_document,
    list_documents,
    update_document_visibility,
)
from backend.schemas.document import DocumentCreate, DocumentResponse
from backend.services.ingestion_service import PromptInjectionError, sanitize_and_scan

router = APIRouter(prefix="/documents", tags=["Documents (Admin)"], dependencies=[Depends(require_role(UserRole.ADMIN))])


class IngestRequest(BaseModel):
    title: str
    raw_text: str
    file_path: str | None = None
    project_id: str | None = None


class IngestResponse(BaseModel):
    document_id: int
    status: str
    message: str


class VisibilityUpdateRequest(BaseModel):
    visibility: DocumentVisibility


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_document(payload: IngestRequest, db: Session = Depends(get_db)) -> IngestResponse:
    """Upload + scan (CLAUDE.md §6.5 Tab 1). New documents default to INTERNAL until an Admin relabels them."""
    try:
        sanitize_and_scan(payload.raw_text)
    except PromptInjectionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Chặn file: phát hiện rủi ro") from exc
    except NotImplementedError:
        pass  # TODO: remove once sanitize_and_scan is implemented; ingest proceeds unscanned for now

    doc_schema = DocumentCreate(title=payload.title, file_path=payload.file_path, project_id=payload.project_id)
    document = create_document(db, doc_schema)

    # TODO: kick off ingestion_service.ingest_document (chunk/embed/upsert to Qdrant) as a background task.

    return IngestResponse(
        document_id=document.id,
        status=document.status,
        message=f"Document '{document.title}' created successfully.",
    )


@router.get("", response_model=list[DocumentResponse])
async def get_documents(db: Session = Depends(get_db)) -> list[DocumentResponse]:
    return list_documents(db)


@router.patch("/{document_id}/visibility", response_model=DocumentResponse)
async def set_document_visibility(
    document_id: int, payload: VisibilityUpdateRequest, db: Session = Depends(get_db)
) -> DocumentResponse:
    """Gán nhãn RBAC — bắt buộc trước khi tài liệu có thể phục vụ Chatbot công khai (CLAUDE.md §6.5 Tab 1)."""
    try:
        return update_document_visibility(db, document_id, payload.visibility)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_document(document_id: int, db: Session = Depends(get_db)) -> None:
    try:
        delete_document(db, document_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
