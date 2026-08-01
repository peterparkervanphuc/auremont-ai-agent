from datetime import datetime

from pydantic import BaseModel

from backend.core.enums import DocumentVisibility


class DocumentCreate(BaseModel):
    title: str
    file_path: str | None = None
    project_id: str | None = None
    # Defaults to INTERNAL — Admin must explicitly relabel to PUBLIC (CLAUDE.md §6.5).
    visibility: DocumentVisibility = DocumentVisibility.INTERNAL


class DocumentResponse(BaseModel):
    id: int
    title: str
    file_path: str | None = None
    project_id: str | None = None
    status: str
    visibility: str
    created_at: datetime

    model_config = {"from_attributes": True}
