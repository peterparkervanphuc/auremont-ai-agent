from datetime import datetime

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
