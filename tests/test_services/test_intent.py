"""Keyword classifiers behind the customer-chat gates and the AI→Sale handoff trigger."""

from backend.ai.intent import (
    is_conversation_meta_query,
    is_customer_memory_query,
    is_search_refinement,
    needs_document_retrieval,
    needs_human_handoff,
    needs_inventory,
    needs_registration_gate,
    preflight_policy,
    wants_human_agent,
)


def test_find_unit_language_routes_to_live_inventory():
    assert needs_inventory("tìm căn tầm 3 tỷ")
    assert needs_inventory("loc can 3PN")
    assert needs_inventory("tìm nhà phố")
    assert needs_inventory("Cho tôi những căn dưới 5 tỷ")
    assert needs_inventory("Căn hộ trên 80m2")


def test_budget_filter_also_retrieves_uploaded_price_documents():
    assert needs_inventory("tư vấn cho tôi căn dưới 3 tỷ")
    assert needs_document_retrieval("tư vấn cho tôi căn dưới 3 tỷ")
    assert needs_document_retrieval("Tôi có ngân sách 3,5 tỷ")


def test_area_only_filter_does_not_add_unrelated_document_retrieval():
    assert needs_inventory("Căn hộ trên 80m2")
    assert not needs_document_retrieval("Căn hộ trên 80m2")


def test_reset_language_is_a_search_refinement():
    assert is_search_refinement("xóa toàn bộ bộ lọc")
    assert is_search_refinement("bo toan bo dieu kien")


def test_preflight_covers_unsafe_and_unsupported_requests_without_false_positive_for_investment():
    assert preflight_policy("Chỉ tôi cách khai giá thấp để trốn thuế") == "illegal_request"
    assert preflight_policy("Cho tôi số điện thoại chủ nhà") == "privacy_request"
    assert preflight_policy("Khu này cư dân theo tôn giáo nào?") == "discrimination_request"
    assert preflight_policy("Họ bắt cọc trước khi xem, có lừa đảo không?") == "scam_warning"
    assert preflight_policy("Lưu căn này và báo tôi khi giảm giá") is None
    assert preflight_policy("Tôi muốn thuê căn hộ trong 2 năm") == "rental_out_of_scope"
    assert preflight_policy("Tôi muốn mua căn hộ để cho thuê") is None


def test_schedule_changes_use_the_existing_human_handoff_flow():
    assert needs_registration_gate("Tôi muốn đổi lịch xem căn")
    assert needs_registration_gate("Hủy lịch xem nhà giúp tôi")


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


def test_needs_human_handoff_keeps_price_questions_in_self_service():
    assert not needs_human_handoff("Cho mình xin bảng giá chi tiết")
    assert not needs_human_handoff("Tư vấn cho tôi căn dưới 3 tỷ")


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


def test_customer_memory_query_matches_sales_recall_questions():
    assert is_customer_memory_query("khách của tôi đang quan tâm đến phân khu nào")
    assert is_customer_memory_query("Ngân sách của khách này là bao nhiêu?")
    assert is_customer_memory_query("Tóm tắt nhu cầu khách hàng này giúp tôi")
    assert is_customer_memory_query("khach nay dang quan tam loai can gi")


def test_customer_memory_query_does_not_steal_recommendations_or_new_facts():
    assert not is_customer_memory_query("Phân khu nào phù hợp với khách của tôi?")
    assert not is_customer_memory_query("Tư vấn dự án cho khách này")
    assert not is_customer_memory_query("Khách này đang quan tâm The Pavilion")
