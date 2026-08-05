"""Retrieval trên Qdrant, lọc theo nhãn RBAC của tài liệu.

Đây là chữ R trong RAG: tìm vài đoạn tài liệu liên quan nhất tới câu hỏi để làm căn cứ
cho bước Generate, thay vì nhét cả kho tài liệu vào prompt.

Chỉ phục vụ dữ liệu **tĩnh** đã ingest (bảng giá, chính sách, tiện ích). Tồn kho căn đổi
liên tục nên không ingest vào Qdrant — câu hỏi cần Bảng hàng real-time phải đi nhánh
`inventory_service.lookup_inventory()`. Việc phân luồng đó thuộc về `agent_pipeline`,
không phải hàm này.
"""

import re

from qdrant_client import models

from backend.core.config import settings
from backend.core.enums import DocumentVisibility
from backend.core.gemini_client import GeminiEmbeddingError, embed_query
from backend.core.qdrant_client import get_qdrant_client

# Lấy dư kết quả từ Qdrant rồi mới re-rank và cắt về top_k. Vector search nhanh nhưng
# thô; xếp lại trên một tập rộng hơn thì đoạn đúng mới có cơ hội trồi lên.
OVERFETCH_FACTOR = 4

# Trọng số của tín hiệu từ khoá khi re-rank. Để thấp vì điểm vector vẫn là chính.
IDENTIFIER_WEIGHT = 0.2

_TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)


class RetrievalError(RuntimeError):
    """Không embed được câu hỏi hoặc không truy vấn được Qdrant."""


def retrieve(query: str, visibility: DocumentVisibility, project_id: str | None = None, top_k: int = 5) -> list[dict]:
    """Return retrieved chunks: [{"document_id": int, "title": str, "content": str, "score": float}, ...].

    `visibility` là **mức quyền của người hỏi**, không phải nhãn cần khớp chính xác:
    INTERNAL (Sale/Admin) đọc được cả tài liệu nội bộ lẫn công khai, PUBLIC chỉ đọc được
    tài liệu công khai. Khớp chính xác sẽ khiến Sale không bao giờ thấy tài liệu PUBLIC —
    vô lý, vì đó chính là tài liệu họ được phép gửi cho khách.

    Trả về `[]` khi chưa có tài liệu nào được ingest (collection chưa tồn tại) — Sale sẽ
    thấy Empty State "Chưa có dữ liệu dự án" chứ không phải một lỗi hệ thống.

    Raise `RetrievalError` khi Qdrant hoặc Gemini thật sự hỏng.
    """
    if not query.strip() or top_k <= 0:
        return []

    try:
        query_vector = embed_query(query)
    except GeminiEmbeddingError as exc:
        raise RetrievalError("Không embed được câu hỏi.") from exc

    conditions: list[models.Condition] = [_visibility_condition(visibility)]
    if project_id:
        conditions.append(models.FieldCondition(key="project_id", match=models.MatchValue(value=project_id)))

    client = get_qdrant_client()
    try:
        # Chưa ai upload tài liệu thì collection chưa được tạo. Đây là trạng thái bình
        # thường lúc mới deploy, không phải sự cố.
        if not client.collection_exists(settings.qdrant_collection):
            return []

        response = client.query_points(
            collection_name=settings.qdrant_collection,
            query=query_vector,
            query_filter=models.Filter(must=conditions),
            limit=top_k * OVERFETCH_FACTOR,
            with_payload=True,
        )
    except Exception as exc:
        raise RetrievalError("Không truy vấn được Qdrant.") from exc

    hits = []
    for point in response.points:
        payload = point.payload or {}
        content = payload.get("content") or ""
        if not content:
            continue
        hits.append(
            {
                "document_id": payload.get("document_id"),
                "title": payload.get("title") or "",
                "content": content,
                # page đi kèm để bước Generate trích nguồn được tới số trang.
                "page": payload.get("page"),
                # Cosine của Qdrant nằm trong [-1, 1]; đưa về [0, 1] cho dễ so với
                # ngưỡng verifier_threshold_sale và dễ đọc trên Admin dashboard.
                "score": (point.score + 1.0) / 2.0,
            }
        )

    return _rerank(query, hits)[:top_k]


def _visibility_condition(visibility: DocumentVisibility) -> models.Condition:
    """Lớp RBAC thứ hai: chặn ở route thôi chưa đủ.

    Nếu không lọc ở đây, tài liệu INTERNAL vẫn lọt vào context và LLM sẽ đọc nội dung
    nội bộ cho khách nghe, trong khi route vẫn "an toàn".
    """
    if visibility == DocumentVisibility.PUBLIC:
        allowed = [DocumentVisibility.PUBLIC.value]
    else:
        allowed = [DocumentVisibility.INTERNAL.value, DocumentVisibility.PUBLIC.value]

    return models.FieldCondition(key="visibility", match=models.MatchAny(any=allowed))


def _identifiers(text: str) -> set[str]:
    """Token có chứa chữ số: '2PN', 'OP3', '2024', 'Q1'.

    Embedding rất giỏi bắt ngữ nghĩa nhưng lại làm nhoè đúng những mã này — '2PN' và
    '3PN' gần như trùng vector dù là hai loại căn khác hẳn nhau. Đây là tín hiệu duy
    nhất cần vớt lại bằng từ khoá.
    """
    return {token.lower() for token in _TOKEN_PATTERN.findall(text) if any(c.isdigit() for c in token)}


def _rerank(query: str, hits: list[dict]) -> list[dict]:
    """Xếp lại theo điểm vector, cộng thêm điểm cho đoạn khớp mã trong câu hỏi.

    Cố tình giữ nhẹ và không thêm dependency. Muốn chất lượng cao hơn thì thay hàm này
    bằng cross-encoder (sentence-transformers) hoặc Cohere Rerank — chữ ký giữ nguyên.
    """
    wanted = _identifiers(query)
    if not wanted:
        return sorted(hits, key=lambda hit: hit["score"], reverse=True)

    for hit in hits:
        overlap = len(wanted & _identifiers(hit["content"])) / len(wanted)
        hit["score"] = round(
            (1 - IDENTIFIER_WEIGHT) * hit["score"] + IDENTIFIER_WEIGHT * overlap,
            6,
        )

    return sorted(hits, key=lambda hit: hit["score"], reverse=True)
