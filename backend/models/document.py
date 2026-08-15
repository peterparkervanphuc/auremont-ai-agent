from sqlalchemy import JSON, Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text

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

    id = Column(Integer, primary_key=True, index=True)

    # ----------------------- File và quyền truy cập -----------------------
    title = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=True)
    status = Column(
        String(50),
        default=DocumentStatus.PENDING,
        nullable=False,
        index=True,
    )
    visibility = Column(
        String(20),
        default=DocumentVisibility.INTERNAL,
        nullable=False,
        index=True,
    )

    uploaded_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    uploaded_at = Column(DateTime, default=utcnow, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    # ----------------------- Phạm vi áp dụng dự án -----------------------
    # None nghĩa là tài liệu áp dụng chung cho toàn công ty / toàn bộ dự án.
    project_id = Column(
        String(36),
        ForeignKey("projects.id"),
        nullable=True,
        index=True,
    )

    # Một file có thể áp dụng cho nhiều phân khu, ví dụ:
    # ["The Beverly", "The London"].
    subdivision_names = Column(JSON, nullable=True)

    # Một file có thể áp dụng cho nhiều tòa/block.
    # Ví dụ: ["S1.01", "S1.02"].
    building_codes = Column(JSON, nullable=True)

    # Ví dụ: ["Studio", "1PN+", "2PN", "3PN"].
    unit_types = Column(JSON, nullable=True)

    # Ví dụ: Hà Nội, Hưng Yên hoặc phạm vi pháp lý "toàn quốc".
    applicable_area = Column(String(255), nullable=True)

    # ----------------------- Phân loại nghiệp vụ -----------------------
    category = Column(
        String(50),
        default=DocumentCategory.OTHER,
        nullable=False,
        index=True,
    )
    subcategory = Column(String(100), nullable=True, index=True)

    # Ví dụ:
    # "Chính sách bán hàng The Beverly tháng 08/2026"
    document_summary = Column(Text, nullable=True)

    # AI đề xuất, Admin duyệt.
    review_status = Column(
        String(30),
        default=DocumentReviewStatus.PENDING,
        nullable=False,
        index=True,
    )
    classification_confidence = Column(Float, nullable=True)
    classification_reason = Column(Text, nullable=True)
    classified_at = Column(DateTime, nullable=True)

    reviewed_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    reviewed_at = Column(DateTime, nullable=True)

    # ----------------------- Phiên bản và thời gian áp dụng -----------------------
    # Dùng cho cả chính sách bán hàng lẫn văn bản luật.
    version_label = Column(String(100), nullable=True)
    issued_date = Column(Date, nullable=True)
    effective_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True)

    # Với chính sách/bảng giá: ví dụ "08/2026", "Đợt 1".
    applicable_period = Column(String(100), nullable=True)

    # ----------------------- Metadata pháp lý -----------------------
    # Các field này chỉ cần điền nếu category = legal_document.
    legal_document_type = Column(String(100), nullable=True, index=True)
    legal_document_number = Column(String(100), nullable=True, index=True)
    legal_issuer = Column(String(255), nullable=True)
    legal_domain = Column(String(100), nullable=True, index=True)

    legal_status = Column(
        String(30),
        default=LegalStatus.UNKNOWN,
        nullable=False,
        index=True,
    )
    is_current = Column(Boolean, default=True, nullable=False, index=True)
