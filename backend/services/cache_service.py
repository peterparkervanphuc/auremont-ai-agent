"""Semantic Cache — reuse answers for semantically identical questions, spending no LLM tokens.

Sales staff ask the same thing over and over in different wordings ("giá căn 2PN?",
"căn 2PN bao nhiêu tiền?"). A literal string cache misses all of those, so matching here
is done on the **question vector**: if cosine similarity against an already-answered
question is high enough, the stored answer is returned directly, skipping the entire
Retrieve → Generate → Verify chain.

The cache lives in its **own** Qdrant collection (`salesmate_qa_cache`), separate from the
document collection, so clearing the cache can never touch ingested document vectors.

The principle throughout this file: **if the cache breaks, fail silently**. It is a cost
optimisation, not a source of truth — letting it raise into the pipeline would turn a
trivial Qdrant hiccup into a total inability to answer, when the only real cost of
skipping it is a few extra tokens.
"""

import logging
import uuid
from dataclasses import dataclass, field

from qdrant_client import models

from backend.core.config import settings
from backend.core.gemini_client import embed_query
from backend.core.qdrant_client import get_qdrant_client

logger = logging.getLogger(__name__)

CACHE_COLLECTION = "salesmate_qa_cache"

# Deliberately high. Serving the answer to a merely "similar" question is far worse than
# spending a few more tokens: the Sale would read wrong figures without ever noticing.
CACHE_SIMILARITY_THRESHOLD = 0.95


@dataclass
class CachedAnswer:
    answer: str
    citations: list[dict]
    verifier_score: float
    # Cached alongside the answer so a cache hit still shows the photos the question
    # asked for. Defaulted because rows written before this field existed have no key.
    images: list[dict] = field(default_factory=list)


def lookup_cache(query: str, project_id: str | None = None) -> CachedAnswer | None:
    """Find a cached answer for an equivalent question. `None` means a cache miss."""
    if not query.strip():
        return None

    try:
        client = get_qdrant_client()
        if not client.collection_exists(CACHE_COLLECTION):
            return None

        response = client.query_points(
            collection_name=CACHE_COLLECTION,
            query=embed_query(query),
            query_filter=_project_filter(project_id),
            limit=1,
            with_payload=True,
        )
    except Exception:
        # Qdrant down or a Gemini embedding failure -> treat as a cache miss and let the
        # pipeline take the full path. Logged at WARNING rather than ERROR: the answer is
        # still correct, only more expensive. But it must be logged — a permanently dead
        # cache burns tokens on every single request with no other outward symptom.
        logger.warning(
            "Cache lookup failed; treating as a miss.",
            exc_info=True,
            extra={"event": "cache.lookup.failed", "project_id": project_id},
        )
        return None

    if not response.points:
        return None

    hit = response.points[0]
    # Qdrant returns cosine in [-1, 1]; rescale to [0, 1] to share one scale with
    # CACHE_SIMILARITY_THRESHOLD and with rag_service scores.
    similarity = (hit.score + 1.0) / 2.0
    if similarity < CACHE_SIMILARITY_THRESHOLD:
        return None

    payload = hit.payload or {}
    answer = payload.get("answer")
    if not answer:
        return None

    return CachedAnswer(
        answer=answer,
        citations=payload.get("citations") or [],
        verifier_score=payload.get("verifier_score") or 0.0,
        images=payload.get("images") or [],
    )


def store_cache(
    query: str,
    answer: str,
    citations: list[dict],
    verifier_score: float,
    project_id: str | None = None,
    images: list[dict] | None = None,
) -> None:
    """Store a (question, answer) pair that has met the quality bar.

    Callers are responsible for **not** calling this for answers with `requires_hitl` or
    below the verifier threshold — see `agent_pipeline`. Rationale: price/commitment
    answers must go through Verify + RiskCheck every time so the Sale always sees the
    HITL card, and caching a low-scoring answer merely replicates a bad answer.
    """
    if not query.strip() or not answer.strip():
        return

    try:
        _ensure_cache_collection()

        get_qdrant_client().upsert(
            collection_name=CACHE_COLLECTION,
            points=[
                models.PointStruct(
                    # ID derived from question + project: re-asking the exact same question
                    # overwrites the old row instead of bloating the cache with near-duplicates.
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"salesmate:qa:{project_id or ''}:{query.strip()}")),
                    vector=embed_query(query),
                    payload={
                        "query": query,
                        "answer": answer,
                        "citations": citations,
                        "images": images or [],
                        "verifier_score": verifier_score,
                        "project_id": project_id,
                    },
                )
            ],
        )
    except Exception:
        # A failed cache write has no bearing on the answer already being served.
        logger.warning(
            "Cache write failed; the answer already served is unaffected.",
            exc_info=True,
            extra={"event": "cache.store.failed", "project_id": project_id},
        )
        return


def _ensure_cache_collection() -> None:
    client = get_qdrant_client()
    if client.collection_exists(CACHE_COLLECTION):
        return

    client.create_collection(
        collection_name=CACHE_COLLECTION,
        vectors_config=models.VectorParams(
            size=settings.embedding_dimensions,
            distance=models.Distance.COSINE,
        ),
    )


def _project_filter(project_id: str | None) -> models.Filter | None:
    """Stop one project's cache from answering for another — prices and policies differ entirely.

    A session with no project may only reuse cache entries that also have no project,
    since an answer specific to one project does not generalise to a generic question.
    """
    if project_id is None:
        return models.Filter(must=[models.IsNullCondition(is_null=models.PayloadField(key="project_id"))])

    return models.Filter(must=[models.FieldCondition(key="project_id", match=models.MatchValue(value=project_id))])
