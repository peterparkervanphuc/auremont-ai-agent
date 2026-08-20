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

    # Drives AuremontAvatar.tsx's animation for an AGENT-authored message — one of
    # MessageEmotion (happy/regretful/respectful), computed deterministically from the
    # pipeline/gate outcome that produced this message (see agent_pipeline.py and
    # customer_chat.py), never a separate LLM call. NULL (a Sale/customer's own message,
    # or an older row from before this column existed) reads as a neutral idle pose.
    emotion = Column(String(20), nullable=True)

    # Short reply options for the customer to tap instead of typing, e.g. ["Để ở", "Đầu
    # tư"] — only ever set on a PUBLIC-clearance AGENT message where the model itself
    # decided the question it just asked has a natural short-list of answers (see
    # SYSTEM_INSTRUCTION_PUBLIC/ConsultAnswer in backend/ai/prompts.py). NULL everywhere
    # else: a Sale/customer's own message, an INTERNAL answer, a canned gate/notice, or a
    # row from before this column existed.
    quick_replies = Column(JSON, nullable=True)

    verifier_score = Column(Float, nullable=True)  # Overall Verifier score: min of the three below
    # The component scores behind verifier_score, kept apart for the Admin dashboard:
    # low faithfulness means invented figures, low relevancy means retrieval fetched the wrong
    # documents, low completeness means a multi-part question was only half answered.
    # Nullable: messages written before this column existed, cache hits, and every
    # edge-case notice (empty state, inventory down) have no Verifier run behind them.
    faithfulness = Column(Float, nullable=True)
    answer_relevancy = Column(Float, nullable=True)
    completeness = Column(Float, nullable=True)
    # The Verifier's classification of the defect (verifier_service.FailureMode), so Admin
    # Tab 2 can group failures by cause — "the model invents figures" and "the corpus is
    # missing this document" need completely different fixes, and an undifferentiated list
    # of low scores cannot tell them apart. NULL wherever no Verifier ran.
    failure_mode = Column(String(32), nullable=True)
    requires_hitl = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=utcnow, nullable=False)
