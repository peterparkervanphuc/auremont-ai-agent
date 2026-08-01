from datetime import datetime

from pydantic import BaseModel

from backend.core.enums import HitlStatus


class HitlConfirmRequest(BaseModel):
    """Payload for the mandatory 'XÁC NHẬN & GỬI' action (CLAUDE.md §6.4.e)."""

    confirmed_content: str


class HitlLogResponse(BaseModel):
    id: int
    message_id: int
    sale_id: int
    status: HitlStatus
    confirmed_content: str | None = None
    confirmed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
