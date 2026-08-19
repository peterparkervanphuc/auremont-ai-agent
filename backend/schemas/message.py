from datetime import datetime

from pydantic import BaseModel

from backend.core.enums import MessageEmotion, MessageSender


class Citation(BaseModel):
    document_id: int
    title: str
    page: int | None = None


class AnswerImage(BaseModel):
    """One project photo shown in the swipeable strip under an answer."""

    url: str
    project_id: str
    project_name: str


class MessageCreate(BaseModel):
    session_id: int | None = None
    content: str


class MessageResponse(BaseModel):
    id: int
    session_id: int | None = None
    sender: MessageSender
    content: str
    citations: list[Citation] | None = None
    images: list[AnswerImage] | None = None
    verifier_score: float | None = None
    requires_hitl: bool
    # Whether a confirmation exists for this answer. Derived server-side from hitl_logs,
    # never sent by the client: a client-supplied flag could present an unread commitment
    # as approved.
    hitl_confirmed: bool = False
    # Drives AuremontAvatar.tsx — see MessageEmotion. `None` on a Sale/Customer's own
    # message, or an AGENT message from before this field existed.
    emotion: MessageEmotion | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
