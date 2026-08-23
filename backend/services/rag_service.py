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
import math
import re
from collections.abc import Iterable, Sequence
from typing import Any

from qdrant_client import models

from backend.core import tracing
from backend.core.cohere_client import CohereRerankError
from backend.core.cohere_client import rerank as cohere_rerank
from backend.core.config import settings
from backend.core.enums import DocumentCategory, DocumentReviewStatus, DocumentVisibility
from backend.core.gemini_client import GeminiEmbeddingError, embed_query
from backend.core.qdrant_client import get_qdrant_client
from backend.core.sparse_embedding import SparseEmbeddingError, embed_query_sparse
from backend.services.vector_store_service import DENSE_VECTOR, SPARSE_VECTOR
from backend.utils.text import strip_diacritics

logger = logging.getLogger(__name__)

# Over-fetch from Qdrant, then re-rank and trim back to top_k. Vector search is fast but
# coarse; re-ranking a wider set gives the genuinely right passage a chance to surface.
OVERFETCH_FACTOR = 4

# Weight of the keyword signal during re-ranking. Kept low because the vector score
# remains the primary signal.
IDENTIFIER_WEIGHT = 0.2

_TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)
# Preserve separators inside business identifiers so ``2PN`` and ``2PN+1`` remain
# different constraints, as do a full unit code and any coincidentally shared component.
_STRONG_IDENTIFIER_PATTERN = re.compile(r"[^\W_]+(?:[-.][^\W_]+)*(?:\+[^\W_]*)?", re.UNICODE)
_BEDROOM_IDENTIFIER_PATTERN = re.compile(
    r"^(?P<count>\d+)(?:pn|br)(?P<plus>\+(?:1)?)?$",
    re.IGNORECASE,
)


class RetrievalError(RuntimeError):
    """The query could not be embedded, or Qdrant could not be queried."""


def _build_query_filter(
    *,
    visibility: DocumentVisibility,
    project_id: str | None,
    project_ids: Iterable[str] | None,
    excluded_project_ids: Iterable[str] | None,
) -> models.Filter:
    """Assemble every payload condition a retrieval must satisfy.

    Kept apart from the search itself because this is the RBAC boundary: the clearance,
    approval and currency conditions here are what stop an internal or retired document
    reaching an answer, independent of whatever the route allowed.
    """
    conditions: list[models.Condition] = [
        _visibility_condition(visibility),
        models.FieldCondition(
            key="review_status",
            match=models.MatchValue(value=DocumentReviewStatus.APPROVED),
        ),
        models.FieldCondition(
            key="is_current",
            match=models.MatchValue(value=True),
        ),
    ]
    scoped_project_ids = list(
        dict.fromkeys(value for value in (project_ids or ([project_id] if project_id else [])) if value)
    )
    project_scope: list[models.Condition] | None = None
    if scoped_project_ids:
        # Project-scoped documents OR company/global documents. Uploading a general
        # buying guide without a project assignment must not make it disappear from every
        # project conversation, while documents assigned to another project remain out.
        project_match = (
            models.MatchValue(value=scoped_project_ids[0])
            if len(scoped_project_ids) == 1
            else models.MatchAny(any=scoped_project_ids)
        )
        project_scope = [
            models.FieldCondition(key="project_id", match=project_match),
            models.IsNullCondition(is_null=models.PayloadField(key="project_id")),
        ]

    excluded_ids = list(dict.fromkeys(project_id for project_id in excluded_project_ids or [] if project_id))
    # `other` means the classifier could not map the source to a supported knowledge-base
    # purpose. Keep this defense even if stale DB/Qdrant metadata accidentally marks such a
    # document approved and current.
    exclusions: list[models.Condition] = [
        models.FieldCondition(
            key="category",
            match=models.MatchValue(value=DocumentCategory.OTHER),
        )
    ]
    if excluded_ids:
        # Null/global documents do not match this condition and remain available.  Only
        # chunks assigned to a subdivision the customer explicitly rejected are removed.
        exclusions.append(
            models.FieldCondition(
                key="project_id",
                match=models.MatchAny(any=excluded_ids),
            )
        )

    query_filter = models.Filter(
        must=conditions,
        should=project_scope,
        must_not=exclusions,
    )
    return query_filter


def _points_to_hits(points: Iterable[Any], *, fused: bool) -> list[dict]:
    """Turn Qdrant points into the hit dicts the rest of the pipeline works with.

    `fused` selects the score scale: an RRF-fused score already lives in [0, 1], a raw
    cosine does not and is rescaled from [-1, 1].
    """
    hits: list[dict] = []
    for point in points:
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
    return hits


def retrieve(
    query: str,
    visibility: DocumentVisibility,
    project_id: str | None = None,
    top_k: int = 5,
    *,
    focus_query: str | None = None,
    project_ids: Iterable[str] | None = None,
    excluded_project_ids: Iterable[str] | None = None,
) -> list[dict]:
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

    # Defense in depth: ingestion also keeps pending suggestions at is_current=false, but
    # requiring approval here prevents a stale/corrupt vector payload with is_current=true
    # from grounding an answer before an Admin reviews a weak classification.
    query_filter = _build_query_filter(
        visibility=visibility,
        project_id=project_id,
        project_ids=project_ids,
        excluded_project_ids=excluded_project_ids,
    )
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

    hits = _points_to_hits(response.points, fused=fused)

    ranked = _rerank(query, hits, fused=fused)
    return _select_context(focus_query or query, ranked, top_k=top_k)


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
    if settings.rerank_enabled and settings.cohere_api_key:
        reranked = _rerank_cohere(query, hits)
        if reranked is not None:
            tracing.step("rerank", ranker="cohere", candidate_count=len(hits))
            return reranked

        # Recorded, not just logged. A Cohere Trial key allows 10 calls/minute, so under
        # any real concurrency this path is taken constantly — and the only outward sign
        # is that ranking quietly gets worse. Without this step the Admin trace shows a
        # perfectly normal run and nothing anywhere says the cross-encoder never ran.
        tracing.step("rerank", ranker="heuristic", candidate_count=len(hits), degraded=True)
        return _rerank_heuristic(query, hits, fused=fused)

    tracing.step("rerank", ranker="heuristic", candidate_count=len(hits), degraded=False)
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

    # Treat hosted output as untrusted tool data. A stale SDK/API response containing an
    # invalid or duplicate index must degrade to the local ranker, not select the wrong
    # passage or crash retrieval with IndexError.
    if not _valid_rerank_results(scored, candidate_count=len(hits)):
        logger.warning(
            "Cohere returned invalid rerank indexes; falling back to the identifier heuristic.",
            extra={"event": "retrieval.rerank.invalid", "candidate_count": len(hits)},
        )
        return None

    reordered = []
    for index, relevance_score in scored:
        hit = dict(hits[index])
        hit["score"] = round(relevance_score, 6)
        reordered.append(hit)
    return reordered


def _valid_rerank_results(scored: Sequence[tuple[int, float]], *, candidate_count: int) -> bool:
    """Cohere is asked to score every candidate, so require one valid index for each."""
    indexes = [index for index, _score in scored]
    return (
        len(indexes) == candidate_count
        and len(set(indexes)) == candidate_count
        and all(isinstance(index, int) and 0 <= index < candidate_count for index in indexes)
        and all(isinstance(score, int | float) and math.isfinite(score) for _index, score in scored)
    )


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


def _select_context(query: str, hits: list[dict], *, top_k: int) -> list[dict]:
    """Choose a compact, non-redundant context after all retrieval scoring.

    Ranking models are deliberately fuzzy, but identifiers are not: when the current
    question says ``2PN`` or ``OP3-CT1-0504``, a passage carrying that exact token must
    precede an otherwise semantic-near ``3PN`` passage. This final stable ordering applies
    to dense, RRF and hosted rerank results alike.

    The second pass removes near-duplicate overlap from the same document and enforces a
    total context budget. It never truncates a chunk (which could sever a table row or
    legal clause), and always keeps the best hit even when that one chunk exceeds budget.
    """
    if not hits or top_k <= 0:
        return []

    ordered = _prioritize_identifier_coverage(query, hits)
    selected: list[dict] = []
    selected_tokens: list[tuple[object, set[str]]] = []
    used_chars = 0
    duplicate_count = 0
    budget_count = 0

    for hit in ordered:
        content = str(hit.get("content") or "").strip()
        if not content:
            continue

        tokens = _content_tokens(content)
        document_id = hit.get("document_id")
        if document_id is not None and any(
            document_id == existing_document_id and _near_duplicate(tokens, existing_tokens)
            for existing_document_id, existing_tokens in selected_tokens
        ):
            duplicate_count += 1
            continue

        if selected and used_chars + len(content) > settings.rag_max_context_chars:
            budget_count += 1
            continue

        selected.append(hit)
        selected_tokens.append((document_id, tokens))
        used_chars += len(content)
        if len(selected) == top_k:
            break

    if duplicate_count or budget_count:
        logger.debug(
            "RAG context selection removed redundant or over-budget candidates.",
            extra={
                "event": "retrieval.context.selected",
                "candidate_count": len(hits),
                "selected_count": len(selected),
                "duplicate_count": duplicate_count,
                "budget_count": budget_count,
                "context_chars": used_chars,
            },
        )

    return selected


def _prioritize_identifier_coverage(query: str, hits: list[dict]) -> list[dict]:
    """Stable-sort strong exact identifiers ahead of fuzzy relevance scores.

    Pure numbers are deliberately excluded here: a year or budget is useful as a small
    heuristic signal, but must not make an unrelated paragraph outrank a semantically
    correct one. Product/unit codes such as ``2PN`` and ``OP3`` contain both letters and
    digits and are safe enough to act as hard ordering constraints.
    """
    wanted = _strong_identifiers(query)
    if not wanted:
        return hits

    return sorted(
        hits,
        key=lambda hit: len(wanted & _strong_identifiers(str(hit.get("content") or ""))) / len(wanted),
        reverse=True,
    )


def _strong_identifiers(text: str) -> set[str]:
    tokens = {_normalise_identifier(match.group(0)) for match in _STRONG_IDENTIFIER_PATTERN.finditer(text)}
    return {
        token
        for token in tokens
        if any(character.isalpha() for character in token) and any(character.isdigit() for character in token)
    }


def _normalise_identifier(token: str) -> str:
    """Collapse equivalent Vietnamese/English real-estate unit labels.

    The corpus commonly uses ``BR`` while users type ``PN``; ``2BR+`` and ``2PN+1``
    likewise name the same layout. This normalisation is intentionally narrow so an
    arbitrary product code is never rewritten by accident.
    """
    lowered = token.lower()
    bedroom = _BEDROOM_IDENTIFIER_PATTERN.fullmatch(lowered)
    if bedroom is None:
        return lowered
    plus = "+1" if bedroom.group("plus") else ""
    return f"{bedroom.group('count')}br{plus}"


def _content_tokens(text: str) -> set[str]:
    return set(_TOKEN_PATTERN.findall(strip_diacritics(text)))


def _near_duplicate(left: set[str], right: set[str]) -> bool:
    if left == right:
        return bool(left)
    # Very short passages share generic words too easily. Exact equality above still
    # catches duplicated headings and one-line facts without creating false positives.
    if min(len(left), len(right)) < 8:
        return False
    union = left | right
    return bool(union) and len(left & right) / len(union) >= settings.rag_duplicate_similarity_threshold
