from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.enums import LeadTier
from backend.core.mysql_client import Base
from backend.utils.time import utcnow


class Lead(Base):
    """A prospective buyer and how ready they are to buy — one row per PERSON.

    Deliberately not a column on `chat_sessions`: `ChatSession.channel` splits one
    customer's AI conversation and their live-Sale thread into two separate rows, and
    `sale_live` resolves LIVE rows only. A tier written on the AI row would be invisible on
    exactly the row the Sale is looking at, and dual-writing both rows to describe one
    person is the bug, not the fix.

    Identity mirrors `ChatSession`'s own ownership invariant, enforced at the application
    layer for the same reason (no portable CHECK across the MySQL/SQLite versions targeted):
      - Anonymous visitor: `visitor_token` set, `customer_id` NULL.
      - Registered customer: `customer_id` set, `visitor_token` NULL.
    Both columns are UNIQUE and nullable — MySQL and SQLite both permit many NULLs under
    UNIQUE, the same trick `chat_sessions.visitor_token` already relies on — so one person
    has exactly one row in either state. Registration transfers the row rather than creating
    a second (see `repositories.lead.claim_anonymous_lead`), so a visitor's accumulated
    score survives them signing up.

    No contact columns here. Contact details are only ever captured at registration, so they
    always have a `users` row to live on; copying them here would create a drift surface
    with no anonymous case to justify it.
    """

    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, unique=True, index=True
    )
    visitor_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    # Last project the person showed interest in — powers the Admin per-project breakdown.
    project_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("projects.id"), nullable=True, index=True)

    # Indexed: the live inbox sorts on this every 5 seconds, for every logged-in Sale.
    tier: Mapped[str] = mapped_column(
        String(10), default=LeadTier.COLD, server_default=LeadTier.COLD.value, nullable=False, index=True
    )
    score: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    # Kept apart from `score` so the LLM's contribution stays auditable after the fact —
    # without it, a retuned weight table and a drifting model look identical in the data.
    rule_score: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    # NULL means the LLM pass has never run for this lead, which is different from it having
    # run and found nothing (0).
    soft_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    urgency: Mapped[str | None] = mapped_column(String(12), nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Latched signal flags plus the evidence behind them and a one-sentence Vietnamese
    # reason. JSON rather than a wide mostly-NULL table, same reasoning as
    # `conflict_flags.evidence` and `audit_logs.payload`: the signal set will change as the
    # weights are tuned against real traffic, and a verdict with no evidence is unauditable.
    signals: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Scoring provenance, same shape as `conflict_flags`: "rule" or "rule+llm".
    detection_method: Mapped[str] = mapped_column(
        String(20), default="rule", server_default="rule", nullable=False
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Bumped whenever the weight table changes, so rows scored under old weights stay
    # identifiable instead of silently polluting the Admin averages.
    analysis_version: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Customer turns seen so far — both a signal and the anchor for the LLM debounce.
    turn_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    llm_scored_turn: Mapped[int | None] = mapped_column(Integer, nullable=True)

    scored_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    llm_scored_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
