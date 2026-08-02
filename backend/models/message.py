from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text

from backend.core.mysql_client import Base


class Message(Base):
    """Một lượt trao đổi trong phiên tư vấn của Sale — câu hỏi của Sale hoặc câu trả lời của Agent."""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=True, index=True)

    sender = Column(String(20), nullable=False)  # MessageSender
    content = Column(Text, nullable=False)

    # Retrieval citations, e.g. [{"document_id": 12, "title": "...", "page": 3}]
    citations = Column(JSON, nullable=True)

    verifier_score = Column(Float, nullable=True)  # Faithfulness/Relevancy score from the Verifier Agent
    requires_hitl = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
