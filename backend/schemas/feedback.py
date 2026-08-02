from datetime import datetime

from pydantic import BaseModel

from backend.core.enums import FeedbackType


class FeedbackCreate(BaseModel):
    """Sale báo cáo câu trả lời sai/thiếu."""

    message_id: int
    type: FeedbackType
    comment: str | None = None


class FeedbackResponse(BaseModel):
    id: int
    message_id: int
    user_id: int | None = None
    type: FeedbackType
    comment: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class FailedQuestion(BaseModel):
    """Một dòng trong bảng "Top câu hỏi AI trả lời thất bại" của Admin Tab 2."""

    message_id: int
    question: str
    feedback_count: int
