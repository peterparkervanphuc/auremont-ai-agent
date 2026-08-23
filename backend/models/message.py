from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.mysql_client import Base
from backend.utils.time import utcnow


class Message(Base):
    """One turn in a Sale's consultation session — either a Sale question or an Agent answer."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("chat_sessions.id"), nullable=True, index=True)

    sender: Mapped[str] = mapped_column(String(20), nullable=False)  # MessageSender
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Retrieval citations, e.g. [{"document_id": 12, "title": "...", "page": 3}]
    citations: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)

    # Project gallery images shown as a swipeable strip under the answer, e.g.
    # [{"url": "http://.../hai-au/don-lap.jpg", "project_id": "hai-au", "project_name": "Hải Âu"}].
    # Stored per message rather than resolved on read so reopening an old conversation
    # shows what the Sale actually saw, even after the catalogue changes.
    images: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)

    # Drives AuremontAvatar.tsx's animation for an AGENT-authored message — one of
    # MessageEmotion (happy/regretful/respectful), computed deterministically from the
    # pipeline/gate outcome that produced this message (see agent_pipeline.py and
    # customer_chat.py), never a separate LLM call. NULL (a Sale/customer's own message,
    # or an older row from before this column existed) reads as a neutral idle pose.
    emotion: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Short reply options for the customer to tap instead of typing, e.g. ["Để ở", "Đầu
    # tư"] — only ever set on a PUBLIC-clearance AGENT message where the model itself
    # decided the question it just asked has a natural short-list of answers (see
    # SYSTEM_INSTRUCTION_PUBLIC/ConsultAnswer in backend/ai/prompts.py). NULL everywhere
    # else: a Sale/customer's own message, an INTERNAL answer, a canned gate/notice, or a
    # row from before this column existed.
    quick_replies: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # Recommended units rendered as their own cards rather than as bullet lines in
    # `content`, e.g. [{"project_name": "The Sapphire 2", "unit_type": "2PN",
    # "area_range": "55-64 m²", "price_range": "3,1-4,3 tỷ đồng", "image_url": "http://...",
    # "project_id": "the-sapphire-2"}]. Only ever set on a PUBLIC-clearance AGENT message
    # that recommends 1-2 specific units with a full set of figures (see
    # prompts.PropertyListing). NULL everywhere else, same reasoning as quick_replies above.
    listings: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    # Plausible NEXT questions about the topic just discussed, e.g. ["Giá căn 2PN bao
    # nhiêu?", "Tiện ích nội khu có gì?"] — offered to BOTH audiences (Sale and customer),
    # unlike `quick_replies` above. The distinction matters: quick_replies answer a
    # question the assistant just asked, these start the asker's next one. Generated in the
    # same schema-constrained call as the answer itself (ConsultAnswer/SaleAnswer in
    # backend/ai/prompts.py), so they cost no extra LLM round trip. NULL on a
    # Sale/customer's own message, a canned gate/notice, a cache hit, or a row from before
    # this column existed.
    suggested_questions: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    verifier_score: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # Overall Verifier score: min of the three below
    # The component scores behind verifier_score, kept apart for the Admin dashboard:
    # low faithfulness means invented figures, low relevancy means retrieval fetched the wrong
    # documents, low completeness means a multi-part question was only half answered.
    # Nullable: messages written before this column existed, cache hits, and every
    # edge-case notice (empty state, inventory down) have no Verifier run behind them.
    faithfulness: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_relevancy: Mapped[float | None] = mapped_column(Float, nullable=True)
    completeness: Mapped[float | None] = mapped_column(Float, nullable=True)
    # The Verifier's classification of the defect (verifier_service.FailureMode), so Admin
    # Tab 2 can group failures by cause — "the model invents figures" and "the corpus is
    # missing this document" need completely different fixes, and an undifferentiated list
    # of low scores cannot tell them apart. NULL wherever no Verifier ran.
    failure_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    requires_hitl: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
