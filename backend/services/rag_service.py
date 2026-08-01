"""Retrieval over the Qdrant vector store, filtered by RBAC visibility (CLAUDE.md §6.1 step 2).

TODO:
- Embed the incoming query (same embedding model used at ingestion time).
- Query Qdrant with a payload filter on `visibility` (INTERNAL+PUBLIC for Sale, PUBLIC-only for Chatbot)
  and optionally `project_id`.
- Apply a re-ranker over the top-k hits before returning.
- When the question is classified as needing unit availability, query
  `backend.repositories.inventory_unit` (MySQL `inventory_units` table) directly instead of Qdrant —
  CLAUDE.md §6.1 step 2 explicitly replaces the old real-time inventory API with a direct DB query.
"""

from backend.core.enums import DocumentVisibility


def retrieve(query: str, visibility: DocumentVisibility, project_id: str | None = None, top_k: int = 5) -> list[dict]:
    """Return retrieved chunks: [{"document_id": int, "title": str, "content": str, "score": float}, ...]."""
    raise NotImplementedError("TODO: implement Qdrant retrieval + re-ranking")
