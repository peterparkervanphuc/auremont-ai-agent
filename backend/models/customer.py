from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String

from backend.core.mysql_client import Base


class Customer(Base):
    """External end-buyer actor, authenticated via OTP (phone/email) — kept separate from `User` (CLAUDE.md §4)."""

    __tablename__ = "customers"

    id = Column(String(36), primary_key=True, index=True)
    phone = Column(String(20), unique=True, index=True, nullable=True)
    email = Column(String(100), unique=True, index=True, nullable=True)
    full_name = Column(String(255), nullable=True)

    is_verified = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
