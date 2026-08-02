"""Tool tra cứu tồn kho qua API nội bộ real-time của công ty.

TODO:
- Gọi HTTP tới `settings.inventory_api_url` (kèm `settings.inventory_api_key`) để tra tồn kho căn theo
  project_id/mã căn/loại căn — dùng làm Tool (Function Calling) cho Main Agent khi câu hỏi cần dữ liệu
  Bảng hàng real-time (không có sẵn trong Vector DB).
- Bọc lỗi kết nối/timeout thành `InventoryApiError` để router/pipeline hiển thị đúng thông báo
  "Tạm thời không tra được tồn kho" thay vì để lỗi rơi tự do.
"""

from dataclasses import dataclass


class InventoryApiError(Exception):
    """Mất kết nối hoặc lỗi phản hồi từ API tồn kho nội bộ."""


@dataclass
class InventoryUnit:
    unit_code: str
    project_id: str
    unit_type: str | None
    price: float | None
    status: str


def lookup_inventory(project_id: str, query: str) -> list[InventoryUnit]:
    """Gọi API tồn kho real-time của công ty. Raise InventoryApiError khi mất kết nối."""
    raise NotImplementedError("TODO: implement HTTP call to inventory_api_url")
