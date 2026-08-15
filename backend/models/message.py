from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text

from backend.core.mysql_client import Base
from backend.utils.time import utcnow


class Message(Base):
    """One turn in a Sale's consultation session — either a Sale question or an Agent answer."""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=True, index=True)

    sender = Column(String(20), nullable=False)  # MessageSender
    content = Column(Text, nullable=False)

    # Retrieval citations, e.g. [{"document_id": 12, "title": "...", "page": 3}]
    citations = Column(JSON, nullable=True)

    # Project gallery images shown as a swipeable strip under the answer, e.g.
    # [{"url": "http://.../hai-au/don-lap.jpg", "project_id": "hai-au", "project_name": "Hải Âu"}].
    # Stored per message rather than resolved on read so reopening an old conversation
    # shows what the Sale actually saw, even after the catalogue changes.
    images = Column(JSON, nullable=True)

    verifier_score = Column(Float, nullable=True)  # Overall Verifier score: min(faithfulness, relevancy)
    # The two component scores behind verifier_score, kept apart for the Admin dashboard:
    # low faithfulness means invented figures, low relevancy means retrieval fetched the wrong
    # documents. Nullable: messages written before this column existed, cache hits, and every
    # edge-case notice (empty state, inventory down) have no Verifier run behind them.
    faithfulness = Column(Float, nullable=True)
    answer_relevancy = Column(Float, nullable=True)
    requires_hitl = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=utcnow, nullable=False)
