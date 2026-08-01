from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from backend.core.mysql_client import Base


class ChatSession(Base):
    """A Sale consultation session (CLAUDE.md §5.2.b) — holds its own Memory per customer."""

    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    title = Column(String(255), nullable=True)  # e.g. "Session: Khách Nguyễn Văn A" — free text, Sale-entered

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
