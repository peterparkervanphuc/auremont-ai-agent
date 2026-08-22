from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.enums import (
    DocumentCategory,
    DocumentReviewStatus,
    DocumentStatus,
    DocumentVisibility,
    LegalStatus,
)
from backend.core.mysql_client import Base
from backend.utils.time import utcnow


class Document(Base):
    """A file in the knowledge base.

    File có thể là chính sách bán hàng, bảng giá, thông tin phân khu,
    tài liệu pháp lý hoặc tài liệu nội bộ. Metadata được AI đề xuất và
    Admin xác nhận trước khi tài liệu được dùng để trả lời.
    """

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # ----------------------- File và quyền truy cập -----------------------
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50),
        default=DocumentStatus.PENDING,
        nullable=False,
        index=True,
    )
    visibility: Mapped[str] = mapped_column(
        String(20),
        default=DocumentVisibility.INTERNAL,
        nullable=False,
        index=True,
    )

    uploaded_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    # ----------------------- Phạm vi áp dụng dự án -----------------------
    # None nghĩa là tài liệu áp dụng chung cho toàn công ty / toàn bộ dự án.
    project_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("projects.id"),
        nullable=True,
        index=True,
    )

    # Một file có thể áp dụng cho nhiều phân khu, ví dụ:
    # ["The Beverly", "The London"].
    subdivision_names: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # Một file có thể áp dụng cho nhiều tòa/block.
    # Ví dụ: ["S1.01", "S1.02"].
    building_codes: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # Ví dụ: ["Studio", "1PN+", "2PN", "3PN"].
    unit_types: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # Ví dụ: Hà Nội, Hưng Yên hoặc phạm vi pháp lý "toàn quốc".
    applicable_area: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ----------------------- Phân loại nghiệp vụ -----------------------
    category: Mapped[str] = mapped_column(
        String(50),
        default=DocumentCategory.OTHER,
        nullable=False,
        index=True,
    )
    subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # Ví dụ:
    # "Chính sách bán hàng The Beverly tháng 08/2026"
    document_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # AI đề xuất, Admin duyệt.
    review_status: Mapped[str] = mapped_column(
        String(30),
        default=DocumentReviewStatus.PENDING,
        nullable=False,
        index=True,
    )
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    classification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The LLM's original safety signal is retained after an Admin reviews the document,
    # so the audit trail can distinguish an automatic approval from a human decision.
    # Legacy rows are NULL because the old classifier never produced this signal.
    classification_requires_admin_review: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    classification_version: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    classified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Canonical business facts extracted by the classifier for semantic conflict
    # comparison. The JSON shape is versioned by `classification_version`.
    conflict_facts: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)

    reviewed_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # ----------------------- Phiên bản và thời gian áp dụng -----------------------
    # Dùng cho cả chính sách bán hàng lẫn văn bản luật.
    version_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    issued_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Với chính sách/bảng giá: ví dụ "08/2026", "Đợt 1".
    applicable_period: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ----------------------- Metadata pháp lý -----------------------
    # Các field này chỉ cần điền nếu category = legal_document.
    legal_document_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    legal_document_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    legal_issuer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    legal_domain: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    legal_status: Mapped[str] = mapped_column(
        String(30),
        default=LegalStatus.UNKNOWN,
        nullable=False,
        index=True,
    )
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
