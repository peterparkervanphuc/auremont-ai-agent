from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from backend.core.mysql_client import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=True)
    status = Column(String(50), default="pending", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

