from datetime import datetime

from pydantic import BaseModel

from backend.core.enums import SessionSource


class ChatSessionCreate(BaseModel):
    customer_id: str | None = None
    source: SessionSource = SessionSource.SALE_INITIATED
    title: str | None = None


class ChatSessionResponse(BaseModel):
    id: int
    sale_id: int
    customer_id: str | None = None
    source: str
    title: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
