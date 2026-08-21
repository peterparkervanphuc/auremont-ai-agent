"""Keyword classifiers behind the customer-chat gates and the AI→Sale handoff trigger."""

from backend.ai.intent import (
    is_conversation_meta_query,
    needs_human_handoff,
    needs_registration_gate,
    wants_human_agent,
)


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


def test_conversation_meta_query_matches_questions_about_the_transcript():
    """These are answerable only from the session history, so the pipeline must route them
    past the Verifier — see agent_pipeline._route_after_generate."""
    assert is_conversation_meta_query("tôi vừa hỏi về phân khu nào")
    assert is_conversation_meta_query("bạn vừa nói gì vậy")
    assert is_conversation_meta_query("tóm tắt lại cuộc trò chuyện giúp tôi")
    assert is_conversation_meta_query("toi vua hoi ve phan khu nao")  # no diacritics


def test_conversation_meta_query_ignores_project_questions():
    """The costly direction to get wrong: a real project question skipping verification."""
    assert not is_conversation_meta_query("The Zenpark ở đâu")
    assert not is_conversation_meta_query("Giá căn 2PN bao nhiêu")
    assert not is_conversation_meta_query("Chính sách bán hàng thế nào")
