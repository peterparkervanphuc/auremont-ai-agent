from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.enums import SessionChannel, SessionStatus
from backend.core.mysql_client import Base
from backend.utils.time import utcnow


class ChatSession(Base):
    """A consultation session — a Sale's session with a customer, OR a public customer-chat
    session (anonymous or a logged-in CUSTOMER account).

    `sale_id` / `customer_id` / `visitor_token` describe ownership, enforced at the
    application layer rather than a DB constraint (not reliably expressible as a portable
    CHECK across the MySQL/SQLite versions this app targets):
      - Sale/Admin session (Sale consulting on their own): `sale_id` set, the other two NULL.
      - Anonymous customer session: `visitor_token` set, the other two NULL.
      - Registered customer session, not yet claimed by a Sale: `customer_id` set (once
        claimed from anonymous, or created directly while logged in), the other two NULL.
      - Registered customer session claimed by a Sale (live handoff, `status=SALE_HANDLING`):
        BOTH `customer_id` and `sale_id` set, `visitor_token` NULL, and `channel=LIVE` — a
        distinct row from that customer's `channel=AI` conversation, which the Sale never sees. Code paths that list a
        Sale's own AI-consult sessions (`list_sessions_for_sale`) or resolve their ownership
        (`sale_chat._owned_session`) must exclude rows with `customer_id` set, or a claimed
        customer session leaks into the Sale's unrelated self-consult session list/access.

    `status` (see `SessionStatus`) only has meaning for a customer session (anonymous or
    CUSTOMER-owned): whether the AI is still answering (BOT_HANDLING), the customer is
    waiting for a Sale to pick it up (WAITING_SALE), or a Sale has taken over and the AI must
    stay silent (SALE_HANDLING). Sale-authored sessions leave it at the default, unused.
    """

    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # Nullable: a customer-chat session (anonymous or CUSTOMER-owned) has no Sale owner
    # until claimed. Every Sale-side query filters `WHERE sale_id = :user.id AND
    # customer_id IS NULL`, so this stays safe for `_owned_session()`/`list_sessions_for_sale()`.
    sale_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    status: Mapped[str] = mapped_column(String(20), default=SessionStatus.BOT_HANDLING, nullable=False)

    # Which conversation this row holds for a customer: the AI thread or the live-Sale
    # thread. They are separate rows so a Sale physically cannot read the AI history — the
    # live-inbox and `sale_live` endpoints only ever resolve a LIVE row. Sale-authored
    # self-consult sessions keep the AI default, which nothing reads it for.
    channel: Mapped[str] = mapped_column(String(10), default=SessionChannel.AI, nullable=False, index=True)

    # Stamped the moment `status` becomes WAITING_SALE (see repositories/chat_session.py::
    # enter_waiting_queue), cleared on claim/return-to-bot. Deliberately NOT the same as
    # `created_at` below: a session can be created long before it ever needs a human (a
    # customer chatting with the AI for a while first), so `created_at` alone would make the
    # live-inbox queue show a wildly inflated "waiting since" time.
    handoff_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Set once a logged-in CUSTOMER account owns this session (either created it directly,
    # or claimed it from an anonymous visitor_token session on registration).
    customer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Server-generated opaque token identifying an anonymous visitor's session before they
    # register/log in — never client-generated. Cleared once the session is claimed by a
    # customer_id (see repositories/chat_session.py::claim_session).
    visitor_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)

    # Free text entered by the Sale, e.g. "Session: Khách Nguyễn Văn A".
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # The customer this session belongs to — each session keeps its own Memory per customer.
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # The project this consultation session belongs to: it narrows retrieval to that
    # project's documents and picks which project's stock the inventory API is asked for.
    # Nullable, and genuinely optional — the session-creation form no longer asks the Sale
    # to choose a project, so most rows carry NULL. Inventory still works in that case:
    # `inventory_service.resolve_api_project_id` falls back to the INVENTORY_PROJECT_MAP
    # catch-all rather than refusing the lookup.
    project_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("projects.id"), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
