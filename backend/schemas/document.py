from datetime import datetime

from pydantic import BaseModel


class DocumentCreate(BaseModel):
    title: str
    file_path: str | None = None


class DocumentResponse(BaseModel):
    id: int
    title: str
    file_path: str | None = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
