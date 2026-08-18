from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text

from backend.core.enums import DocumentRelationType, DocumentReviewStatus
from backend.core.mysql_client import Base
from backend.models import (  # noqa: F401
    chat_session,
    conflict_flag,
    document,
    document_relation,
    feedback,
    hitl_log,
    message,
    project,
    user,
)
from backend.utils.time import utcnow


class DocumentRelation(Base):
    """How a newly uploaded document affects an existing one.

    Ví dụ:
    - Chính sách tháng 08 thay thế chính sách tháng 07.
    - Bảng giá đợt 2 cập nhật bảng giá đợt 1.
    - Nghị định mới bãi bỏ một nghị định cũ.
    """

    __tablename__ = "document_relations"

    id = Column(Integer, primary_key=True, index=True)

    source_document_id = Column(
        Integer,
        ForeignKey("documents.id"),
        nullable=False,
        index=True,
    )
    target_document_id = Column(
        Integer,
        ForeignKey("documents.id"),
        nullable=False,
        index=True,
    )

    relation_type = Column(
        String(30),
        default=DocumentRelationType.RELATED_TO,
        nullable=False,
        index=True,
    )

    # Ví dụ: "Chỉ thay thế chính sách cho phân khu The Beverly".
    scope_note = Column(Text, nullable=True)

    # Đoạn text AI/rule tìm thấy để đề xuất quan hệ.
    evidence = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)

    review_status = Column(
        String(30),
        default=DocumentReviewStatus.PENDING,
        nullable=False,
        index=True,
    )

    reviewed_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
