from datetime import datetime

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    location: str | None = None
    description: str | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    location: str | None = None
    description: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ProjectSummary(BaseModel):
    """Dữ liệu rút gọn cho thẻ dự án ở trang Tra cứu dự án — suy ra từ `Project.details`."""

    id: str
    name: str
    location: str | None = None
    description: str | None = None
    type: str
    price_from: str | None = None
    cover_image: str | None = None

    model_config = {"from_attributes": True}


class ProjectDetail(ProjectSummary):
    developer: str | None = None
    highlights: list[str] = []
    pricing: list[dict] = []
    amenities: list[dict] = []
    gallery: list[str] = []
    contact: dict | None = None


class CategorySummary(BaseModel):
    """Nhóm sản phẩm theo loại hình (Chung cư/Biệt thự/Shophouse) trong MỘT dự án —
    dùng cho trang Tra cứu vì đây là công cụ Sale nội bộ của một đại đô thị duy nhất,
    không phải sàn liệt kê nhiều dự án khác nhau."""

    slug: str
    name: str
    price_from: str
    price_to: str
    size_from: float | None = None
    size_to: float | None = None
    types_count: int
    cover_image: str | None = None
    type_names: list[str] = []


class CategoryTypeRow(BaseModel):
    type: str
    size_range: str
    price_range: str
    description: str | None = None
    storeys: str | None = None


class CategoryDetail(BaseModel):
    slug: str
    name: str
    description: str
    cover_image: str | None = None
    types: list[CategoryTypeRow]
    amenities: list[dict] = []
    highlights: list[str] = []
    gallery: list[str] = []
