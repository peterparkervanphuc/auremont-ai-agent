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
    assert result.requires_admin_review is False


def test_future_legal_effective_date_is_not_yet_effective():
    result = classify_document(
        "Nghi_dinh_123_2099_ND_CP.pdf",
        """
        NGHỊ ĐỊNH 123/2099/NĐ-CP
        CỦA CHÍNH PHỦ
        Nghị định này có hiệu lực thi hành kể từ ngày 01/01/2099.
        """,
    )

    assert result.effective_date == date(2099, 1, 1)
    assert result.legal_status == LegalStatus.NOT_YET_EFFECTIVE


def test_expired_legal_document_is_not_marked_effective():
    result = classify_document(
        "Nghi_dinh_10_2020_ND_CP.pdf",
        """
        NGHỊ ĐỊNH 10/2020/NĐ-CP
        CỦA CHÍNH PHỦ
        Có hiệu lực từ 01/01/2020 và hết hiệu lực kể từ 01/01/2021.
        """,
    )

    assert result.expiry_date == date(2021, 1, 1)
    assert result.legal_status == LegalStatus.EXPIRED


def test_body_only_legal_signature_still_requires_admin_review():
    result = classify_document(
        "6f42d13e-1908-4a30-a828-e197c1c673db.pdf",
        """
        NGHỊ ĐỊNH 96/2024/NĐ-CP
        CỦA CHÍNH PHỦ
        Quy định chi tiết một số điều của Luật Kinh doanh bất động sản.
        """,
    )

    assert result.category == DocumentCategory.LEGAL_DOCUMENT
    assert result.confidence <= 0.85
    assert result.requires_admin_review is True


def test_unknown_document_stays_other():
    result = classify_document(
        "ghi_chu_cuoc_hop.pdf",
        "Nội dung trao đổi chung, không có từ khóa tài liệu dự án.",
    )

    assert result.category == DocumentCategory.OTHER
    assert result.confidence == 0.3


def test_filename_signal_without_body_confirmation_is_not_auto_approved():
    result = classify_document(
        "CSBH_noi_bo.pdf",
        "Tài liệu làm việc. Nội dung đang được tổng hợp và chưa có tiêu đề chính thức.",
    )

    assert result.category == DocumentCategory.SALES_POLICY
    assert result.confidence == 0.85
    assert "Admin" in result.reason


def test_sales_policy_mentioning_a_decision_is_not_a_legal_document():
    """LEGAL_DOCUMENT khớp 'quyet dinh' và đứng đầu bảng rule.

    Với first-match, một CSBH bình thường nhắc "theo quyết định của Chủ đầu tư" sẽ bị
    xếp thành văn bản luật, rồi bị cắt bằng splitter Điều/Khoản — sai hoàn toàn với
    cấu trúc một file chính sách.
    """
    result = classify_document(
        "Chinh_sach_ban_hang_The_Beverly.pdf",
        """
        CHÍNH SÁCH BÁN HÀNG THÁNG 08/2026
        Mức chiết khấu áp dụng theo quyết định của Chủ đầu tư.
        Công văn hướng dẫn kèm theo.
        """,
    )

    assert result.category == DocumentCategory.SALES_POLICY


def test_keyword_only_in_body_stays_below_the_auto_approve_bar():
    """Một từ khóa lọt trong thân bài không đủ để tự động đưa tài liệu vào kho tri thức."""
    result = classify_document(
        "tai_lieu_gui_khach.pdf",
        "Kèm theo bảng giá tham khảo của dự án.",
    )

    assert result.category == DocumentCategory.PRICE_LIST
    assert result.confidence < 0.9
    assert "Cần Admin xác nhận" in result.reason


def test_keyword_in_filename_with_underscores_is_still_matched():
    """Tên file thật dùng gạch dưới/gạch ngang, không phải dấu cách."""
    result = classify_document("Bang-gia.Q3-2026_The-Palma.pdf", "Nội dung không có từ khóa nào.")

    assert result.category == DocumentCategory.PRICE_LIST
    assert result.confidence == 0.85
    assert result.requires_admin_review is True


def test_price_list_filename_wins_over_policy_phrases_in_body():
    """Bảng giá Zurich thật từng bị xếp thành sales_policy vì các mục chính sách bên trong."""
    result = classify_document(
        "Bang_Gia_The_Zurich_v1.pdf",
        """
        BẢNG GIÁ CĂN HỘ THE ZURICH
        Phiên bản: V1.0 - Tháng 07/2026
        Ngày ban hành: 01/07/2026

        III. CHÍNH SÁCH BÁN HÀNG
        IV. CHÍNH SÁCH GIÁ
        Giá bán và đơn giá chi tiết theo từng mã căn.
        """,
    )

    assert result.category == DocumentCategory.PRICE_LIST
    assert result.version_label == "V1.0"
    assert result.applicable_period == "07/2026"
    assert result.issued_date == date(2026, 7, 1)


def test_strong_body_heading_overrides_a_misleading_filename():
    result = classify_document(
        "Bang_Gia_Hai_Au.pdf",
        """
        CHÍNH SÁCH BÁN HÀNG HẢI ÂU
        Chính sách kinh doanh quy định bảng giá, giá bán và đơn giá tham chiếu
        cho từng loại căn hộ trong đợt mở bán.
        """,
    )

    assert result.category == DocumentCategory.SALES_POLICY
    assert result.confidence < 0.9
    assert "Cần Admin xác nhận" in result.reason


def test_body_only_sales_policy_is_not_overridden_by_legal_references():
    """Các từ Luật/Quyết định trong điều kiện áp dụng không biến CSBH thành văn bản luật."""
    result = classify_document(
        "6f42d13e-1908-4a30-a828-e197c1c673db.pdf",
        """
        CHÍNH SÁCH BÁN HÀNG THE BEVERLY
        Chính sách tuân thủ Luật Kinh doanh bất động sản.
        Mức ưu đãi áp dụng theo quyết định của Chủ đầu tư và công văn hướng dẫn.
        """,
    )

    assert result.category == DocumentCategory.SALES_POLICY
    assert result.confidence < 0.9


def test_project_overview_is_not_a_sales_policy_because_of_a_pricing_section():
    """Mục “Chính sách giá” là phần con phổ biến trong tài liệu giới thiệu phân khu."""
    result = classify_document(
        "HaiAu_VHOP_ThongTinDuAn_Full.pdf",
        """
        TỔNG QUAN DỰ ÁN HẢI ÂU
        Giới thiệu vị trí, quy hoạch, tiện ích và thiết kế của khu đô thị.

        I. VỊ TRÍ
        II. TIỆN ÍCH
        III. MẶT BẰNG
        IV. CHÍNH SÁCH GIÁ BÁN
        Giá bán chỉ mang tính tham khảo tại thời điểm giới thiệu.
        """,
    )

    assert result.category == DocumentCategory.SUBDIVISION_INFO


def test_camel_case_filename_is_classified_without_body_keywords():
    result = classify_document(
        "HaiAu_VHOP_ThongTinDuAn_Full.pdf",
        "Nội dung mô tả vị trí và tiện ích.",
    )

    assert result.category == DocumentCategory.SUBDIVISION_INFO
    assert "tên file" in result.reason
    assert result.requires_admin_review is True


def test_subdivision_metadata_drops_generic_scope_noise():
    result = classify_document(
        "Thong_tin_du_an.pdf",
        """
        Phân khu thấp tầng - Vinhomes Ocean Park 1
        Phân khu: Hải Âu
        Phân khu cao tầng và thấp tầng
        Phân khu | Vinhomes Ocean Park |
        """,
        parent_project_names=["Vinhomes Ocean Park", "Ocean Park 1"],
    )

    assert result.subdivision_names == ["Hai Au"]


def test_prime_minister_is_not_reduced_to_government_issuer():
    result = classify_document(
        "Quyet_dinh_123_2026_QD_TTg.pdf",
        """
        QUYẾT ĐỊNH 123/2026/QĐ-TTG
        CỦA THỦ TƯỚNG CHÍNH PHỦ
        """,
    )

    assert result.legal_issuer == "Thủ tướng Chính phủ"


def test_issue_date_uses_label_instead_of_first_unrelated_date():
    result = classify_document(
        "Bang_gia_The_Zurich_v2.pdf",
        """
        BẢNG GIÁ THE ZURICH
        Thời hạn bảo hành một số hạng mục đến 31/01/2028.
        Phiên bản | V2
        Áp dụng tháng 8 năm 2026
        Ngày ban hành | 15/08/2026
        Áp dụng từ 15/08/2026 đến 31/08/2026
        """,
    )

    assert result.version_label == "V2"
    assert result.applicable_period == "08/2026"
    assert result.issued_date == date(2026, 8, 15)
    assert result.effective_date == date(2026, 8, 15)
    assert result.expiry_date == date(2026, 8, 31)


def test_sales_round_is_kept_as_a_meaningful_applicable_period():
    result = classify_document(
        "Bang gia The Beverly dot 2.docx",
        """
        BẢNG GIÁ BÁN CĂN HỘ
        Đợt mở bán: Đợt 2
        Áp dụng từ 01/09/2026 đến 30/09/2026
        """,
    )

    assert result.category == DocumentCategory.PRICE_LIST
    assert result.applicable_period == "Đợt 2"


def test_explicit_sales_round_precedes_a_later_month_mention():
    result = classify_document(
        "Bang_gia_The_Beverly.pdf",
        """
        BẢNG GIÁ BÁN CĂN HỘ
        Đợt áp dụng | Đợt 2
        Lịch bàn giao dự kiến trong tháng 12/2026.
        """,
    )

    assert result.applicable_period == "Đợt 2"
