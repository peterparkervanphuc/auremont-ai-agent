from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from backend.core.enums import UnitStatus


class InventoryUnitImageResponse(BaseModel):
    id: int
    image_path: str

    model_config = {"from_attributes": True}


class InventoryUnitCreate(BaseModel):
    """Kênh 2 — Form UI thêm/sửa 1 căn lẻ (CLAUDE.md §6.6.b)."""

    unit_code: str
    project_id: str
    building: str | None = None
    floor: str | None = None
    unit_type: str | None = None
    area_sqm: Decimal | None = None
    price: Decimal | None = None
    status: UnitStatus = UnitStatus.AVAILABLE
    extra_attributes: dict[str, Any] | None = None
    is_public: bool = True


class InventoryUnitUpdate(BaseModel):
    project_id: str | None = None
    building: str | None = None
    floor: str | None = None
    unit_type: str | None = None
    area_sqm: Decimal | None = None
    price: Decimal | None = None
    status: UnitStatus | None = None
    extra_attributes: dict[str, Any] | None = None
    is_public: bool | None = None


class InventoryUnitResponse(BaseModel):
    id: int
    unit_code: str
    project_id: str
    building: str | None = None
    floor: str | None = None
    unit_type: str | None = None
    area_sqm: Decimal | None = None
    price: Decimal | None = None
    status: UnitStatus
    extra_attributes: dict[str, Any] | None = None
    is_public: bool
    has_images: bool
    images: list[InventoryUnitImageResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InventoryUnitFilter(BaseModel):
    """Query params for the public listing (CLAUDE.md §6.3.a)."""

    project_id: str | None = None
    unit_type: str | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None


class InventoryBulkUploadRow(BaseModel):
    """Kết quả preview 1 dòng sau khi match Excel + ảnh (CLAUDE.md §6.6.a bước 4)."""

    unit_code: str
    has_image: bool
    error: str | None = None


class InventoryBulkUploadPreview(BaseModel):
    rows: list[InventoryBulkUploadRow]
    total: int
    missing_images: int
