from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from backend.core.enums import DocumentStatus, DocumentVisibility
from backend.core.mysql_client import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=True)
    status = Column(String(50), default=DocumentStatus.PENDING, nullable=False)

    # Nhãn RBAC — mặc định INTERNAL để tài liệu quên gán nhãn không bị chia sẻ ra ngoài.
    visibility = Column(String(20), default=DocumentVisibility.INTERNAL, nullable=False)

    # Ingestion provenance — which Admin uploaded this file, and when.
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

