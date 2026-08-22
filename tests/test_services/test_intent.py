"""Keyword classifiers behind the customer-chat gates and the AI→Sale handoff trigger."""

from backend.ai.intent import needs_human_handoff, needs_inventory, needs_registration_gate, wants_human_agent


def test_needs_inventory_matches_a_budget_threshold():
    """A budget-based recommendation is an inventory question too — see intent.py's
    _PRICE_THRESHOLD_PATTERN: without it this falls through to document retrieval, which
    has nothing shaped like "under 5 billion" to match."""
    assert needs_inventory("tư vấn cho tôi căn hộ dưới 5 tỷ")
    assert needs_inventory("con can nao duoi 5 ty khong")  # no diacritics
    assert needs_inventory("có căn nào trên 3 tỷ không")
    assert needs_inventory("tối đa 4,5 tỷ thì xem được căn nào")


def test_needs_inventory_matches_a_budget_range():
    assert needs_inventory("từ 3 tỷ đến 5 tỷ có căn nào không")
    assert needs_inventory("căn hộ tầm 3-5 tỷ")


def test_needs_inventory_ignores_a_bare_price_answer_without_a_threshold_word():
    """A plain price question ("giá căn 2PN?") still belongs to the price-list document,
    not the live inventory tool — only an explicit threshold routes to the tool."""
    assert not needs_inventory("Giá căn 2PN dự án Ocean Park 3 là bao nhiêu?")


def test_needs_registration_gate_matches_closing_questions():
    assert needs_registration_gate("Cho mình xin bảng giá chi tiết với ạ")
    assert needs_registration_gate("con can gui bang gia chi tiet khong")  # no diacritics


def test_needs_registration_gate_ignores_general_questions():
    assert not needs_registration_gate("Dự án ở vị trí nào?")


def test_wants_human_agent_matches_explicit_asks():
    assert wants_human_agent("Cho mình gặp người thật được không")
    assert wants_human_agent("cho gap chuyen vien tu van")  # no diacritics


def test_wants_human_agent_ignores_general_questions():
    assert not wants_human_agent("Căn hộ có mấy phòng ngủ?")


def test_needs_human_handoff_covers_closing_questions():
    """A logged-in customer's closing-adjacent question should hand off to a Sale, the
    same signal that gates an anonymous visitor behind registration."""
    assert needs_human_handoff("Cho mình xin bảng giá chi tiết")


def test_needs_human_handoff_covers_explicit_requests():
    assert needs_human_handoff("Tôi muốn gặp chuyên viên")


def test_needs_human_handoff_covers_frustration():
    assert needs_human_handoff("AI trả lời linh tinh quá, chán ghê")


def test_needs_human_handoff_ignores_general_questions():
    assert not needs_human_handoff("Dự án có những tiện ích gì?")
