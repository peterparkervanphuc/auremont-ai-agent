from datetime import date, datetime

from pydantic import BaseModel

from backend.core.enums import ConflictStatus


class ConflictResolveRequest(BaseModel):
    keep_document_id: int  # the document to keep; the other is superseded


class ConflictFlagResponse(BaseModel):
    id: int
    document_id_a: int
    document_id_b: int
    description: str | None = None
    status: ConflictStatus
    created_at: datetime
    resolved_by: int | None = None
    resolved_at: datetime | None = None

    model_config = {"from_attributes": True}


class ConflictDocumentSummary(BaseModel):
    id: int
    title: str
    project_id: str | None = None
    version_label: str | None = None
    issued_date: date | None = None
    effective_date: date | None = None
    uploaded_at: datetime | None = None
    category: str
    visibility: str
    summary: str | None = None
    classification_reason: str | None = None


class ConflictDetailResponse(ConflictFlagResponse):
    # Similarity was not persisted by the existing ingestion pipeline. Null is an
    # explicit "not measured" state; the Admin UI must never invent a percentage.
    similarity_score: float | None = None
    project_id: str | None = None
    project_name: str | None = None
    document_a: ConflictDocumentSummary
    document_b: ConflictDocumentSummary
