from datetime import date

from backend.core.enums import DocumentCategory, LegalStatus
from backend.services.document_classification_service import (
    classify_document,
)


def test_classifies_sales_policy_with_project_scope():
    result = classify_document(
        "CSBH_The_Beverly_T8_2026.pdf",
        """
        CHÍNH SÁCH BÁN HÀNG
        Phân khu: The Beverly
        Áp dụng từ 01/08/2026 đến 31/08/2026.
        Dành cho căn 1PN+, 2PN và 3PN tại tòa BE1.
        """,
    )

    assert result.category == DocumentCategory.SALES_POLICY
    assert result.subdivision_names == ["The Beverly"]
    assert result.building_codes == ["BE1"]
    assert result.unit_types == ["1PN+", "2PN", "3PN"]
    assert result.effective_date == date(2026, 8, 1)
    assert result.expiry_date == date(2026, 8, 31)
    assert result.confidence >= 0.9


def test_classifies_price_list():
    result = classify_document(
        "Bang_gia_The_Beverly.pdf",
        "BẢNG GIÁ bán căn hộ phân khu The Beverly.",
    )

    assert result.category == DocumentCategory.PRICE_LIST
    assert result.confidence >= 0.88


def test_extracts_legal_document_metadata():
    result = classify_document(
        "Nghi_dinh_96_2024_ND_CP.pdf",
        """
        NGHỊ ĐỊNH 96/2024/NĐ-CP
        CỦA CHÍNH PHỦ

        Quy định chi tiết một số điều của Luật Kinh doanh bất động sản.
        Nghị định này có hiệu lực thi hành kể từ ngày 01/08/2024.
        """,
    )

    assert result.category == DocumentCategory.LEGAL_DOCUMENT
    assert result.legal_document_type == "Nghị định"
    assert result.legal_document_number == "96/2024/NĐ-CP"
    assert result.legal_issuer == "Chính phủ"
    assert result.legal_domain == "Kinh doanh bất động sản"
    assert result.effective_date == date(2024, 8, 1)
    assert result.legal_status == LegalStatus.EFFECTIVE
    assert result.confidence >= 0.97


def test_unknown_document_stays_other():
    result = classify_document(
        "ghi_chu_cuoc_hop.pdf",
        "Nội dung trao đổi chung, không có từ khóa tài liệu dự án.",
    )

    assert result.category == DocumentCategory.OTHER
    assert result.confidence == 0.3
