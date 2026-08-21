"""Retrieval over Qdrant, filtered by each document's RBAC label.

This is the R in RAG: find the handful of document passages most relevant to the question
to ground the Generate step, instead of stuffing the whole corpus into the prompt.

Retrieval is hybrid when `hybrid_search_enabled` is on: a dense Gemini vector and a BM25
sparse vector search the same points independently, and Qdrant fuses the two rankings
with Reciprocal Rank Fusion. The channels fail in opposite directions, which is the whole
point — dense understands a paraphrase but blurs "2PN" into "3PN", BM25 cannot read
meaning but matches a unit code exactly. RRF ranks by position rather than score, so
neither channel's scale has to be reconciled with the other's.

An optional third stage narrows the over-fetched candidates further when `rerank_enabled`
is on: Cohere Rerank v3.5, a cross-encoder that scores query and passage together rather
than comparing independent embeddings. It catches relevance that neither retrieval channel
can — a passage can rank high on cosine or token overlap and still not answer the question.
Falls back to the cheaper identifier-overlap heuristic whenever reranking is disabled or
the API call fails, so a Cohere outage degrades quality rather than availability.

Serves **static** ingested data only (price lists, policies, amenities). Unit inventory
changes constantly and is therefore never ingested into Qdrant — questions needing the
real-time inventory table must go through `inventory_service.lookup_inventory()`. Routing
between the two belongs to `agent_pipeline`, not to this module.
"""

import logging
import re

from qdrant_client import models

from backend.core.cohere_client import CohereRerankError
from backend.core.cohere_client import rerank as cohere_rerank
from backend.core.config import settings
from backend.core.enums import DocumentVisibility
from backend.core.gemini_client import GeminiEmbeddingError, embed_query
from backend.core.qdrant_client import get_qdrant_client
from backend.core.sparse_embedding import SparseEmbeddingError, embed_query_sparse
from backend.services.vector_store_service import DENSE_VECTOR, SPARSE_VECTOR

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

    sparse_query_vector = None
    if settings.hybrid_search_enabled:
        try:
            sparse_query_vector = embed_query_sparse(query)
        except SparseEmbeddingError:
            # Degrade rather than fail: the keyword channel sharpens retrieval, but the
            # dense channel alone still answers the question. A Sale waiting in front of
            # a customer must not lose their answer to a model-cache problem.
            logger.warning(
                "BM25 query embedding failed; retrieving with the dense channel only.",
                exc_info=True,
                extra={"event": "retrieval.sparse_embed.failed", "project_id": project_id},
            )

    # No review_status condition: an uploaded document answers immediately. Everything that
    # must stay out of retrieval for correctness — a duplicate, a document flagged as
    # contradicting another, one whose legal status expired — has `is_current` cleared
    # instead, so that single condition carries all of it (see ingestion_service, where
    # is_current is computed from exactly those three).
    conditions: list[models.Condition] = [
        _visibility_condition(visibility),
        models.FieldCondition(
            key="is_current",
            match=models.MatchValue(value=True),
        ),
    ]
    if project_id:
        conditions.append(models.FieldCondition(key="project_id", match=models.MatchValue(value=project_id)))

    query_filter = models.Filter(must=conditions)
    candidate_limit = top_k * OVERFETCH_FACTOR

    client = get_qdrant_client()
    try:
        # If nobody has uploaded a document yet the collection does not exist. That is a
        # normal state right after deployment, not a fault.
        if not client.collection_exists(settings.qdrant_collection):
            return []

        if sparse_query_vector is not None:
            response = client.query_points(
                collection_name=settings.qdrant_collection,
                # The filter is repeated on each branch on purpose. RRF ranks whatever
                # each branch returns, so a branch that fetched documents the asker may
                # not read would spend its ranking slots on them and push readable ones
                # out before the outer filter ever removes them.
                prefetch=[
                    models.Prefetch(
                        query=query_vector,
                        using=DENSE_VECTOR,
                        filter=query_filter,
                        limit=candidate_limit,
                    ),
                    models.Prefetch(
                        query=sparse_query_vector,
                        using=SPARSE_VECTOR,
                        filter=query_filter,
                        limit=candidate_limit,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                query_filter=query_filter,
                limit=candidate_limit,
                with_payload=True,
            )
        else:
            response = client.query_points(
                collection_name=settings.qdrant_collection,
                query=query_vector,
                # Required now that the collection holds named vectors: without it
                # Qdrant cannot tell which vector to search.
                using=DENSE_VECTOR,
                query_filter=query_filter,
                limit=candidate_limit,
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

    # RRF scores are sums of 1/(k + rank) across the two channels, not similarities, so
    # the cosine rescale below would be meaningless on them. Only the ordering matters
    # downstream — nothing compares this number against a threshold — so fused scores are
    # passed through untouched.
    fused = sparse_query_vector is not None

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
                # Y position (PDF points from the page's top) for scrolling a citation's
                # PDF viewer straight to this chunk — see chunking_service.py and
                # CitationList.tsx's withPageAnchor. None for DOCX or an older chunk
                # indexed before this field existed.
                "y_position": payload.get("y_position"),
                # project_id travels along so a reply built from an unscoped, cross-project
                # search (no project_id filter above) can tell "these docs actually agree on
                # one project" apart from "retrieval grabbed unrelated projects" — see
                # agent_pipeline._generate's citation filtering.
                "project_id": payload.get("project_id"),
                # Qdrant cosine lives in [-1, 1]; rescale to [0, 1] so it reads well on
                # the Admin dashboard. A fused (hybrid) score is already normalised.
                "score": point.score if fused else (point.score + 1.0) / 2.0,
            }
        )

    return _rerank(query, hits, fused=fused)[:top_k]


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


def _rerank(query: str, hits: list[dict], fused: bool = False) -> list[dict]:
    """Re-order candidates, preferring the Cohere cross-encoder when it is enabled.

    The cross-encoder scores query+passage jointly, so it replaces both the RRF pass-
    through and the identifier heuristic below when available — it is strictly more
    accurate than either. `_rerank_cohere` returns None on any failure (missing key,
    network error, empty response), and this function falls back to the previous
    behaviour rather than letting a Cohere outage take retrieval down with it.
    """
    if settings.rerank_enabled:
        reranked = _rerank_cohere(query, hits)
        if reranked is not None:
            return reranked

    return _rerank_heuristic(query, hits, fused=fused)


def _rerank_cohere(query: str, hits: list[dict]) -> list[dict] | None:
    """Score every candidate with Cohere Rerank v3.5; None means "fall back"."""
    if not hits:
        return hits

    try:
        scored = cohere_rerank(query, [hit["content"] for hit in hits])
    except CohereRerankError:
        logger.warning(
            "Cohere rerank failed; falling back to the identifier heuristic.",
            exc_info=True,
            extra={"event": "retrieval.rerank.failed", "candidate_count": len(hits)},
        )
        return None

    reordered = []
    for index, relevance_score in scored:
        hit = hits[index]
        hit["score"] = round(relevance_score, 6)
        reordered.append(hit)
    return reordered


def _rerank_heuristic(query: str, hits: list[dict], fused: bool = False) -> list[dict]:
    """Re-order by vector score, boosting passages that match codes from the question.

    Skipped entirely once results are fused, for two reasons. BM25 already matched those
    codes properly — this identifier boost is a crude stand-in for the keyword channel
    that now exists for real. And the arithmetic no longer holds: it mixes a score with a
    0-1 overlap ratio, which assumes the score is itself roughly 0-1. RRF scores are
    around 1/60 per channel, so the overlap term would swamp them and re-sort the results
    by "mentions a number" alone, discarding the fusion ranking.

    Deliberately lightweight and dependency-free — the fallback for when Cohere Rerank
    (`_rerank_cohere` above) is disabled or unavailable.
    """
    if fused:
        return hits

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
