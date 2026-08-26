from datetime import datetime

from pydantic import BaseModel

from backend.core.enums import LeadPurpose, LeadTier, LeadUrgency


class LiveInboxEntry(BaseModel):
    """One row in the Sale-facing "Khách đang chờ" queue (routers/sale_live.py)."""

    session_id: int
    customer_label: str
    last_message_preview: str
    # When this session entered WAITING_SALE — NOT when the session itself was created
    # (a customer may have been chatting with the AI for a while first). `None` once it's
    # already claimed (SALE_HANDLING), since it's no longer "waiting" for anything.
    waiting_since: datetime | None

    # Not nullable: a lead with no buying signal yet genuinely IS cold, and a nullable tier
    # would make the frontend render an empty badge for the most common row on the page.
    lead_tier: LeadTier = LeadTier.COLD
    lead_score: int = 0
    # Why the tier says what it says. A badge with no reason is a verdict a Sale cannot
    # check, which is the same objection `conflict_flags.evidence` exists to answer.
    lead_reason: str | None = None
    customer_name: str | None = None
    customer_phone: str | None = None


class LeadSignalDetail(BaseModel):
    """One fired scoring signal, for the full breakdown panel on the chat screen itself.

    `LiveInboxEntry.lead_reason` (a single joined string) is enough for a queue row; the
    chat screen has room for the actual evidence — this is that evidence, one row per
    signal that fired, so a Sale can check the tier rather than just trust it.
    """

    label: str
    points: int


class LeadDetailResponse(BaseModel):
    """Full lead breakdown for the Sale actually talking to this customer right now.

    `null` when nobody has scored this session yet (e.g. the very first message of a fresh
    live handoff) — the frontend renders an explicit "chưa có dữ liệu" state rather than a
    misleading COLD badge with zero evidence behind it.
    """

    customer_label: str
    customer_name: str | None = None
    customer_phone: str | None = None

    lead_tier: LeadTier
    lead_score: int
    rule_score: int
    # None means the LLM pass has never run for this lead — different from having run and
    # found nothing (0), which is why this is not folded into `lead_score` alone.
    soft_score: int | None = None
    urgency: LeadUrgency | None = None
    purpose: LeadPurpose | None = None
    confidence: float | None = None
    detection_method: str

    turn_count: int
    scored_at: datetime | None = None

    signals: list[LeadSignalDetail] = []
    # The LLM's own one-sentence explanation, carried forward from the last turn it actually
    # ran on — see repositories.lead.update_lead_score. None until the LLM pass has fired
    # at least once (see should_enrich's decision-band gate).
    llm_reason: str | None = None

    # One concrete thing to do next, from lead_scoring_service.suggest_next_action. Advice
    # for the Sale, never an automated action.
    next_action: str = ""
    # What the customer has told the AI about what they want, read from the same Redis
    # profile the answer pipeline uses (memory_service). Lets the Sale open with context
    # instead of re-asking questions the customer already answered.
    budgets: list[str] = []
    unit_types: list[str] = []
    projects: list[str] = []


class SaleLiveMessageRequest(BaseModel):
    content: str


class SaleSuggestResponse(BaseModel):
    """A draft answer for the Sale to review/edit — never persisted as a message until the
    Sale actually sends it via POST /sale/live-inbox/{id}/reply."""

    draft: str
    # True when the draft carries price/commitment risk. This reply path goes straight to a
    # live customer with no HITL card in between, so the Sale UI uses this to demand an
    # explicit acknowledgement before an AI-drafted commitment can be sent.
    requires_hitl: bool = False
