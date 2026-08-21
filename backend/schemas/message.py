from datetime import datetime

from pydantic import BaseModel

from backend.core.enums import MessageEmotion, MessageSender


class Citation(BaseModel):
    document_id: int
    title: str
    # Set only when another citation in the same list carries an identical title, to tell
    # the two apart ("tr.5", "#37"). Kept out of `title` deliberately: CitationList.tsx
    # decides between the inline PDF preview and a new tab by testing that the title still
    # ends in ".pdf", so appending anything to it silently breaks the preview and the
    # page/Y anchoring. Absent on citations stored before this field existed.
    qualifier: str | None = None
    page: int | None = None
    # PDF points from the page's top — lets the citation preview scroll straight to this
    # spot instead of just the top of the page. None for DOCX, or a chunk indexed before
    # this field existed. See chunking_service.py / CitationList.tsx's withPageAnchor.
    y_position: float | None = None


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
    # Short reply options the customer can tap instead of typing — see Message.quick_replies.
    quick_replies: list[str] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
