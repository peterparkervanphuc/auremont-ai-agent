"""Retrieval over Qdrant, filtered by each document's RBAC label.

This is the R in RAG: find the handful of document passages most relevant to the question
to ground the Generate step, instead of stuffing the whole corpus into the prompt.

Serves **static** ingested data only (price lists, policies, amenities). Unit inventory
changes constantly and is therefore never ingested into Qdrant — questions needing the
real-time inventory table must go through `inventory_service.lookup_inventory()`. Routing
between the two belongs to `agent_pipeline`, not to this module.
"""

import logging
import re

from qdrant_client import models

from backend.core.config import settings
from backend.core.enums import DocumentVisibility
from backend.core.gemini_client import GeminiEmbeddingError, embed_query
from backend.core.qdrant_client import get_qdrant_client

logger = logging.getLogger(__name__)

# Over-fetch from Qdrant, then re-rank and trim back to top_k. Vector search is fast but
# coarse; re-ranking a wider set gives the genuinely right passage a chance to surface.
OVERFETCH_FACTOR = 4

# Weight of the keyword signal during re-ranking. Kept low because the vector score
# remains the primary signal.
IDENTIFIER_WEIGHT = 0.2

_TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)


class RetrievalError(RuntimeError):
    """The query could not be embedded, or Qdrant could not be queried."""


def retrieve(query: str, visibility: DocumentVisibility, project_id: str | None = None, top_k: int = 5) -> list[dict]:
    """Return retrieved chunks: [{"document_id": int, "title": str, "content": str, "score": float}, ...].

    `visibility` is **the asker's clearance level**, not a label to match exactly:
    INTERNAL (Sale/Admin) can read both internal and public documents, PUBLIC can read
    only public ones. Matching exactly would mean a Sale never sees PUBLIC documents —
    absurd, since those are precisely the ones they are allowed to send to customers.

    Returns `[]` when nothing has been ingested yet (the collection does not exist) — the
    Sale then sees the "Chưa có dữ liệu dự án" empty state rather than a system error.

    Raises `RetrievalError` when Qdrant or Gemini genuinely fails.
    """
    if not query.strip() or top_k <= 0:
        return []

    try:
        query_vector = embed_query(query)
    except GeminiEmbeddingError as exc:
        logger.exception(
            "Embedding the query failed.",
            extra={"event": "retrieval.embed.failed", "project_id": project_id},
        )
        raise RetrievalError("Could not embed the query.") from exc

    conditions: list[models.Condition] = [
        _visibility_condition(visibility),
        models.FieldCondition(
            key="review_status",
            match=models.MatchValue(value="approved"),
        ),
        models.FieldCondition(
            key="is_current",
            match=models.MatchValue(value=True),
        ),
    ]
    if project_id:
        conditions.append(models.FieldCondition(key="project_id", match=models.MatchValue(value=project_id)))

    client = get_qdrant_client()
    try:
        # If nobody has uploaded a document yet the collection does not exist. That is a
        # normal state right after deployment, not a fault.
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
        # Most important handoff point: the RetrievalError raised here is caught and
        # entirely swallowed by agent_pipeline._retrieve. This log line is the ONLY
        # record that Qdrant genuinely failed.
        logger.exception(
            "Qdrant query failed.",
            extra={
                "event": "retrieval.qdrant.failed",
                "project_id": project_id,
                "collection": settings.qdrant_collection,
            },
        )
        raise RetrievalError("Could not query Qdrant.") from exc

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
                # page travels along so the Generate step can cite down to a page number.
                "page": payload.get("page"),
                # Qdrant cosine lives in [-1, 1]; rescale to [0, 1] to compare easily
                # against verifier_threshold_sale and to read well on the Admin dashboard.
                "score": (point.score + 1.0) / 2.0,
            }
        )

    return _rerank(query, hits)[:top_k]


def _visibility_condition(visibility: DocumentVisibility) -> models.Condition:
    """The second RBAC layer: guarding the route alone is not enough.

    Without filtering here, INTERNAL documents would still reach the context and the LLM
    would read internal content out to a customer, all while the route itself looked
    perfectly "safe".
    """
    if visibility == DocumentVisibility.PUBLIC:
        allowed = [DocumentVisibility.PUBLIC.value]
    else:
        allowed = [DocumentVisibility.INTERNAL.value, DocumentVisibility.PUBLIC.value]

    return models.FieldCondition(key="visibility", match=models.MatchAny(any=allowed))


def _identifiers(text: str) -> set[str]:
    """Tokens containing a digit: '2PN', 'OP3', '2024', 'Q1'.

    Embeddings capture meaning well but blur exactly these codes — '2PN' and '3PN' sit
    almost on top of each other in vector space despite being entirely different unit
    types. This is the one signal worth rescuing with keyword matching.
    """
    return {token.lower() for token in _TOKEN_PATTERN.findall(text) if any(c.isdigit() for c in token)}


def _rerank(query: str, hits: list[dict]) -> list[dict]:
    """Re-order by vector score, boosting passages that match codes from the question.

    Deliberately lightweight and dependency-free. For higher quality, swap this function
    for a cross-encoder (sentence-transformers) or Cohere Rerank — the signature stays.
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
