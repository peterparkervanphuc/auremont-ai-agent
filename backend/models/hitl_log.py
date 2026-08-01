from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from backend.core.enums import HitlStatus
from backend.core.mysql_client import Base


class HitlLog(Base):
    """Audit trail for the mandatory HITL confirmation on price/commitment answers (CLAUDE.md §6.4.e)."""

    __tablename__ = "hitl_logs"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False, index=True)
    sale_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    status = Column(String(20), default=HitlStatus.PENDING, nullable=False)
    confirmed_content = Column(Text, nullable=True)  # snapshot of what was actually confirmed/sent
    confirmed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
