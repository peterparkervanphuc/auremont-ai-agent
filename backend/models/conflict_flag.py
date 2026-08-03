from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from backend.core.enums import ConflictStatus
from backend.core.mysql_client import Base
from backend.utils.time import utcnow


class ConflictFlag(Base):
    """Flags contradictory content between two documents, e.g. two price-list versions """

    __tablename__ = "conflict_flags"

    id = Column(Integer, primary_key=True, index=True)
    document_id_a = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    document_id_b = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)

    description = Column(Text, nullable=True)
    status = Column(String(20), default=ConflictStatus.OPEN, nullable=False)

    created_at = Column(DateTime, default=utcnow, nullable=False)

    # Who closed the flag, and when.
    resolved_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    resolved_at = Column(DateTime, nullable=True)
