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
import time
from dataclasses import dataclass, field
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from backend.ai import prompts
from backend.ai.answer_cleanup import drop_image_denials
from backend.ai.citations import build_citations
from backend.ai.intent import needs_document_retrieval as query_needs_documents
from backend.ai.intent import needs_inventory as query_needs_inventory
from backend.core import tracing
from backend.core.enums import DocumentVisibility, MessageEmotion
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

# Standard messages from the edge-case table in README §5.4. These are shown verbatim in
# the chat, so wording differs by audience: Sale/Admin (INTERNAL clearance) get an
# actionable internal instruction ("báo Admin cập nhật"), while a customer/anonymous asker
# (PUBLIC clearance) has no Admin to report to — telling them to would just read as broken.
EMPTY_STATE_MESSAGE_INTERNAL = "Chưa có dữ liệu dự án, vui lòng báo Admin cập nhật."
EMPTY_STATE_MESSAGE_PUBLIC = (
    "Auremont chưa có đủ thông tin để trả lời câu hỏi này. Bạn thử hỏi cách khác, hoặc để "
    "lại thông tin liên hệ để được chuyên viên hỗ trợ nhé."
)
INVENTORY_UNAVAILABLE_MESSAGE = "Tạm thời không tra được tồn kho."
LOW_CONFIDENCE_MESSAGE_INTERNAL = "Không đủ thông tin, liên hệ Admin."
LOW_CONFIDENCE_MESSAGE_PUBLIC = (
    "Auremont chưa đủ thông tin để trả lời chính xác câu này. Bạn có thể hỏi cụ thể hơn, "
    "hoặc để lại thông tin liên hệ để được hỗ trợ nhanh nhất nhé."
)
RETRIEVAL_ERROR_MESSAGE = "Tạm thời không tra cứu được tài liệu, vui lòng thử lại sau."
GENERATION_ERROR_MESSAGE = "Tạm thời không tạo được câu trả lời, vui lòng thử lại sau."

# Every message above, as one set. These are UI states rather than things the assistant
# said about a project, so the router filters them out when assembling conversation
# history — see `_conversation_history` in routers/sale_chat.py.
NOTICE_MESSAGES = frozenset(
    {
        EMPTY_STATE_MESSAGE_INTERNAL,
        EMPTY_STATE_MESSAGE_PUBLIC,
        INVENTORY_UNAVAILABLE_MESSAGE,
        LOW_CONFIDENCE_MESSAGE_INTERNAL,
        LOW_CONFIDENCE_MESSAGE_PUBLIC,
        RETRIEVAL_ERROR_MESSAGE,
        GENERATION_ERROR_MESSAGE,
    }
)


def _empty_state_message(clearance: DocumentVisibility) -> str:
    return EMPTY_STATE_MESSAGE_PUBLIC if clearance == DocumentVisibility.PUBLIC else EMPTY_STATE_MESSAGE_INTERNAL


def _low_confidence_message(clearance: DocumentVisibility) -> str:
    return LOW_CONFIDENCE_MESSAGE_PUBLIC if clearance == DocumentVisibility.PUBLIC else LOW_CONFIDENCE_MESSAGE_INTERNAL


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
    # The third criterion, alongside the two above: a multi-part question answered only in
    # part scores low here while both of the others stay high.
    completeness: float | None = None
    # The Verifier's classification of the defect (verifier_service.FailureMode) and its
    # one-sentence explanation. Carried out of the pipeline so the Admin dashboard can
    # group failures by cause instead of listing undifferentiated low scores.
    failure_mode: str | None = None
    verifier_feedback: str | None = None
    # Project photos the question asked to see; empty whenever it asked for none.
    images: list[dict] = field(default_factory=list)
    # Drives AuremontAvatar.tsx — see MessageEmotion. `None` here means the caller (a
    # router) decides the emotion itself (customer_chat.py's gate/handoff branches, which
    # never reach the pipeline at all, set it directly rather than through this field).
    emotion: str | None = None


class PipelineState(TypedDict, total=False):
    """State threaded through the nodes — as described in ARCHITECTURE.md §3."""

    query: str
    project_id: str | None
    # Short-term working memory: earlier turns of this session, oldest first. Empty for the
    # first question in a session and whenever the caller has no DB session.
    conversation_history: list[prompts.ConversationTurn]
    # Long-term memory, already rendered by memory_service.format_profile.
    memory_profile: str
    # The asker's clearance for `rag_service.retrieve`/`cache_service`: INTERNAL for Sale/
    # Admin (full access), PUBLIC for the customer chat flow (anonymous or logged-in
    # customer). See backend/routers/customer_chat.py.
    clearance: DocumentVisibility
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
    completeness: float
    # The Verifier's classification of what went wrong, kept on the state so the router
    # and the audit log can both read it. See verifier_service.FailureMode.
    failure_mode: str
    # The Verifier's one-sentence correction note. This is what turns the retry into a
    # Reflexion loop: `_generate` reads it back and tells the model what to fix, instead
    # of re-running an identical prompt and usually getting an identical answer.
    verifier_feedback: str
    # The Verifier's proposal ("accept"/"regenerate"/"decline"). The router decides what
    # to actually do with it — see `_route_after_verify`.
    next_action: str
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
    """Check the Semantic Cache before spending any tokens.

    Skipped entirely once the session has history. The cache matches on the question text
    alone, so a follow-up like "còn 3PN thì sao?" would collide with the same words asked in
    a completely different conversation and serve back an answer about another project.
    Mid-conversation questions depend most on context and are exactly the ones the cache
    cannot key correctly — so they take the full path.
    """
    if state.get("conversation_history"):
        tracing.step("cache_check", hit=False, skipped="has_history")
        return {"used_cache": False}

    # Same reasoning for long-term memory: the cache is shared across everyone, but a
    # personalised answer was shaped by one person's profile. Serving it to the next
    # person who happens to ask the same words would leak that shaping.
    if state.get("memory_profile"):
        tracing.step("cache_check", hit=False, skipped="has_memory_profile")
        return {"used_cache": False}

    clearance = state.get("clearance", DocumentVisibility.INTERNAL)
    cached = cache_service.lookup_cache(state["query"], state.get("project_id"), clearance)
    if cached is None:
        tracing.step("cache_check", hit=False)
        return {"used_cache": False}

    tracing.step("cache_check", hit=True, verifier_score=cached.verifier_score)
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

    Queries at `state["clearance"]`: INTERNAL (Sale/Admin) can read both internal and
    public documents, PUBLIC (customer chat) reads only public ones — `rag_service`
    treats this argument as *the asker's clearance level*, not a label to match exactly.
    """
    query = state["query"]
    clearance = state.get("clearance", DocumentVisibility.INTERNAL)

    needs_inventory = query_needs_inventory(query)
    needs_document_retrieval = query_needs_documents(query)
    hits: list[dict] = []

    # The routing decision itself, recorded before it is acted on: "why did this question
    # never call the inventory API?" is otherwise unanswerable after the fact.
    tracing.step(
        "intent",
        needs_inventory=needs_inventory,
        needs_document_retrieval=needs_document_retrieval,
        clearance=str(clearance),
    )

    if needs_document_retrieval:
        try:
            # Retrieval embeds the question expanded with the previous one, so a bare
            # follow-up ("còn 3PN thì sao?") still carries the project and topic into the
            # vector. Intent detection above deliberately keeps reading the raw query: the
            # question at hand decides whether inventory is needed, not the one before it.
            hits = retrieve(
                prompts.build_retrieval_query(query, state.get("conversation_history") or []),
                clearance,
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
            tracing.step("retrieve", ok=False, error="qdrant_unavailable")
            # A combined inventory + policy question can still answer from its
            # live source when Qdrant is temporarily unavailable.
            if not needs_inventory:
                return {"notice": RETRIEVAL_ERROR_MESSAGE}
        else:
            # Scores travel with the count: a run that retrieved five documents whose best
            # score was 0.31 failed for a completely different reason than one that
            # retrieved nothing, and the two are indistinguishable from a bare count.
            top_score = hits[0].get("score") if hits else None
            tracing.step(
                "retrieve",
                ok=True,
                doc_count=len(hits),
                top_score=round(top_score, 4) if isinstance(top_score, int | float) else None,
                document_ids=[hit.get("document_id") for hit in hits],
            )

    if not hits and not needs_inventory:
        # No documents ingested yet and the question is not an inventory lookup ->
        # Empty State, not a system error.
        tracing.step("empty_state")
        return {"notice": _empty_state_message(clearance)}

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
    started = time.perf_counter()

    try:
        units = lookup_inventory(project_id, state["query"])
    except InventoryApiError:
        logger.warning(
            "Inventory lookup failed for project %s.",
            project_id,
            exc_info=True,
            extra={"event": "pipeline.inventory.failed", "project_id": project_id},
        )
        # Latency is recorded on the failure path too: a timeout and an instant refusal
        # are different faults, and only the duration tells them apart.
        tracing.step(
            "tool.inventory",
            ok=False,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        if state.get("retrieved_docs"):
            return {"inventory_failed": True, "inventory_units": []}
        return {"inventory_failed": True, "notice": INVENTORY_UNAVAILABLE_MESSAGE}

    tracing.step(
        "tool.inventory",
        ok=True,
        unit_count=len(units),
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )
    # An empty `units` list is a valid answer ("no 2PN units left"), not a failure —
    # inventory_service keeps those two cases distinct.
    return {"inventory_units": units, "inventory_failed": False}


def _generate(state: PipelineState) -> dict[str, Any]:
    """Generate an answer with citations from the collected context."""
    docs = state.get("retrieved_docs") or []
    units = state.get("inventory_units") or []
    is_public = state.get("clearance", DocumentVisibility.INTERNAL) == DocumentVisibility.PUBLIC

    prompt = prompts.build_prompt(
        state["query"],
        docs,
        units,
        state.get("needs_inventory", False),
        state.get("inventory_failed", False),
        state.get("images") or [],
        state.get("conversation_history") or [],
        state.get("memory_profile") or "",
        is_public=is_public,
        correction=state.get("verifier_feedback") or "",
    )
    system_instruction = prompts.SYSTEM_INSTRUCTION_PUBLIC if is_public else prompts.SYSTEM_INSTRUCTION
    attempt = state.get("retry_count", 0) + 1
    started = time.perf_counter()

    try:
        answer = generate_text(prompt, system_instruction=system_instruction)
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
        tracing.step("generate", attempt=attempt, ok=False)
        return {"notice": GENERATION_ERROR_MESSAGE}

    # Strip before checking for emptiness: an answer made up of only Markdown characters
    # renders as blank on screen, so it must fall into the error branch instead of
    # sending the Sale an empty chat bubble.
    answer = strip_markdown(answer)

    if not answer:
        tracing.step("generate", attempt=attempt, ok=False, empty=True)
        return {"notice": GENERATION_ERROR_MESSAGE}

    answer = drop_image_denials(answer, state.get("images") or [])

    # `corrected` is the flag that makes a Reflexion visible in the trace: attempt 2 with
    # a correction is the loop working, attempt 2 without one is a blind retry.
    tracing.step(
        "generate",
        attempt=attempt,
        ok=True,
        answer_len=len(answer),
        doc_count=len(docs),
        unit_count=len(units),
        corrected=bool(state.get("verifier_feedback")),
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )
    return {"draft_answer": answer, "citations": build_citations(docs)}


def _verify(state: PipelineState) -> dict[str, Any]:
    """The Verifier Agent scores the draft independently of Generate.

    Returns the three numeric criteria plus the structured verdict (`failure_mode`,
    `verifier_feedback`, `next_action`). The feedback is what `_generate` reads on a
    retry, so a regeneration is aimed at the specific defect rather than blind.
    """
    context = [doc["content"] for doc in state.get("retrieved_docs") or []]
    context.extend(prompts.format_unit_for_verifier(unit) for unit in state.get("inventory_units") or [])
    started = time.perf_counter()
    result = verifier_service.score_answer(state["query"], state.get("draft_answer", ""), context)

    # The label the eval flywheel is built on. `feedback` is deliberately absent: it can
    # quote the answer text, and traces are written to a file with a much looser handling
    # story than the audit log's.
    tracing.step(
        "verify",
        attempt=state.get("retry_count", 0) + 1,
        score=round(result.score, 4),
        faithfulness=round(result.faithfulness, 4),
        relevancy=round(result.relevancy, 4),
        completeness=round(result.completeness, 4),
        failure_mode=result.failure_mode.value,
        next_action=result.next_action.value,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )

    return {
        "verifier_score": round(result.score, 4),
        "faithfulness": round(result.faithfulness, 4),
        "answer_relevancy": round(result.relevancy, 4),
        "completeness": round(result.completeness, 4),
        "failure_mode": result.failure_mode.value,
        "verifier_feedback": result.feedback,
        "next_action": result.next_action.value,
    }


def _risk_check(state: PipelineState) -> dict[str, Any]:
    """Touches price/commitment -> raise the HITL flag so the Sale must read and confirm."""
    requires_hitl = risk_service.detect_commitment_risk(state.get("draft_answer", ""))
    tracing.step("risk_check", requires_hitl=requires_hitl)
    return {"requires_hitl": requires_hitl}


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
        tracing.step("tool.images", ok=False, skipped="no_db_session")
        return {"images": []}

    context = "\n".join(
        f"{doc.get('title') or ''} {doc.get('content') or ''}" for doc in state.get("retrieved_docs") or []
    )
    images = answer_images_service.collect_images(db, state["query"], context)
    tracing.step("tool.images", ok=True, image_count=len(images))
    return {"images": images}


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
    """Low score gets one regeneration; still low means declining beats answering wrongly.

    The Verifier's `next_action` is a proposal, and the routing rules here override it in
    both directions. A "decline" short-circuits the retry — when the judgement is that the
    context simply has no answer, regenerating burns a Gemini call to produce the same gap
    — but a passing score still wins, since a judge that scores well and then asks to
    decline is contradicting itself and the score is the number the threshold is tuned on.
    """
    score = state.get("verifier_score", 0.0)
    if score >= _threshold():
        tracing.step("route.after_verify", decision="accept", score=score)
        return "risk_check"

    if state.get("next_action") == verifier_service.NextAction.DECLINE.value:
        tracing.step("route.after_verify", decision="decline", score=score, reason="verifier_declined")
        return "low_confidence"

    if state.get("retry_count", 0) < MAX_GENERATE_RETRIES:
        tracing.step("route.after_verify", decision="retry", score=score)
        return "retry"

    tracing.step("route.after_verify", decision="decline", score=score, reason="retries_exhausted")
    return "low_confidence"


def _bump_retry(state: PipelineState) -> dict[str, Any]:
    return {"retry_count": state.get("retry_count", 0) + 1}


def _low_confidence(state: PipelineState) -> dict[str, Any]:
    return {"notice": _low_confidence_message(state.get("clearance", DocumentVisibility.INTERNAL))}


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


def run_pipeline(
    query: str,
    project_id: str | None = None,
    db: Session | None = None,
    conversation_history: list[prompts.ConversationTurn] | None = None,
    memory_profile: str = "",
    clearance: DocumentVisibility = DocumentVisibility.INTERNAL,
) -> PipelineResult:
    """Entry point for the Sale and customer chat flows.

    `clearance` is the asker's RBAC tier for retrieval and the semantic cache — INTERNAL
    (default, used by `sale_chat.py`) can read internal+public documents; the customer
    chat flow (`customer_chat.py`) always passes PUBLIC, anonymous or logged-in alike.

    `db` is only used by the image tool, to read the project catalogue. It is optional so
    callers with no session (unit tests driving the pipeline directly) keep working; those
    simply get an answer with no photos attached.

    `conversation_history` is the session's short-term working memory — earlier turns,
    oldest first — which lets the agent resolve a follow-up that names nothing ("còn 3PN
    thì sao?"). Omitting it degrades to the previous stateless behaviour rather than
    failing, so every existing caller keeps working unchanged.

    Never raises under any circumstance — the router calls this directly to build the
    response message, so every failure must collapse into a readable `PipelineResult`.
    """
    if not query or not query.strip():
        return PipelineResult(_empty_state_message(clearance), [], 0.0, False, emotion=MessageEmotion.REGRETFUL)

    tracing.start_run(query_len=len(query), project_id=project_id, clearance=str(clearance))
    try:
        return _run_traced(query, project_id, db, conversation_history, memory_profile, clearance)
    finally:
        # In a `finally` so a trace is still written when the graph raises. The outcome
        # fields are read off the result inside `_run_traced`; this only guarantees the
        # record is closed and flushed exactly once per run.
        tracing.finish()


def _run_traced(
    query: str,
    project_id: str | None,
    db: Session | None,
    conversation_history: list[prompts.ConversationTurn] | None,
    memory_profile: str,
    clearance: DocumentVisibility,
) -> PipelineResult:
    """The body of `run_pipeline`, split out so tracing can wrap every exit path."""
    initial: PipelineState = {
        "query": query.strip(),
        "project_id": project_id,
        "conversation_history": conversation_history or [],
        "memory_profile": memory_profile,
        "clearance": clearance,
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
        tracing.set_outcome(outcome="crash", verifier_score=0.0)
        return PipelineResult(GENERATION_ERROR_MESSAGE, [], 0.0, False, emotion=MessageEmotion.REGRETFUL)

    notice = state.get("notice")
    if notice:
        # Edge-case branch: a message instead of an answer, with no citations and always
        # score 0 so the Admin dashboard correctly counts it as a failed answer.
        #
        # Photos still ride along. They were requested explicitly and assert nothing, so
        # withholding them because the *text* could not be verified helps nobody.
        tracing.set_outcome(
            outcome="notice",
            verifier_score=state.get("verifier_score", 0.0),
            failure_mode=state.get("failure_mode"),
            retry_count=state.get("retry_count", 0),
        )
        return PipelineResult(
            notice,
            [],
            0.0,
            False,
            images=state.get("images") or [],
            # Carried even here — especially here. A declined answer is the case Admin most
            # needs to diagnose, and "which failure mode" is the whole diagnosis.
            failure_mode=state.get("failure_mode"),
            verifier_feedback=state.get("verifier_feedback"),
            emotion=MessageEmotion.REGRETFUL,
        )

    result = PipelineResult(
        draft_answer=state.get("draft_answer", ""),
        citations=state.get("citations") or [],
        verifier_score=state.get("verifier_score", 0.0),
        requires_hitl=state.get("requires_hitl", False),
        used_cache=state.get("used_cache", False),
        faithfulness=state.get("faithfulness"),
        answer_relevancy=state.get("answer_relevancy"),
        completeness=state.get("completeness"),
        failure_mode=state.get("failure_mode"),
        verifier_feedback=state.get("verifier_feedback"),
        images=state.get("images") or [],
        # Every path that gets here made it past Generate/Verify with a real answer — a
        # cache hit is exactly the same in spirit (an answer that already cleared this bar
        # once). requires_hitl doesn't downgrade this: Sale/Admin still gets the HITL card
        # regardless of avatar mood, and the customer flow never reaches this line for a
        # requires_hitl PUBLIC-tier answer (see the belt-and-suspenders check in
        # customer_chat.py, which intercepts it before persisting).
        emotion=MessageEmotion.HAPPY,
    )

    # Mid-conversation answers are never written to the cache, for the mirror of the reason
    # `_cache_check` skips reading it: the key would be the bare follow-up text, while the
    # answer only makes sense given the turns before it. Storing "còn 3PN thì sao?" would
    # poison the cache for every later session asking those same words.
    # `memory_profile` is excluded for the same reason: the answer was shaped by one
    # person's remembered preferences, so it is not a safe generic answer to replay.
    if not result.used_cache and not initial["conversation_history"] and not memory_profile:
        _store_cache(query, result, project_id, clearance)

    tracing.set_outcome(
        outcome="answered",
        verifier_score=result.verifier_score,
        failure_mode=result.failure_mode,
        requires_hitl=result.requires_hitl,
        used_cache=result.used_cache,
        retry_count=state.get("retry_count", 0),
        citation_count=len(result.citations),
    )
    return result


def _store_cache(query: str, result: PipelineResult, project_id: str | None, clearance: DocumentVisibility) -> None:
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
        clearance=clearance,
    )


# --------------------------------------------------------------------------- helpers


def _threshold() -> float:
    """Read the threshold at call time so settings changed by tests/Admin take effect immediately."""
    from backend.core.config import get_settings

    return get_settings().verifier_threshold_sale
