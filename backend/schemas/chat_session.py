from datetime import datetime

from pydantic import BaseModel


class ChatSessionCreate(BaseModel):
    title: str | None = None


class ChatSessionResponse(BaseModel):
    id: int
    sale_id: int
    title: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
