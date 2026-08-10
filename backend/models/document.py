from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from backend.core.enums import DocumentStatus, DocumentVisibility
from backend.core.mysql_client import Base
from backend.utils.time import utcnow


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=True)
    status = Column(String(50), default=DocumentStatus.PENDING, nullable=False)

    # RBAC label — defaults to INTERNAL so a document left unlabelled is never
    # accidentally exposed outside the company.
    visibility = Column(String(20), default=DocumentVisibility.INTERNAL, nullable=False)

    # Ingestion provenance — which Admin uploaded this file, and when.
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    uploaded_at = Column(DateTime, default=utcnow, nullable=True)

    created_at = Column(DateTime, default=utcnow, nullable=False)

