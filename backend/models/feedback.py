from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from backend.core.mysql_client import Base
from backend.utils.time import utcnow


class Feedback(Base):
    """Sale's report on a wrong/incomplete agent answer.

    Feeds the "Top câu hỏi AI trả lời thất bại" panel in Admin Tab 2 (§5.3).
    """

    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False, index=True)

    # Who filed it — lets Admin trace a report back to the Sale who hit the problem.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    type = Column(String(20), nullable=False, index=True)  # FeedbackType
    comment = Column(Text, nullable=True)

    created_at = Column(DateTime, default=utcnow, nullable=False)
