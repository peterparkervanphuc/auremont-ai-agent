from datetime import datetime

from pydantic import BaseModel

from backend.core.enums import LiveChatStatus


class LiveChatRequestCreate(BaseModel):
    customer_id: str


class LiveChatRequestResponse(BaseModel):
    id: int
    customer_id: str
    sale_id: int | None = None
    session_id: int | None = None
    status: LiveChatStatus
    created_at: datetime
    accepted_at: datetime | None = None
    ended_at: datetime | None = None

    model_config = {"from_attributes": True}
