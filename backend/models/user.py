from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.mysql_client import Base


class User(Base):
    """
    SQLAlchemy ORM Model representing a system User.

    # TODO: Database Schema Mapping
    # 1. Map this class to the 'users' table in MySQL.
    # 2. Set up password hashing hooks via passlib/bcrypt before committing records.
    # 3. (Optional) Establish a relationship mapping if users own uploaded documents.
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)

    # TODO: Define distinct constraints for registration attributes
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)

    # Stores the hashed string, never plaintext
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # Authorization scopes (e.g., 'admin', 'compliance_officer', 'viewer')
    role: Mapped[str] = mapped_column(String(20), default="viewer", nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

