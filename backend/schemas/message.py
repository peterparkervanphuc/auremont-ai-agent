from datetime import datetime

from pydantic import BaseModel

from backend.core.enums import MessageSender


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
    created_at: datetime

    model_config = {"from_attributes": True}
