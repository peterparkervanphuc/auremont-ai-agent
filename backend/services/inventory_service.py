"""Tool tra cứu tồn kho qua API nội bộ real-time của công ty.

Main Agent gọi hàm này (Function Calling) khi câu hỏi của Sale cần dữ liệu Bảng hàng real-time —
thứ không nằm trong Vector DB vì tồn kho đổi liên tục, ingest vào Qdrant là sẽ trả lời số cũ.

Giai đoạn build đang trỏ `INVENTORY_API_URL` sang một mock API (mockapi.io) dựng đúng shape của API
nội bộ sẽ dùng ở production, nên lúc đổi sang API thật chỉ cần đổi biến môi trường, không sửa code.

Mọi lỗi gọi API được bọc thành `InventoryApiError` để router/pipeline hiển thị đúng thông báo
"Tạm thời không tra được tồn kho" thay vì để lỗi rơi tự do thành 500.
"""

import re
from dataclasses import dataclass, fields

import httpx

from backend.core.config import settings

INVENTORY_TIMEOUT_SECONDS = 5.0

# Loại căn Sale hay nhắc trong câu hỏi: "2PN", "3 pn", "Penthouse", "Studio", "Shophouse", "Duplex".
# \b hai đầu để "21PN" không bị bắt nhầm thành "1PN".
_UNIT_TYPE_PATTERN = re.compile(r"\b(\d+\s*pn|penthouse|studio|shophouse|duplex)\b", re.IGNORECASE)


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
    """Tra tồn kho của một dự án, lọc theo loại căn được nhắc tới trong câu hỏi.

    Trả về danh sách rỗng khi dự án không còn căn nào khớp — đó là một câu trả lời hợp lệ
    ("hiện không còn căn 2PN nào"), khác hẳn với việc không tra được tồn kho. Gộp hai
    trường hợp này lại sẽ khiến Sale thấy báo "Tạm thời không tra được tồn kho" trong khi
    API vẫn chạy tốt và câu trả lời đúng chỉ đơn giản là "hết hàng".

    Raise `InventoryApiError` khi thật sự không lấy được dữ liệu từ API.
    """
    payload = _fetch_units(project_id)

    units = [unit for unit in (_parse_unit(item) for item in payload) if unit is not None]

    wanted_type = _extract_unit_type(query)
    if wanted_type is not None:
        units = [unit for unit in units if _normalize_unit_type(unit.unit_type) == wanted_type]

    return units


def _fetch_units(project_id: str) -> list:
    """Gọi API tồn kho và trả về payload thô, đã chắc chắn là một list."""
    if not settings.inventory_api_url:
        raise InventoryApiError("INVENTORY_API_URL chưa được cấu hình.")

    headers = {}
    if settings.inventory_api_key:
        headers["Authorization"] = f"Bearer {settings.inventory_api_key}"

    try:
        response = httpx.get(
            settings.inventory_api_url,
            params={"project_id": project_id},
            headers=headers,
            timeout=INVENTORY_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        # Bắt trọn nhánh HTTPError: ConnectError, TimeoutException và HTTPStatusError
        # (do raise_for_status ném ra) đều là con của nó.
        raise InventoryApiError(f"Inventory API unreachable: {exc}") from exc
    except ValueError as exc:
        # json.JSONDecodeError kế thừa ValueError — gặp khi API trả về trang HTML lỗi
        # thay vì JSON, thường là lúc URL trỏ sai chỗ.
        raise InventoryApiError("Inventory API trả về body không phải JSON.") from exc

    if not isinstance(payload, list):
        raise InventoryApiError(f"Inventory API trả về {type(payload).__name__}, cần một list.")

    return payload


_FIELD_NAMES = {field.name for field in fields(InventoryUnit)}


def _parse_unit(item: object) -> InventoryUnit | None:
    """Đổi một record thô thành `InventoryUnit`; trả về None nếu record không dùng được.

    Bỏ qua record hỏng thay vì ném lỗi: mock API lẫn API nội bộ đều kèm field lạ (`id`,
    `createdAt`) hoặc thỉnh thoảng thiếu field, và một dòng dữ liệu bẩn không đáng làm
    hỏng cả lần tra cứu của Sale.
    """
    if not isinstance(item, dict):
        return None

    data = {key: value for key, value in item.items() if key in _FIELD_NAMES}
    if not {"unit_code", "project_id", "status"} <= data.keys():
        return None

    unit_type = data.get("unit_type")
    return InventoryUnit(
        unit_code=str(data["unit_code"]),
        project_id=str(data["project_id"]),
        unit_type=str(unit_type) if unit_type is not None else None,
        price=_to_float(data.get("price")),
        status=str(data["status"]),
    )


def _to_float(value: object) -> float | None:
    """Giá có thể về dạng số hoặc chuỗi tuỳ API; giá lỗi thì bỏ trống chứ không chặn cả căn."""
    if value is None or value == "":
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _extract_unit_type(query: str) -> str | None:
    """Rút loại căn từ câu hỏi tự nhiên của Sale. None nghĩa là hỏi chung, không lọc."""
    match = _UNIT_TYPE_PATTERN.search(query)
    return _normalize_unit_type(match.group(0)) if match else None


def _normalize_unit_type(unit_type: str | None) -> str | None:
    """'3 pn' và '3PN' về cùng '3PN' để so khớp không phụ thuộc cách gõ của Sale hay của API."""
    if unit_type is None:
        return None
    return re.sub(r"\s+", "", unit_type).upper()
