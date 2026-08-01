from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from backend.core.enums import LiveChatStatus
from backend.core.mysql_client import Base


class LiveChatRequest(Base):
    """A Customer's request to connect directly with an online Sale (CLAUDE.md §6.3.c)."""

    __tablename__ = "livechat_requests"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    sale_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=True, index=True)

    status = Column(String(20), default=LiveChatStatus.WAITING, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
