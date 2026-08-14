from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.deps import require_role
from backend.core.enums import DocumentStatus, DocumentVisibility, UserRole
from backend.core.mysql_client import get_db
from backend.models.user import User
from backend.repositories.document import (
    create_document,
    delete_document,
    list_documents,
    list_documents_pending_review,
    update_document_classification,
    update_document_visibility,
)
from backend.schemas.document import (
    DocumentClassificationUpdate,
    DocumentCreate,
    DocumentResponse,
)
from backend.services.ingestion_service import (
    DocumentIngestionError,
    PromptInjectionError,
    ingest_uploaded_document,
    sanitize_and_scan,
)
from backend.services.vector_store_service import (
    VectorStoreError,
    update_document_vector_metadata,
)

router = APIRouter(
    prefix="/documents",
    tags=["Documents (Admin)"],
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)

ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".docx"}


class IngestRequest(BaseModel):
    """Legacy raw-text endpoint; kept so the older flow does not break."""

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


@router.post(
    "/upload",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: UploadFile = File(...),
    project_id: str | None = Form(default=None),
    visibility: DocumentVisibility = Form(
        default=DocumentVisibility.INTERNAL,
    ),
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> IngestResponse:
    """Upload PDF/DOCX: parse → scan → MinIO → chunk → Gemini → Qdrant."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File name is required.",
        )

    suffix = Path(file.filename).suffix.lower()

    if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF and DOCX files are supported.",
        )

    file_bytes = await file.read()

    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    if len(file_bytes) > settings.upload_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File exceeds the maximum allowed size of "
                f"{settings.upload_max_bytes} bytes."
            ),
        )

    document = create_document(
        db,
        DocumentCreate(
            title=file.filename,
            project_id=project_id,
            visibility=visibility,
        ),
        uploaded_by=admin.id,
    )

    try:
        document = ingest_uploaded_document(
            db,
            document=document,
            filename=file.filename,
            file_bytes=file_bytes,
            content_type=file.content_type,
        )
    except PromptInjectionError:
        # ingestion_service has already moved the document to BLOCKED.
        return IngestResponse(
            document_id=document.id,
            status=DocumentStatus.BLOCKED,
            message="Document blocked due to suspicious content.",
        )
    except DocumentIngestionError as exc:
        # ingestion_service has already moved the document to FAILED.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document ingestion failed. Check server logs.",
        ) from exc
    finally:
        await file.close()

    return IngestResponse(
        document_id=document.id,
        status=document.status,
        message="Document uploaded and indexed successfully.",
    )


@router.post(
    "/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_document(
    payload: IngestRequest,
    db: Session = Depends(get_db),
) -> IngestResponse:
    """Legacy raw-text ingest endpoint."""
    try:
        sanitize_and_scan(payload.raw_text)
    except PromptInjectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Chặn file: phát hiện rủi ro",
        ) from exc

    document = create_document(
        db,
        DocumentCreate(
            title=payload.title,
            file_path=payload.file_path,
            project_id=payload.project_id,
        ),
    )

    return IngestResponse(
        document_id=document.id,
        status=document.status,
        message=f"Document '{document.title}' created successfully.",
    )


@router.get("", response_model=list[DocumentResponse])
async def get_documents(
    db: Session = Depends(get_db),
) -> list[DocumentResponse]:
    return list_documents(db)


@router.patch(
    "/{document_id}/visibility",
    response_model=DocumentResponse,
)
async def set_document_visibility(
    document_id: int,
    payload: VisibilityUpdateRequest,
    db: Session = Depends(get_db),
) -> DocumentResponse:
    try:
        return update_document_visibility(
            db,
            document_id,
            payload.visibility,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_document(
    document_id: int,
    db: Session = Depends(get_db),
) -> None:
    try:
        delete_document(db, document_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

@router.get(
    "/pending-review",
    response_model=list[DocumentResponse],
)
async def get_pending_review_documents(
    db: Session = Depends(get_db),
) -> list[DocumentResponse]:
    """Danh sách file chờ Admin xác nhận phân loại."""

    return list_documents_pending_review(db)


@router.patch(
    "/{document_id}/classification",
    response_model=DocumentResponse,
)
async def approve_document_classification(
    document_id: int,
    payload: DocumentClassificationUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> DocumentResponse:
    """Admin sửa metadata và duyệt file để bước sau cho phép RAG sử dụng."""

    try:
        document = update_document_classification(
            db,
            document_id=document_id,
            payload=payload,
            reviewed_by=admin.id,
        )
        update_document_vector_metadata(
            document.id,
            review_status=document.review_status,
            legal_status=document.legal_status,
            category=document.category,
        )
        return document
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except VectorStoreError as exc:
        # The DB approval is committed first; leaving Qdrant pending is safe
        # because RAG will keep excluding it until the sync is retried.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document was approved but vector metadata could not be synced.",
        ) from exc
