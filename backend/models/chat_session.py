from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from backend.core.enums import SessionSource
from backend.core.mysql_client import Base


class ChatSession(Base):
    """A Sale consultation session (CLAUDE.md §6.4.b/c) — holds its own Memory, keyed per customer."""

    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=True, index=True)

    source = Column(String(20), default=SessionSource.SALE_INITIATED, nullable=False)
    title = Column(String(255), nullable=True)  # e.g. "Session: Khách Nguyễn Văn A"

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
