from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.mysql_client import Base
from backend.utils.time import utcnow


class AuditLog(Base):
    """Durable business-event trail: who did what, when.

    stdout logs answer "what went wrong just now" and are gone once the container
    is replaced. This table answers "who logged in last Tuesday" and "which Sale
    confirmed that price" months later, which is what an audit trail is for.

    Diagnostic logs deliberately do **not** land here — only `salesmate.audit`
    events. Tracebacks and access lines are high volume, short-lived, and belong
    in the log collector, not in the operational database.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Indexed because every dashboard query filters on one of these.
    event: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)

    # No ForeignKey on user_id on purpose: an audit row must outlive the user it
    # refers to. A cascade delete that silently erased the trail of a removed
    # account would defeat the point of keeping one.
    username: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Ties a row back to its stdout lines (access log, tracebacks) for the same
    # request while those are still in the collector's retention window.
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Event-specific fields. JSON rather than a wide table of mostly-NULL columns:
    # each event type carries a different shape, and adding a field to one event
    # should not require a migration.
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
