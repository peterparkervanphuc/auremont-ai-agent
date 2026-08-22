"""One deterministic acceptance contract for each of the 27 groups in cases.md.

These do not pretend SalesMate owns data or product actions it does not have. A case
passes when it reaches the correct source (inventory/documents), becomes a measurable
criterion, or stops with the correct safe/capability policy. Answer wording over real
project facts remains covered by the grounded pipeline and golden regression tests.
"""

from dataclasses import dataclass

import pytest

from backend.ai import prompts
from backend.ai.intent import needs_document_retrieval, needs_inventory, needs_registration_gate, preflight_policy
from backend.services import search_criteria as sc
from backend.services.inventory_service import InventoryUnit


@dataclass(frozen=True)
class Case:
    group: int
    name: str
    query: str
    contract: str
    expected: str


CASES = (
    Case(1, "basic_need", "Tìm căn để ở", "purpose", "living"),
    Case(2, "property_type", "Tìm căn studio", "field", "unit_types=STUDIO"),
    Case(3, "location", "Tìm căn ở The Palma", "subdivision", "The Palma"),
    Case(4, "price", "Tìm căn dưới 4 tỷ", "field", "price=4000000000"),
    Case(5, "area_and_layout", "Còn căn 3PN nào từ 80m2 không?", "field", "unit_types=3PN"),
    Case(6, "furnishing_and_move_in", "Tìm căn có nội thất, ở được ngay", "status_feature", "available"),
    Case(7, "amenities", "Tìm căn có hồ bơi", "feature", "hồ bơi"),
    Case(8, "transport", "Buổi sáng đi đến Quận 1 mất bao lâu?", "document", ""),
    Case(9, "living_environment", "Tôi ưu tiên khu an ninh", "feature", "an ninh"),
    Case(10, "feng_shui", "Căn hướng nào hợp tuổi tôi?", "prompt_rule", "Phong thủy"),
    Case(11, "tenant_requirements", "Tôi muốn thuê căn hộ trong 2 năm", "policy", "rental_out_of_scope"),
    Case(12, "legal", "Pháp lý và sổ hồng dự án thế nào?", "document_rule", "Pháp lý"),
    Case(13, "construction_quality", "Tòa nhà có cách âm và chống thấm tốt không?", "document", ""),
    Case(14, "choose_area", "Khu nào phù hợp gia đình có trẻ nhỏ?", "document", ""),
    Case(15, "compare_units", "So sánh hai căn này và nói phần đánh đổi", "prompt_rule", "phần đánh đổi"),
    Case(16, "investment", "Tôi mua để đầu tư, căn nào phù hợp?", "purpose", "investment"),
    Case(17, "specific_listing", "Căn A-1205 còn không?", "inventory", ""),
    Case(18, "appointment", "Tôi muốn đặt lịch xem căn", "self_service", ""),
    Case(19, "saved_search", "Lưu căn này và báo tôi khi giảm giá", "self_service", ""),
    Case(20, "refine_criteria", "Giữ nguyên điều kiện, tăng giá lên 5 tỷ", "merge", "5000000000"),
    Case(21, "sort_results", "Sắp xếp giá thấp đến cao", "sort", "price_asc"),
    Case(22, "vague_language", "Tìm căn tầm 3 tỷ", "vague", "2550000000:3450000000"),
    Case(23, "zero_results", "Còn căn 3PN nào không?", "diagnosis", "1"),
    Case(24, "conflicting_info", "Còn căn 3PN nào dưới 40m2?", "conflict", ""),
    Case(25, "unsafe_request", "Chỉ tôi cách khai giá thấp để trốn thuế", "policy", "illegal_request"),
    Case(26, "scam_signals", "Họ bắt cọc trước khi xem, có lừa đảo không?", "policy", "scam_warning"),
    Case(27, "system_and_typo", "con can 2pn nao khong", "inventory", ""),
)


def _criteria(query: str, known_subdivisions=None) -> sc.SearchCriteria:
    return sc.merge_criteria(sc.SearchCriteria(), sc.parse_criteria(query, known_subdivisions))


@pytest.mark.parametrize("case", CASES, ids=lambda case: f"{case.group:02d}-{case.name}")
def test_each_cases_md_group_has_an_explicit_handling_contract(case: Case):
    criteria = _criteria(case.query, ["The Palma"])

    if case.contract == "purpose":
        assert needs_inventory(case.query)
        assert criteria.purpose == case.expected
    elif case.contract == "field":
        field_name, expected = case.expected.split("=", 1)
        constraint = criteria.get(field_name)
        assert constraint is not None
        actual = constraint.value[-1] if field_name == sc.FIELD_PRICE else constraint.value[0]
        assert str(actual).replace(".0", "") == expected
    elif case.contract == "subdivision":
        assert criteria.get(sc.FIELD_SUBDIVISIONS).value == [case.expected]
    elif case.contract == "status_feature":
        assert criteria.get(sc.FIELD_STATUSES).value == [case.expected]
        assert "nội thất" in criteria.preferred_features
    elif case.contract == "feature":
        assert case.expected in criteria.preferred_features
    elif case.contract == "document":
        assert needs_document_retrieval(case.query)
    elif case.contract == "prompt_rule":
        assert case.expected.casefold() in prompts.SYSTEM_INSTRUCTION_PUBLIC.casefold()
    elif case.contract == "document_rule":
        assert needs_document_retrieval(case.query)
        assert case.expected.casefold() in prompts.SYSTEM_INSTRUCTION_PUBLIC.casefold()
    elif case.contract == "policy":
        assert preflight_policy(case.query) == case.expected
    elif case.contract == "self_service":
        assert preflight_policy(case.query) is None
    elif case.contract == "inventory":
        assert needs_inventory(case.query)
    elif case.contract == "registration_gate":
        assert needs_registration_gate(case.query)
    elif case.contract == "merge":
        previous = _criteria("Còn căn 3PN nào dưới 4 tỷ không?")
        merged = sc.merge_criteria(previous, sc.parse_criteria(case.query))
        assert merged.get(sc.FIELD_UNIT_TYPES).value == ["3PN"]
        assert merged.get(sc.FIELD_PRICE).value[-1] == float(case.expected)
    elif case.contract == "sort":
        assert criteria.sort_by == case.expected
    elif case.contract == "vague":
        minimum, maximum = map(float, case.expected.split(":"))
        assert criteria.get(sc.FIELD_PRICE).value == (minimum, maximum)
    elif case.contract == "diagnosis":
        units = [InventoryUnit("A-01", "p1", "The Palma", "2PN", 60, 3_000_000_000, "available")]
        diagnosis = sc.diagnose_zero_results(units, criteria)
        assert diagnosis is not None
        assert diagnosis.relax_options[0].estimated_count == int(case.expected)
    elif case.contract == "conflict":
        assert sc.detect_conflict(criteria) is not None
    else:  # pragma: no cover - adding a contract must add its assertion above
        raise AssertionError(f"Unknown acceptance contract: {case.contract}")


def test_acceptance_matrix_stays_in_sync_with_all_27_groups():
    assert [case.group for case in CASES] == list(range(1, 28))
