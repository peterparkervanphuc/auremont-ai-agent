from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.enums import ConflictStatus
from backend.core.mysql_client import Base
from backend.utils.time import utcnow


class ConflictFlag(Base):
    """Flags contradictory content between two documents, e.g. two price-list versions"""

    __tablename__ = "conflict_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_id_a: Mapped[int] = mapped_column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    document_id_b: Mapped[int] = mapped_column(Integer, ForeignKey("documents.id"), nullable=False, index=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=ConflictStatus.OPEN, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    # Who closed the flag, and when.
    resolved_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
