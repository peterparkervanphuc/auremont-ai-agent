"""Multi-Agent orchestration: Cache -> Retrieval -> Tool-Use -> Generation -> Verify -> RiskCheck.

This is the core that wires the existing pieces into one complete answer flow for a
Sale, built as a LangGraph StateGraph following the diagram in ARCHITECTURE.md:

    START -> CacheCheck --hit--> END
                 |miss
             Retrieve --(empty/error)--> END
                 |
          needs real-time? --yes--> ToolCall (inventory API)
                 |no                    |
                 +--------> Generate <--+
                                |
                             Verify --low score--> Generate (at most once)
                                |pass       |retries exhausted -> END
                            RiskCheck -> END

Two principles govern this whole file:

* **Never let an exception escape.** `run_pipeline` sits directly on the Sale's request
  path; an uncaught exception becomes a 500 in the middle of a customer conversation.
  Every failure branch collapses into a readable message with `verifier_score = 0.0`.
* **Fail closed, on the safe side.** Without solid grounding say "not enough
  information" rather than guessing; anything touching price or commitments must be
  flagged for HITL.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from backend.ai import prompts
from backend.ai.answer_cleanup import drop_image_denials
from backend.ai.citations import build_citations
from backend.ai.intent import needs_document_retrieval as query_needs_documents
from backend.ai.intent import needs_inventory as query_needs_inventory
from backend.core.enums import DocumentVisibility
from backend.core.gemini_client import generate_text
from backend.services import answer_images_service, cache_service, risk_service, verifier_service
from backend.services.inventory_service import InventoryApiError, InventoryUnit, lookup_inventory
from backend.services.rag_service import RetrievalError, retrieve
from backend.utils.text import strip_markdown

logger = logging.getLogger(__name__)

RETRIEVAL_TOP_K = 5

# Regenerate exactly once when the Verifier scores low. Each loop costs two more LLM
# calls (generate + verify); more than that blows the sub-3-second field response budget.
MAX_GENERATE_RETRIES = 1

# Standard messages from the edge-case table in README §5.4.
EMPTY_STATE_MESSAGE = "Chưa có dữ liệu dự án, vui lòng báo Admin cập nhật."
INVENTORY_UNAVAILABLE_MESSAGE = "Tạm thời không tra được tồn kho."
LOW_CONFIDENCE_MESSAGE = "Không đủ thông tin, liên hệ Admin."
RETRIEVAL_ERROR_MESSAGE = "Tạm thời không tra cứu được tài liệu, vui lòng thử lại sau."
GENERATION_ERROR_MESSAGE = "Tạm thời không tạo được câu trả lời, vui lòng thử lại sau."


@dataclass
class PipelineResult:
    draft_answer: str
    citations: list[dict]
    verifier_score: float
    requires_hitl: bool
    # Added later, so it must have a default: the `stub_pipeline` fixture in
    # tests/test_api/test_sale_sessions.py builds PipelineResult from the four fields above.
    used_cache: bool = False
    # Two component scores kept alongside `verifier_score` (which stays the min of them):
    # the Admin dashboard charts them separately because they mean different things.
    # Faithfulness low -> the model invented figures; relevancy low -> retrieval fetched
    # the wrong documents. Collapsing both into one number loses that diagnosis.
    faithfulness: float | None = None
    answer_relevancy: float | None = None
    # Project photos the question asked to see; empty whenever it asked for none.
    images: list[dict] = field(default_factory=list)


class PipelineState(TypedDict, total=False):
    """State threaded through the nodes — as described in ARCHITECTURE.md §3."""

    query: str
    project_id: str | None
    retrieved_docs: list[dict]
    needs_inventory: bool
    needs_document_retrieval: bool
    inventory_units: list[InventoryUnit]
    inventory_failed: bool
    draft_answer: str
    citations: list[dict]
    verifier_score: float
    faithfulness: float
    answer_relevancy: float
    requires_hitl: bool
    images: list[dict]
    # Only the image tool reads this; it is threaded through rather than imported so the
    # pipeline keeps working when no session exists (see `run_pipeline`).
    db: Session | None
    retry_count: int
    # When set, this replaces draft_answer as the final answer: one of the edge-case
    # messages above. A notice means the flow stops here and goes no further.
    notice: str
    used_cache: bool


# --------------------------------------------------------------------------- nodes


def _cache_check(state: PipelineState) -> dict[str, Any]:
    """Check the Semantic Cache before spending any tokens."""
    cached = cache_service.lookup_cache(state["query"], state.get("project_id"))
    if cached is None:
        return {"used_cache": False}

    return {
        "used_cache": True,
        "draft_answer": cached.answer,
        "citations": cached.citations,
        "verifier_score": cached.verifier_score,
        # The cache only holds answers that passed RiskCheck and need no HITL (see `_store_cache`).
        "requires_hitl": False,
        "images": cached.images,
    }


def _retrieve(state: PipelineState) -> dict[str, Any]:
    """Pull context from Qdrant and decide whether the inventory API is needed.

    Always queries with INTERNAL permission: only Sale and Admin can use this chat flow,
    and `rag_service` treats that argument as *the asker's clearance level* — INTERNAL
    can read both internal and public documents.
    """
    query = state["query"]

    needs_inventory = query_needs_inventory(query)
    needs_document_retrieval = query_needs_documents(query)
    hits: list[dict] = []

    if needs_document_retrieval:
        try:
            hits = retrieve(
                query,
                DocumentVisibility.INTERNAL,
                state.get("project_id"),
                RETRIEVAL_TOP_K,
            )
        except RetrievalError:
            logger.exception(
                "Qdrant retrieval failed.",
                extra={
                    "event": "pipeline.retrieve.failed",
                    "project_id": state.get("project_id"),
                    "query_len": len(query),
                },
            )
            # A combined inventory + policy question can still answer from its
            # live source when Qdrant is temporarily unavailable.
            if not needs_inventory:
                return {"notice": RETRIEVAL_ERROR_MESSAGE}

    if not hits and not needs_inventory:
        # No documents ingested yet and the question is not an inventory lookup ->
        # Empty State, not a system error.
        return {"notice": EMPTY_STATE_MESSAGE}

    return {
        "retrieved_docs": hits,
        "needs_inventory": needs_inventory,
        "needs_document_retrieval": needs_document_retrieval,
    }


def _tool_call(state: PipelineState) -> dict[str, Any]:
    """Function Calling into the internal inventory API for constantly changing data.

    A session with no project is NOT short-circuited here. Sessions stopped carrying a
    project when the picker was dropped from session creation, so bailing on a missing
    `project_id` made every live-inventory question answer "Tạm thời không tra được tồn
    kho" while the API was perfectly healthy. `lookup_inventory` resolves the project to
    query (see `resolve_api_project_id`) and raises `InventoryApiError` only when it
    genuinely cannot pick one.
    """
    project_id = state.get("project_id")

    try:
        units = lookup_inventory(project_id, state["query"])
    except InventoryApiError:
        logger.warning(
            "Inventory lookup failed for project %s.",
            project_id,
            exc_info=True,
            extra={"event": "pipeline.inventory.failed", "project_id": project_id},
        )
        if state.get("retrieved_docs"):
            return {"inventory_failed": True, "inventory_units": []}
        return {"inventory_failed": True, "notice": INVENTORY_UNAVAILABLE_MESSAGE}

    # An empty `units` list is a valid answer ("no 2PN units left"), not a failure —
    # inventory_service keeps those two cases distinct.
    return {"inventory_units": units, "inventory_failed": False}


def _generate(state: PipelineState) -> dict[str, Any]:
    """Generate an answer with citations from the collected context."""
    docs = state.get("retrieved_docs") or []
    units = state.get("inventory_units") or []

    prompt = prompts.build_prompt(
        state["query"],
        docs,
        units,
        state.get("needs_inventory", False),
        state.get("inventory_failed", False),
        state.get("images") or [],
    )

    try:
        answer = generate_text(prompt, system_instruction=prompts.SYSTEM_INSTRUCTION)
    except Exception:
        logger.exception(
            "Answer generation failed.",
            extra={
                "event": "pipeline.generate.failed",
                "project_id": state.get("project_id"),
                "doc_count": len(docs),
                "unit_count": len(units),
            },
        )
        return {"notice": GENERATION_ERROR_MESSAGE}

    # Strip before checking for emptiness: an answer made up of only Markdown characters
    # renders as blank on screen, so it must fall into the error branch instead of
    # sending the Sale an empty chat bubble.
    answer = strip_markdown(answer)

    if not answer:
        return {"notice": GENERATION_ERROR_MESSAGE}

    answer = drop_image_denials(answer, state.get("images") or [])

    return {"draft_answer": answer, "citations": build_citations(docs)}


def _verify(state: PipelineState) -> dict[str, Any]:
    """The Verifier Agent scores Faithfulness/Relevancy, independently of Generate."""
    context = [doc["content"] for doc in state.get("retrieved_docs") or []]
    context.extend(prompts.format_unit_for_verifier(unit) for unit in state.get("inventory_units") or [])
    result = verifier_service.score_answer(state["query"], state.get("draft_answer", ""), context)

    return {
        "verifier_score": round(result.score, 4),
        "faithfulness": round(result.faithfulness, 4),
        "answer_relevancy": round(result.relevancy, 4),
    }


def _risk_check(state: PipelineState) -> dict[str, Any]:
    """Touches price/commitment -> raise the HITL flag so the Sale must read and confirm."""
    return {"requires_hitl": risk_service.detect_commitment_risk(state.get("draft_answer", ""))}


def _image_tool(state: PipelineState) -> dict[str, Any]:
    """Fetch project photos, but only for a question that asked to see something.

    Runs *before* Generate, like the inventory tool: the model has to know the photos are
    coming. When this ran afterwards it read "the context contains no images" off its own
    prompt and told the Sale to go ask Admin for pictures — printed directly above a strip
    of those pictures.

    The project is resolved from the question plus the retrieved documents, since a Sale
    often asks "cho xem mặt bằng" without naming one, and retrieval has already grounded
    on the right project by this point.

    Needs a DB session to read the catalogue. `run_pipeline` leaves `db` unset in contexts
    that have none (unit tests calling the pipeline directly), and the tool is then simply
    skipped — an answer without photos, never an error.
    """
    db = state.get("db")
    if db is None:
        return {"images": []}

    context = "\n".join(
        f"{doc.get('title') or ''} {doc.get('content') or ''}" for doc in state.get("retrieved_docs") or []
    )
    return {"images": answer_images_service.collect_images(db, state["query"], context)}


# --------------------------------------------------------------------------- routing


def _route_after_cache(state: PipelineState) -> str:
    return "hit" if state.get("used_cache") else "miss"


def _route_after_retrieve(state: PipelineState) -> str:
    if state.get("notice"):
        return "stop"
    return "tool_call" if state.get("needs_inventory") else "generate"


def _route_after_tool_call(state: PipelineState) -> str:
    return "stop" if state.get("notice") else "generate"


def _route_after_generate(state: PipelineState) -> str:
    if state.get("notice"):
        return "stop"

    # A question answered by photographs skips Verify. Answer-relevancy scores the *text*
    # against the question, and for "cho xem hình ảnh The Palma" no text can score well —
    # the photos are the answer. Left in, it drove every such question into
    # "Không đủ thông tin, liên hệ Admin." while the requested photos sat right below it.
    #
    # Nothing is loosened by this: the images come from the catalogue rather than from the
    # model, and RiskCheck still runs, so a price mentioned in passing still raises HITL.
    # Faithfulness/relevancy stay None, so these answers are excluded from the Admin
    # dashboard averages exactly like cache hits are.
    if state.get("images") and answer_images_service.wants_images(state["query"]):
        return "risk_check"

    return "verify"


def _route_after_verify(state: PipelineState) -> str:
    """Low score gets one regeneration; still low means declining beats answering wrongly."""
    score = state.get("verifier_score", 0.0)
    if score >= _threshold():
        return "risk_check"

    if state.get("retry_count", 0) < MAX_GENERATE_RETRIES:
        return "retry"

    return "low_confidence"


def _bump_retry(state: PipelineState) -> dict[str, Any]:
    return {"retry_count": state.get("retry_count", 0) + 1}


def _low_confidence(state: PipelineState) -> dict[str, Any]:
    return {"notice": LOW_CONFIDENCE_MESSAGE}


# --------------------------------------------------------------------------- graph


def _build_graph():
    graph = StateGraph(PipelineState)

    graph.add_node("cache_check", _cache_check)
    graph.add_node("retrieve", _retrieve)
    graph.add_node("tool_call", _tool_call)
    graph.add_node("generate", _generate)
    graph.add_node("verify", _verify)
    graph.add_node("risk_check", _risk_check)
    graph.add_node("image_tool", _image_tool)
    graph.add_node("bump_retry", _bump_retry)
    graph.add_node("low_confidence", _low_confidence)

    graph.add_edge(START, "cache_check")
    graph.add_conditional_edges("cache_check", _route_after_cache, {"hit": END, "miss": "retrieve"})
    graph.add_conditional_edges(
        "retrieve", _route_after_retrieve, {"stop": END, "tool_call": "tool_call", "generate": "image_tool"}
    )
    graph.add_conditional_edges("tool_call", _route_after_tool_call, {"stop": END, "generate": "image_tool"})
    graph.add_conditional_edges(
        "generate", _route_after_generate, {"stop": END, "verify": "verify", "risk_check": "risk_check"}
    )
    graph.add_conditional_edges(
        "verify",
        _route_after_verify,
        {"risk_check": "risk_check", "retry": "bump_retry", "low_confidence": "low_confidence"},
    )
    graph.add_edge("bump_retry", "generate")
    graph.add_edge("low_confidence", END)
    graph.add_edge("image_tool", "generate")
    graph.add_edge("risk_check", END)

    return graph.compile()


# Compile once and reuse: building the graph costs time and does not depend on the query.
_COMPILED_GRAPH = None


def _get_graph():
    global _COMPILED_GRAPH
    if _COMPILED_GRAPH is None:
        _COMPILED_GRAPH = _build_graph()
    return _COMPILED_GRAPH


# --------------------------------------------------------------------------- entry point


def run_pipeline(query: str, project_id: str | None = None, db: Session | None = None) -> PipelineResult:
    """Entry point for the Sale chat flow.

    `db` is only used by the image tool, to read the project catalogue. It is optional so
    callers with no session (unit tests driving the pipeline directly) keep working; those
    simply get an answer with no photos attached.

    Never raises under any circumstance — the router calls this directly to build the
    response message, so every failure must collapse into a readable `PipelineResult`.
    """
    if not query or not query.strip():
        return PipelineResult(EMPTY_STATE_MESSAGE, [], 0.0, False)

    initial: PipelineState = {
        "query": query.strip(),
        "project_id": project_id,
        "retrieved_docs": [],
        "citations": [],
        "verifier_score": 0.0,
        "requires_hitl": False,
        "retry_count": 0,
        "used_cache": False,
        "images": [],
        "db": db,
    }

    try:
        state = _get_graph().invoke(initial)
    except Exception:
        # Final safety net: an unexpected error inside the graph must not become a 500.
        # Without this log the failure is completely invisible — the Sale just sees a
        # generic message and nothing anywhere records why.
        logger.exception(
            "Pipeline sap — tra ve thong bao loi chung.",
            extra={
                "event": "pipeline.crash",
                "project_id": project_id,
                "query_len": len(query),
            },
        )
        return PipelineResult(GENERATION_ERROR_MESSAGE, [], 0.0, False)

    notice = state.get("notice")
    if notice:
        # Edge-case branch: a message instead of an answer, with no citations and always
        # score 0 so the Admin dashboard correctly counts it as a failed answer.
        #
        # Photos still ride along. They were requested explicitly and assert nothing, so
        # withholding them because the *text* could not be verified helps nobody.
        return PipelineResult(notice, [], 0.0, False, images=state.get("images") or [])

    result = PipelineResult(
        draft_answer=state.get("draft_answer", ""),
        citations=state.get("citations") or [],
        verifier_score=state.get("verifier_score", 0.0),
        requires_hitl=state.get("requires_hitl", False),
        used_cache=state.get("used_cache", False),
        faithfulness=state.get("faithfulness"),
        answer_relevancy=state.get("answer_relevancy"),
        images=state.get("images") or [],
    )

    if not result.used_cache:
        _store_cache(query, result, project_id)

    return result


def _store_cache(query: str, result: PipelineResult, project_id: str | None) -> None:
    """Cache only clean answers: above the Verifier threshold and free of price/commitment.

    Price-touching answers must re-run RiskCheck every time so the Sale always gets the
    HITL card — serving them from cache would skip that mandatory confirmation step.

    Image requests are never cached either. The cache matches on meaning, and "cho xem
    hình ảnh The Palma" and "cho xem mặt bằng The Palma" are close enough to collide —
    which served the whole gallery to someone who asked only for floor plans. The photo
    set is chosen per question, so it cannot be shared between two questions.
    """
    if result.requires_hitl or result.verifier_score < _threshold():
        return

    if answer_images_service.wants_images(query):
        return

    cache_service.store_cache(
        query=query,
        answer=result.draft_answer,
        citations=result.citations,
        verifier_score=result.verifier_score,
        project_id=project_id,
        images=result.images,
    )


# --------------------------------------------------------------------------- helpers


def _threshold() -> float:
    """Read the threshold at call time so settings changed by tests/Admin take effect immediately."""
    from backend.core.config import get_settings

    return get_settings().verifier_threshold_sale
