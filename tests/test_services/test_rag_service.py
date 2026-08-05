from types import SimpleNamespace

import pytest
from qdrant_client import models

from backend.core.config import settings
from backend.core.enums import DocumentVisibility
from backend.core.gemini_client import GeminiEmbeddingError
from backend.services import rag_service


class FakeQdrantClient:
    """Ghi lại tham số truy vấn để test soi được filter, limit, collection."""

    def __init__(self, *, points=None, collection_exists: bool = True):
        self.points = points or []
        self.exists = collection_exists
        self.query_calls = []

    def collection_exists(self, collection_name: str) -> bool:
        return self.exists

    def query_points(self, **kwargs):
        self.query_calls.append(kwargs)
        return SimpleNamespace(points=self.points)


def _point(content: str, *, score: float, document_id: int = 1, title: str = "bang-gia.pdf", page: int | None = 1):
    return SimpleNamespace(
        score=score,
        payload={
            "document_id": document_id,
            "title": title,
            "page": page,
            "content": content,
            "visibility": "internal",
        },
    )


@pytest.fixture
def qdrant(monkeypatch):
    fake_client = FakeQdrantClient()
    monkeypatch.setattr(rag_service, "get_qdrant_client", lambda: fake_client)
    monkeypatch.setattr(rag_service, "embed_query", lambda query: [0.1, 0.2, 0.3])
    monkeypatch.setattr(settings, "qdrant_collection", "test_documents")
    return fake_client


def _conditions(call) -> list:
    return call["query_filter"].must


def _visibility_values(call) -> list[str]:
    for condition in _conditions(call):
        if condition.key == "visibility":
            return list(condition.match.any)
    raise AssertionError("Không có filter visibility")


# --- Filter RBAC --------------------------------------------------------------------


def test_internal_clearance_sees_internal_and_public(qdrant):
    """Sale/Admin đọc được cả hai loại — khớp chính xác sẽ chặn nhầm tài liệu PUBLIC."""
    rag_service.retrieve("giá căn hộ", DocumentVisibility.INTERNAL)

    assert sorted(_visibility_values(qdrant.query_calls[0])) == ["internal", "public"]


def test_public_clearance_sees_only_public(qdrant):
    rag_service.retrieve("giá căn hộ", DocumentVisibility.PUBLIC)

    assert _visibility_values(qdrant.query_calls[0]) == ["public"]


def test_accepts_plain_string_visibility(qdrant):
    """DocumentVisibility là StrEnum nên caller truyền chuỗi thô vẫn phải đúng."""
    rag_service.retrieve("giá căn hộ", "public")

    assert _visibility_values(qdrant.query_calls[0]) == ["public"]


def test_project_id_adds_filter(qdrant):
    rag_service.retrieve("giá căn hộ", DocumentVisibility.INTERNAL, project_id="ocean-park-3")

    keys = [condition.key for condition in _conditions(qdrant.query_calls[0])]
    assert "project_id" in keys


def test_project_id_omitted_when_not_given(qdrant):
    rag_service.retrieve("giá căn hộ", DocumentVisibility.INTERNAL)

    keys = [condition.key for condition in _conditions(qdrant.query_calls[0])]
    assert keys == ["visibility"]


# --- Truy vấn ------------------------------------------------------------------------


def test_overfetches_before_reranking(qdrant):
    """Phải lấy dư rồi mới cắt, nếu không re-rank chỉ xáo lại đúng tập đã bị cắt."""
    rag_service.retrieve("giá căn hộ", DocumentVisibility.INTERNAL, top_k=5)

    call = qdrant.query_calls[0]
    assert call["limit"] == 5 * rag_service.OVERFETCH_FACTOR
    assert call["collection_name"] == "test_documents"
    assert call["with_payload"] is True
    assert call["query"] == [0.1, 0.2, 0.3]


def test_returns_expected_shape_and_normalized_score(qdrant):
    """Cosine [-1, 1] của Qdrant được đưa về [0, 1]."""
    qdrant.points = [_point("Giá căn hộ tham khảo.", score=1.0, document_id=7, title="bang-gia.pdf", page=3)]

    result = rag_service.retrieve("giá căn hộ", DocumentVisibility.INTERNAL)

    assert result == [
        {
            "document_id": 7,
            "title": "bang-gia.pdf",
            "content": "Giá căn hộ tham khảo.",
            "page": 3,
            "score": 1.0,
        }
    ]


def test_truncates_to_top_k(qdrant):
    qdrant.points = [_point(f"noi dung {i}", score=0.9) for i in range(12)]

    assert len(rag_service.retrieve("giá căn hộ", DocumentVisibility.INTERNAL, top_k=3)) == 3


def test_skips_points_without_content(qdrant):
    qdrant.points = [
        _point("có nội dung", score=0.9),
        SimpleNamespace(score=0.9, payload={"document_id": 2, "title": "x.pdf", "content": ""}),
        SimpleNamespace(score=0.9, payload=None),
    ]

    result = rag_service.retrieve("giá căn hộ", DocumentVisibility.INTERNAL)

    assert len(result) == 1


# --- Re-rank -------------------------------------------------------------------------


def test_identifier_match_outranks_higher_vector_score(qdrant):
    """'2PN' và '3PN' gần như trùng vector; từ khoá là thứ duy nhất tách được hai loại căn."""
    qdrant.points = [
        _point("Căn 3PN diện tích lớn, giá 5.2 tỷ.", score=0.90, document_id=1),
        _point("Căn 2PN giá 3.6 tỷ.", score=0.86, document_id=2),
    ]

    result = rag_service.retrieve("Giá căn 2PN?", DocumentVisibility.INTERNAL)

    assert result[0]["document_id"] == 2


def test_pure_vector_order_when_query_has_no_identifier(qdrant):
    """Câu hỏi không có mã nào thì không bịa ra tín hiệu từ khoá."""
    qdrant.points = [
        _point("Chính sách thanh toán.", score=0.60, document_id=1),
        _point("Tiện ích nội khu.", score=0.90, document_id=2),
    ]

    result = rag_service.retrieve("tiện ích thế nào", DocumentVisibility.INTERNAL)

    assert [hit["document_id"] for hit in result] == [2, 1]


# --- Trạng thái rỗng và lỗi ----------------------------------------------------------


def test_missing_collection_returns_empty_list(qdrant):
    """Chưa ai upload tài liệu — Empty State, không phải lỗi hệ thống."""
    qdrant.exists = False

    assert rag_service.retrieve("giá căn hộ", DocumentVisibility.INTERNAL) == []
    assert qdrant.query_calls == []


def test_blank_query_returns_empty_without_calling_qdrant(qdrant):
    assert rag_service.retrieve("   ", DocumentVisibility.INTERNAL) == []
    assert qdrant.query_calls == []


def test_non_positive_top_k_returns_empty(qdrant):
    assert rag_service.retrieve("giá căn hộ", DocumentVisibility.INTERNAL, top_k=0) == []
    assert qdrant.query_calls == []


def test_embedding_failure_becomes_retrieval_error(qdrant, monkeypatch):
    def _boom(query):
        raise GeminiEmbeddingError("Gemini down")

    monkeypatch.setattr(rag_service, "embed_query", _boom)

    with pytest.raises(rag_service.RetrievalError, match="Không embed được"):
        rag_service.retrieve("giá căn hộ", DocumentVisibility.INTERNAL)


def test_qdrant_failure_becomes_retrieval_error(qdrant, monkeypatch):
    def _boom(**kwargs):
        raise ConnectionError("Qdrant unreachable")

    monkeypatch.setattr(qdrant, "query_points", _boom)

    with pytest.raises(rag_service.RetrievalError, match="Không truy vấn được Qdrant"):
        rag_service.retrieve("giá căn hộ", DocumentVisibility.INTERNAL)


def test_filter_is_a_qdrant_filter_object(qdrant):
    """Giữ đúng kiểu của qdrant-client để không vỡ khi nâng version."""
    rag_service.retrieve("giá căn hộ", DocumentVisibility.INTERNAL)

    assert isinstance(qdrant.query_calls[0]["query_filter"], models.Filter)


# --- Integration: engine Qdrant thật, chạy in-memory ---------------------------------
#
# FakeQdrantClient ở trên chỉ chứng minh ta GỌI đúng tham số, không chứng minh Qdrant
# HIỂU chúng — filter sai cấu trúc hay dùng sai API query_points vẫn pass hết. Local
# mode chạy đúng engine truy vấn nên bịt được khoảng trống đó mà không cần Docker.


@pytest.fixture
def live_qdrant(monkeypatch):
    from qdrant_client import QdrantClient

    from backend.services import vector_store_service

    client = QdrantClient(":memory:")
    monkeypatch.setattr(rag_service, "get_qdrant_client", lambda: client)
    monkeypatch.setattr(vector_store_service, "get_qdrant_client", lambda: client)
    monkeypatch.setattr(settings, "qdrant_collection", "itest_documents")
    monkeypatch.setattr(settings, "embedding_dimensions", 3)
    monkeypatch.setattr(rag_service, "embed_query", lambda query: [1.0, 0.0, 0.0])

    from backend.services.chunking_service import DocumentChunk

    vector_store_service.index_document_chunks(
        document_id=1,
        title="bang-gia.pdf",
        project_id="ocean-park-3",
        visibility="internal",
        chunks=[DocumentChunk(index=0, text="Căn 2PN giá 3.6 tỷ.", page=2)],
        vectors=[[1.0, 0.0, 0.0]],
    )
    vector_store_service.index_document_chunks(
        document_id=2,
        title="cong-khai.pdf",
        project_id="ocean-park-3",
        visibility="public",
        chunks=[DocumentChunk(index=0, text="Tiện ích nội khu.", page=1)],
        vectors=[[0.9, 0.1, 0.0]],
    )
    return client


def test_live_internal_clearance_reads_both_tiers(live_qdrant):
    result = rag_service.retrieve("Giá căn 2PN?", DocumentVisibility.INTERNAL)

    assert sorted(hit["document_id"] for hit in result) == [1, 2]


def test_live_public_clearance_cannot_read_internal_document(live_qdrant):
    """Lớp RBAC thứ hai chạy thật: tài liệu nội bộ không được lọt vào context."""
    result = rag_service.retrieve("Giá căn 2PN?", DocumentVisibility.PUBLIC)

    assert [hit["document_id"] for hit in result] == [2]


def test_live_project_filter_excludes_other_projects(live_qdrant):
    assert rag_service.retrieve("Giá căn 2PN?", DocumentVisibility.INTERNAL, project_id="khong-ton-tai") == []


def test_live_carries_page_for_citation(live_qdrant):
    """Không có page thì bước Generate không trích nguồn tới số trang được."""
    result = rag_service.retrieve("Giá căn 2PN?", DocumentVisibility.INTERNAL, project_id="ocean-park-3")

    assert result[0]["page"] == 2
    assert result[0]["title"] == "bang-gia.pdf"
