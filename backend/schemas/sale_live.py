from datetime import datetime

from pydantic import BaseModel


class LiveInboxEntry(BaseModel):
    """One row in the Sale-facing "Khách đang chờ" queue (routers/sale_live.py)."""

    session_id: int
    customer_label: str
    last_message_preview: str
    # When this session entered WAITING_SALE — NOT when the session itself was created
    # (a customer may have been chatting with the AI for a while first). `None` once it's
    # already claimed (SALE_HANDLING), since it's no longer "waiting" for anything.
    waiting_since: datetime | None


class SaleLiveMessageRequest(BaseModel):
    content: str


class SaleSuggestResponse(BaseModel):
    """A draft answer for the Sale to review/edit — never persisted as a message until the
    Sale actually sends it via POST /sale/live-inbox/{id}/reply."""

    draft: str
