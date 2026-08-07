from unittest.mock import patch

import httpx
import pytest

from backend.core.config import settings
from backend.services.inventory_service import (
    InventoryApiError,
    lookup_inventory,
)

MOCK_URL = "https://mockapi.io/api/v1/inventory"

# Shape đúng như mock API trả về: có field lạ `id` mà InventoryUnit không khai báo.
MOCK_UNITS = [
    {
        "id": "1",
        "unit_code": "OP3-A-0102",
        "project_id": "ocean-park-3",
        "unit_type": "1PN",
        "price": 2400000000,
        "status": "available",
    },
    {
        "id": "2",
        "unit_code": "OP3-A-0203",
        "project_id": "ocean-park-3",
        "unit_type": "2PN",
        "price": 3600000000,
        "status": "available",
    },
    {
        "id": "3",
        "unit_code": "OP3-B-1105",
        "project_id": "ocean-park-3",
        "unit_type": "2PN",
        "price": 3750000000,
        "status": "reserved",
    },
    {
        "id": "4",
        "unit_code": "OP3-B-1801",
        "project_id": "ocean-park-3",
        "unit_type": "3PN",
        "price": 5200000000,
        "status": "sold",
    },
]


@pytest.fixture(autouse=True)
def configured_api(monkeypatch):
    """Trỏ config sang mock API. monkeypatch tự trả lại giá trị cũ sau mỗi test."""
    monkeypatch.setattr(settings, "inventory_api_url", MOCK_URL)
    monkeypatch.setattr(settings, "inventory_api_key", "")


def _response(payload, status_code: int = 200) -> httpx.Response:
    """Response thật của httpx — cần `request` thì raise_for_status mới chạy được."""
    return httpx.Response(status_code, json=payload, request=httpx.Request("GET", MOCK_URL))


def _text_response(body: str) -> httpx.Response:
    return httpx.Response(200, text=body, request=httpx.Request("GET", MOCK_URL))


# --- Luồng thành công ---------------------------------------------------------------


@patch("httpx.get")
def test_filters_by_unit_type_in_question(mock_get):
    """Câu hỏi nhắc '2PN' thì chỉ trả về căn 2PN."""
    mock_get.return_value = _response(MOCK_UNITS)

    result = lookup_inventory("ocean-park-3", "Còn căn 2PN nào trống không em?")

    assert [unit.unit_code for unit in result] == ["OP3-A-0203", "OP3-B-1105"]
    assert all(unit.unit_type == "2PN" for unit in result)


@patch("httpx.get")
def test_returns_all_units_when_question_has_no_unit_type(mock_get):
    """Hỏi chung chung thì không lọc — để Agent tự tóm tắt toàn bảng hàng."""
    mock_get.return_value = _response(MOCK_UNITS)

    result = lookup_inventory("ocean-park-3", "Dự án còn hàng không?")

    assert len(result) == 4


@patch("httpx.get")
def test_unit_type_matching_ignores_case_and_spacing(mock_get):
    """'3 pn' viết rời và thường vẫn khớp '3PN' của API."""
    mock_get.return_value = _response(MOCK_UNITS)

    result = lookup_inventory("ocean-park-3", "cho anh xin căn 3 pn")

    assert [unit.unit_code for unit in result] == ["OP3-B-1801"]


@patch("httpx.get")
def test_word_boundary_prevents_substring_match(mock_get):
    """'21PN' không được bắt nhầm thành '1PN'."""
    mock_get.return_value = _response(MOCK_UNITS)

    result = lookup_inventory("ocean-park-3", "có căn 21PN không")

    assert result == []


@patch("httpx.get")
def test_sends_project_id_and_auth_header(mock_get):
    """project_id đi vào query param, API key đi vào Authorization."""
    mock_get.return_value = _response(MOCK_UNITS)

    with patch.object(settings, "inventory_api_key", "secret-token"):
        lookup_inventory("ocean-park-3", "còn hàng không")

    _, kwargs = mock_get.call_args
    assert kwargs["params"] == {"project_id": "ocean-park-3"}
    assert kwargs["headers"]["Authorization"] == "Bearer secret-token"
    assert kwargs["timeout"] == 5.0


@patch("httpx.get")
def test_omits_auth_header_when_no_api_key(mock_get):
    """Mock API công khai không cần key — không gửi header rỗng."""
    mock_get.return_value = _response(MOCK_UNITS)

    lookup_inventory("ocean-park-3", "còn hàng không")

    assert "Authorization" not in mock_get.call_args.kwargs["headers"]


# --- Hết hàng: rỗng, KHÔNG phải lỗi -------------------------------------------------


@patch("httpx.get")
def test_empty_inventory_returns_empty_list(mock_get):
    """Dự án hết sạch hàng là câu trả lời hợp lệ, không phải sự cố API."""
    mock_get.return_value = _response([])

    assert lookup_inventory("ocean-park-3", "còn căn nào không") == []


@patch("httpx.get")
def test_no_matching_unit_type_returns_empty_list(mock_get):
    """Hỏi Penthouse mà bảng hàng không có thì trả rỗng, không nổ lỗi."""
    mock_get.return_value = _response(MOCK_UNITS)

    assert lookup_inventory("ocean-park-3", "còn Penthouse không") == []


# --- Dữ liệu bẩn ---------------------------------------------------------------------


@patch("httpx.get")
def test_skips_records_missing_required_fields(mock_get):
    """Một dòng dữ liệu hỏng không được làm hỏng cả lần tra cứu."""
    mock_get.return_value = _response(
        [
            {
                "unit_code": "OP3-A-0203",
                "project_id": "ocean-park-3",
                "unit_type": "2PN",
                "price": 3600000000,
                "status": "available",
            },
            {"project_id": "ocean-park-3", "unit_type": "2PN"},  # thiếu unit_code + status
            "không phải object",
        ]
    )

    result = lookup_inventory("ocean-park-3", "căn 2PN")

    assert len(result) == 1
    assert result[0].unit_code == "OP3-A-0203"


@patch("httpx.get")
def test_coerces_price_and_tolerates_bad_price(mock_get):
    """Giá về dạng chuỗi vẫn thành float; giá rác thì để None chứ không bỏ cả căn."""
    mock_get.return_value = _response(
        [
            {"unit_code": "A", "project_id": "p", "unit_type": "2PN", "price": "3600000000", "status": "available"},
            {"unit_code": "B", "project_id": "p", "unit_type": "2PN", "price": "liên hệ", "status": "available"},
        ]
    )

    result = lookup_inventory("p", "căn 2PN")

    assert result[0].price == 3600000000.0
    assert result[1].price is None
    assert result[1].unit_code == "B"


@patch("httpx.get")
def test_missing_unit_type_becomes_none(mock_get):
    mock_get.return_value = _response([{"unit_code": "A", "project_id": "p", "status": "available"}])

    result = lookup_inventory("p", "còn hàng không")

    assert result[0].unit_type is None
    assert result[0].price is None


# --- Sự cố API: luôn là InventoryApiError -------------------------------------------


@patch("httpx.get")
def test_connection_error_becomes_inventory_api_error(mock_get):
    """Đứt mạng — pipeline cần thấy InventoryApiError để báo 'Tạm thời không tra được tồn kho'."""
    mock_get.side_effect = httpx.ConnectError("Connection refused")

    with pytest.raises(InventoryApiError, match="Inventory API unreachable"):
        lookup_inventory("ocean-park-3", "còn căn nào không")


@patch("httpx.get")
def test_timeout_becomes_inventory_api_error(mock_get):
    mock_get.side_effect = httpx.TimeoutException("Read timeout")

    with pytest.raises(InventoryApiError, match="Inventory API unreachable"):
        lookup_inventory("ocean-park-3", "còn căn nào không")


@patch("httpx.get")
def test_http_500_becomes_inventory_api_error(mock_get):
    """raise_for_status ném HTTPStatusError — cũng phải bị bọc lại."""
    mock_get.return_value = _response({"message": "server error"}, status_code=500)

    with pytest.raises(InventoryApiError, match="Inventory API unreachable"):
        lookup_inventory("ocean-park-3", "còn căn nào không")


@patch("httpx.get")
def test_non_json_body_becomes_inventory_api_error(mock_get):
    """URL trỏ sai chỗ, API trả trang HTML thay vì JSON."""
    mock_get.return_value = _text_response("<html>404 Not Found</html>")

    with pytest.raises(InventoryApiError, match="không phải JSON"):
        lookup_inventory("ocean-park-3", "còn căn nào không")


@patch("httpx.get")
def test_non_list_payload_becomes_inventory_api_error(mock_get):
    """JSON hợp lệ nhưng là object — không lặp được thành danh sách căn."""
    mock_get.return_value = _response({"data": []})

    with pytest.raises(InventoryApiError, match="cần một list"):
        lookup_inventory("ocean-park-3", "còn căn nào không")


def test_missing_config_becomes_inventory_api_error(monkeypatch):
    """Chưa cấu hình URL thì báo rõ ràng, không để httpx nổ lỗi khó hiểu."""
    monkeypatch.setattr(settings, "inventory_api_url", "")

    with pytest.raises(InventoryApiError, match="chưa được cấu hình"):
        lookup_inventory("ocean-park-3", "còn căn nào không")
