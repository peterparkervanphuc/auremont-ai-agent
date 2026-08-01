from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from backend.core.enums import UnitStatus
from backend.core.mysql_client import Base


class InventoryUnit(Base):
    """Structured inventory data — separate from document RAG ingestion (CLAUDE.md §6.6).

    Schema is hybrid: indexed relational columns for the fields every project shares,
    plus `extra_attributes` JSON for per-project attributes (hướng, view, tiện ích riêng...)
    that don't have a fixed shape across projects.
    """

    __tablename__ = "inventory_units"

    id = Column(Integer, primary_key=True, index=True)
    unit_code = Column(String(50), unique=True, index=True, nullable=False)  # Mã căn
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)  # Dự án

    building = Column(String(100), nullable=True)  # Toà
    floor = Column(String(20), nullable=True)  # Tầng
    unit_type = Column(String(100), nullable=True, index=True)  # Loại căn, e.g. "2PN", "Shophouse"
    area_sqm = Column(Numeric(10, 2), nullable=True, index=True)  # Diện tích
    price = Column(Numeric(15, 2), nullable=True, index=True)  # Giá
    status = Column(String(20), default=UnitStatus.AVAILABLE, nullable=False, index=True)  # Trạng thái

    extra_attributes = Column(JSON, nullable=True)  # thuộc tính phụ: hướng, view, tiện ích riêng...

    is_public = Column(Boolean, default=True, nullable=False)  # hiển thị trên Customer Portal
    has_images = Column(Boolean, default=False, nullable=False)  # "Chưa có hình ảnh" khi batch thiếu ảnh

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)  # ngày_cập_nhật

    project = relationship("Project")
    images = relationship("InventoryUnitImage", back_populates="unit", cascade="all, delete-orphan")


class InventoryUnitImage(Base):
    """Ảnh mặt bằng/căn hộ — file gốc lưu MinIO, đây chỉ lưu đường dẫn tham chiếu (CLAUDE.md §6.6)."""

    __tablename__ = "inventory_unit_images"

    id = Column(Integer, primary_key=True, index=True)
    unit_id = Column(Integer, ForeignKey("inventory_units.id"), nullable=False, index=True)
    image_path = Column(String(512), nullable=False)  # MinIO object path
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    unit = relationship("InventoryUnit", back_populates="images")
