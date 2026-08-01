from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from backend.core.enums import DocumentStatus, DocumentVisibility
from backend.core.mysql_client import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=True)
    status = Column(String(50), default=DocumentStatus.PENDING, nullable=False)

    # RBAC tier — defaults to INTERNAL so a forgotten label never leaks to the public Chatbot (CLAUDE.md §6.5).
    visibility = Column(String(20), default=DocumentVisibility.INTERNAL, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

