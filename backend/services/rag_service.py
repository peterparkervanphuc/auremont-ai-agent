"""Retrieval trên Qdrant, lọc theo nhãn RBAC của tài liệu.

TODO:
- Embed the incoming query (same embedding model used at ingestion time).
- Query Qdrant with a payload filter on `visibility` and optionally `project_id`.
- Apply a re-ranker over the top-k hits before returning.
- When the question is classified as needing unit availability (Bảng hàng real-time), call
  `backend.services.inventory_service.lookup_inventory()` (Tool/Function Calling to the company's
  internal inventory API) instead of Qdrant — catch `InventoryApiError` and surface
  "Tạm thời không tra được tồn kho" rather than letting the pipeline fail silently.
"""

from backend.core.enums import DocumentVisibility


def retrieve(query: str, visibility: DocumentVisibility, project_id: str | None = None, top_k: int = 5) -> list[dict]:
    """Return retrieved chunks: [{"document_id": int, "title": str, "content": str, "score": float}, ...]."""
    raise NotImplementedError("TODO: implement Qdrant retrieval + re-ranking")
