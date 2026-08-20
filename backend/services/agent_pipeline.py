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
from backend.ai.intent import names_specific_document_topic
from backend.ai.intent import needs_document_retrieval as query_needs_documents
from backend.ai.intent import needs_inventory as query_needs_inventory
from backend.core.enums import DocumentVisibility, MessageEmotion, MessageSender
from backend.core.gemini_client import generate_json, generate_text
from backend.services import answer_images_service, cache_service, risk_service, verifier_service
from backend.services.inventory_service import (
    InventoryApiError,
    InventoryProjectUnresolvedError,
    InventoryUnit,
    lookup_inventory,
)
from backend.services.rag_service import RetrievalError, retrieve
from backend.utils.text import strip_markdown

logger = logging.getLogger(__name__)

RETRIEVAL_TOP_K = 5

# Caps how much prior conversation is threaded into a turn — see run_pipeline's `history`
# param. Every message beyond this many (most-recent-first) is dropped: unbounded history
# would both blow the prompt-size/latency budget on a long-running chat and dilute the
# LLM's attention on the actual current question with turns that stopped being relevant.
# 16 (8 exchanges), not fewer: SYSTEM_INSTRUCTION_PUBLIC now has the model ask discovery
# questions ONE AT A TIME rather than bundled ("để ở hay đầu tư" then, separately,
# "ngân sách bao nhiêu") — that takes more turns to gather the same info than before, so a
# tighter cap would drop the customer's own early answers (budget, ở/đầu tư) before the
# conversation even gets to a recommendation.
MAX_HISTORY_MESSAGES = 16

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
# Distinct from the message above on purpose: this is not the inventory API being down,
# it's a genuinely normal follow-up question ("which project?") that a real Sale would
# also ask — see InventoryProjectUnresolvedError. Wording it like a system apology
# ("temporarily unable to check") would be actively misleading here.
INVENTORY_NEEDS_PROJECT_MESSAGE_INTERNAL = (
    "Phiên chat này chưa gắn với dự án cụ thể — nêu rõ tên dự án hoặc phân khu trong câu hỏi để tra đúng tồn kho nhé."
)
INVENTORY_NEEDS_PROJECT_MESSAGE_PUBLIC = (
    "Dạ bên em hiện có nhiều dự án khác nhau, anh chị đang quan tâm dự án nào để em kiểm tra "
    "tồn kho chính xác giúp mình ạ?"
)
LOW_CONFIDENCE_MESSAGE_INTERNAL = "Không đủ thông tin, liên hệ Admin."
LOW_CONFIDENCE_MESSAGE_PUBLIC = (
    "Auremont chưa đủ thông tin để trả lời chính xác câu này. Bạn có thể hỏi cụ thể hơn, "
    "hoặc để lại thông tin liên hệ để được hỗ trợ nhanh nhất nhé."
)
RETRIEVAL_ERROR_MESSAGE = "Tạm thời không tra cứu được tài liệu, vui lòng thử lại sau."
GENERATION_ERROR_MESSAGE = "Tạm thời không tạo được câu trả lời, vui lòng thử lại sau."


def _empty_state_message(clearance: DocumentVisibility) -> str:
    return EMPTY_STATE_MESSAGE_PUBLIC if clearance == DocumentVisibility.PUBLIC else EMPTY_STATE_MESSAGE_INTERNAL


def _low_confidence_message(clearance: DocumentVisibility) -> str:
    return LOW_CONFIDENCE_MESSAGE_PUBLIC if clearance == DocumentVisibility.PUBLIC else LOW_CONFIDENCE_MESSAGE_INTERNAL


def _inventory_needs_project_message(clearance: DocumentVisibility) -> str:
    return (
        INVENTORY_NEEDS_PROJECT_MESSAGE_PUBLIC
        if clearance == DocumentVisibility.PUBLIC
        else INVENTORY_NEEDS_PROJECT_MESSAGE_INTERNAL
    )


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
    # Drives AuremontAvatar.tsx — see MessageEmotion. `None` here means the caller (a
    # router) decides the emotion itself (customer_chat.py's gate/handoff branches, which
    # never reach the pipeline at all, set it directly rather than through this field).
    emotion: str | None = None
    # Short reply options the customer can tap — only ever non-empty on a PUBLIC-clearance
    # answer (see prompts.ConsultAnswer); Sale/INTERNAL answers keep this empty, they're
    # generated as plain text.
    quick_replies: list[str] = field(default_factory=list)


class PipelineState(TypedDict, total=False):
    """State threaded through the nodes — as described in ARCHITECTURE.md §3."""

    query: str
    project_id: str | None
    # The asker's clearance for `rag_service.retrieve`/`cache_service`: INTERNAL for Sale/
    # Admin (full access), PUBLIC for the customer chat flow (anonymous or logged-in
    # customer). See backend/routers/customer_chat.py.
    clearance: DocumentVisibility
    # Prior turns of the SAME session, oldest first, already capped to
    # MAX_HISTORY_MESSAGES by run_pipeline — [{"sender": "customer"|"agent"|"sale",
    # "content": str}, ...]. Read-only past this point: only prompts.build_prompt (via
    # _generate) and _retrieve's query-expansion touch it; no node ever writes it back.
    history: list[dict]
    retrieved_docs: list[dict]
    needs_inventory: bool
    needs_document_retrieval: bool
    inventory_units: list[InventoryUnit]
    inventory_failed: bool
    draft_answer: str
    citations: list[dict]
    quick_replies: list[str]
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
    # Overrides the default REGRETFUL avatar mood a notice gets in run_pipeline — most
    # notices really are bad news (empty state, low confidence, an API down), but the
    # "which project do you mean?" notice from _tool_call is an ordinary, pleasant
    # follow-up question, not an apology, so it sets RESPECTFUL here instead.
    notice_emotion: MessageEmotion
    used_cache: bool


# --------------------------------------------------------------------------- nodes


def _cache_check(state: PipelineState) -> dict[str, Any]:
    """Check the Semantic Cache before spending any tokens.

    Skipped entirely once there is conversation history. `cache_service` keys purely on
    the bare query text — a context-dependent follow-up ("giá bao nhiêu?") answered under
    one customer's history must never be replayed verbatim to a different customer whose
    "giá bao nhiêu?" means something else. Only a conversation's opening question, which
    carries no such ambiguity, is eligible for the cache — see the matching guard around
    `_store_cache`'s call site in `run_pipeline`.
    """
    if state.get("history"):
        return {"used_cache": False}

    clearance = state.get("clearance", DocumentVisibility.INTERNAL)
    cached = cache_service.lookup_cache(state["query"], state.get("project_id"), clearance)
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


# A query long/specific enough to name its own topic ("Tôi xem giá Sapphire 2") needs no
# help from history — folding in prior context here only pollutes the embedding with an
# unrelated topic from a few turns back (a live bug: "...thế có hồ bơi không" folded into
# "Tôi xem giá Sapphire 2" buried the actual Sapphire 2 price docs under pool-amenity ones,
# since "hồ bơi" had nothing to do with the topic the customer just switched to). Folding is
# reserved for genuinely short queries that can't carry a topic on their own.
_SHORT_QUERY_WORD_LIMIT = 4

# Vietnamese continuation openers pivot to a new angle on whatever topic is already live,
# WITHOUT naming it — "Thế tôi muốn mua để đầu tư thì sao?" carries exactly as little topic
# signal on its own as a bare "có", but at 9 words it sails past _SHORT_QUERY_WORD_LIMIT.
# Word count alone doesn't catch these, so a query starting with one of these needs folding
# too, regardless of length.
_CONTINUATION_PREFIXES = ("thế ", "vậy ", "còn ", "nếu ")


def _needs_history_fold(query: str) -> bool:
    if len(query.split()) <= _SHORT_QUERY_WORD_LIMIT:
        return True
    return query.strip().lower().startswith(_CONTINUATION_PREFIXES)


def _retrieval_query(query: str, history: list[dict] | None) -> str:
    """Fold recent turns into the string that gets embedded for retrieval — a bare
    follow-up ("giá bao nhiêu?", "có", "thế ... thì sao?") carries almost no signal on its
    own. Two distinct patterns need covering, and neither alone is enough:

    1. The topic a HUMAN set with their own last substantive messages — any non-AGENT
       sender counts (customer, or sale replying mid-handoff or drafting via the /suggest
       co-pilot), not just "whoever has this call's clearance", which stops matching who's
       actually asking once /suggest runs a CUSTOMER's message at INTERNAL clearance for
       Sale's benefit. Up to the last TWO such turns, not just one: a single turn back can
       itself be another referential follow-up ("Khu này có bãi đỗ xe không?") that doesn't
       repeat the actual standing topic (project name, budget) set further back — a live
       bug where "Thế tôi muốn mua để đầu tư thì sao?", three turns after "...ngân sách 3
       tỷ, muốn mua The Pavilion", lost both the project name and the budget because only
       the immediately preceding (unrelated, parking-related) turn got folded in.
    2. A topic the AI ITSELF just introduced by asking about it ("...các khoản chiết khấu
       này không ạ?" -> "có"). Folding in only pattern 1 drops this entirely — a short
       affirmative/negative reply to the AI's own question then retrieves against
       whatever topic was live several turns earlier, which reads as the AI forgetting the
       question it just asked. Only counts when that AI turn actually ends in "?" (a
       closing statement or plain greeting carries no topic worth folding in — a short
       reply isn't answering a question that wasn't asked), and only its tail is kept (not
       the whole paragraph before it), since the trailing question is what a short reply is
       responding to and a long AI reply would otherwise dilute the embedding with prose.

    Only applied when `query` itself needs it (see _needs_history_fold) — a query that
    already names its own topic is self-sufficient and must not be diluted by whatever was
    being discussed a turn earlier.

    Deliberately shallow — up to two turns back, not a scan of the whole history — so an
    old, since-resolved topic much earlier in the conversation doesn't keep dragging
    retrieval toward it. Does not affect keyword classification
    (needs_inventory/needs_document_retrieval) or what the LLM sees as "the question" — see
    _retrieve and build_prompt, both of which keep using the bare `query`.
    """
    if not history or not _needs_history_fold(query):
        return query

    human_turns = [turn.get("content", "") for turn in history if turn.get("sender") != MessageSender.AGENT]
    recent_human_turns = list(dict.fromkeys(human_turns[-2:]))

    last_turn = history[-1]
    last_turn_content = last_turn.get("content", "")
    ai_question_tail = (
        last_turn_content[-160:]
        if last_turn.get("sender") == MessageSender.AGENT and last_turn_content.rstrip().endswith("?")
        else ""
    )

    parts = [part for part in (ai_question_tail, *recent_human_turns) if part]
    return f"{' '.join(parts)} {query}" if parts else query


def _retrieve(state: PipelineState) -> dict[str, Any]:
    """Pull context from Qdrant and decide whether the inventory API is needed.

    Queries at `state["clearance"]`: INTERNAL (Sale/Admin) can read both internal and
    public documents, PUBLIC (customer chat) reads only public ones — `rag_service`
    treats this argument as *the asker's clearance level*, not a label to match exactly.
    """
    query = state["query"]
    clearance = state.get("clearance", DocumentVisibility.INTERNAL)

    # Keyword classification stays on the bare current-turn query — expanding it here
    # would let an old turn's inventory/document keywords leak into a question that no
    # longer needs them. Only the string actually embedded for retrieval is expanded.
    needs_inventory = query_needs_inventory(query)
    needs_document_retrieval = query_needs_documents(query)
    hits: list[dict] = []

    if needs_document_retrieval:
        try:
            hits = retrieve(
                _retrieval_query(query, state.get("history")),
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
            # A combined inventory + policy question can still answer from its
            # live source when Qdrant is temporarily unavailable.
            if not needs_inventory:
                return {"notice": RETRIEVAL_ERROR_MESSAGE}

    if not hits and not needs_inventory and names_specific_document_topic(query):
        # Zero hits for a query that named something specific (policy, discount, legal,
        # price list...) -> genuinely missing data, Empty State rather than a system error.
        #
        # The `names_specific_document_topic` check matters: `needs_document_retrieval`
        # above is True for almost any non-inventory question, including a bare "tư vấn
        # giúp em" with nothing to look up yet — retrieval running (and finding nothing)
        # on a query that never named anything specific isn't "missing data", it's an
        # opening message. Falling through to Generate with empty context lets the model
        # have a normal conversation (SYSTEM_INSTRUCTION_PUBLIC has it ask about needs)
        # instead of a canned "not enough information" wall on hello.
        return {"notice": _empty_state_message(clearance)}

    return {
        "retrieved_docs": hits,
        "needs_inventory": needs_inventory,
        "needs_document_retrieval": needs_document_retrieval,
    }


def _tool_call(state: PipelineState) -> dict[str, Any]:
    """Function Calling into the internal inventory API for constantly changing data.

    Sessions carry no project by default (the picker was dropped from session creation),
    so a missing `project_id` is the common case, not a rare one — see
    InventoryProjectUnresolvedError, caught separately below. A genuine `InventoryApiError`
    (network/API actually down) still degrades to answering from whatever documents were
    also retrieved, falling back to the generic "temporarily unavailable" notice only when
    there is nothing else to answer from.
    """
    project_id = state.get("project_id")
    clearance = state.get("clearance", DocumentVisibility.INTERNAL)

    try:
        units = lookup_inventory(project_id, state["query"])
    except InventoryProjectUnresolvedError:
        # Not an API failure — nothing to log/alert on. This is a normal, frequent shape
        # of question (no project on the session, several projects in the catalogue) with
        # a deterministic, correct response: ask which project, same as a real Sale would.
        # Always the clarifying question here, even if documents were also retrieved —
        # answering an inventory question from an unrelated project's policy doc would be
        # worse than asking.
        return {
            "inventory_failed": True,
            "notice": _inventory_needs_project_message(clearance),
            "notice_emotion": MessageEmotion.RESPECTFUL,
        }
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
    is_public = state.get("clearance", DocumentVisibility.INTERNAL) == DocumentVisibility.PUBLIC

    prompt = prompts.build_prompt(
        state["query"],
        docs,
        units,
        state.get("needs_inventory", False),
        state.get("inventory_failed", False),
        state.get("images") or [],
        is_public=is_public,
        history=state.get("history"),
    )
    quick_replies: list[str] = []

    try:
        if is_public:
            # Structured output on the SAME call (schema-constrained decoding), not a
            # second LLM call — see prompts.ConsultAnswer. Sale/INTERNAL has no quick-reply
            # UI to feed, so it stays on the simpler plain-text generate_text.
            parsed = generate_json(prompt, prompts.ConsultAnswer, system_instruction=prompts.SYSTEM_INSTRUCTION_PUBLIC)
        else:
            parsed = None
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

    if is_public:
        if parsed is None:
            # Same fail-closed posture as verifier_service: a judge/consult call that
            # returns nothing parseable is a generation failure, not an empty answer.
            logger.warning(
                "Consult LLM returned no parseable answer.",
                extra={"event": "pipeline.generate.unparseable", "project_id": state.get("project_id")},
            )
            return {"notice": GENERATION_ERROR_MESSAGE}
        answer, quick_replies = parsed.text, parsed.quick_replies

    # Strip before checking for emptiness: an answer made up of only Markdown characters
    # renders as blank on screen, so it must fall into the error branch instead of
    # sending the Sale an empty chat bubble.
    answer = strip_markdown(answer)

    if not answer:
        return {"notice": GENERATION_ERROR_MESSAGE}

    answer = drop_image_denials(answer, state.get("images") or [])

    return {"draft_answer": answer, "citations": _citations_for(docs), "quick_replies": quick_replies}


def _citations_for(docs: list[dict]) -> list[dict]:
    """Citations are only worth showing when they point at one coherent source.

    An unscoped search (no `project_id` on the session/query) can return top hits from
    several unrelated projects — the exact shape of query that also makes the model ask
    "which project/tower do you mean?" instead of actually answering from any of them.
    Chips naming 2-3 different projects' files under a reply that never engaged with any
    of them read as noise at best and as false grounding at worst, so this drops citations
    entirely rather than picking one project's files to keep — there's no principled way
    to know which project (if any) the answer actually used.
    """
    project_ids = {doc.get("project_id") for doc in docs if doc.get("project_id")}
    if len(project_ids) > 1:
        return []
    return build_citations(docs)


def _verify(state: PipelineState) -> dict[str, Any]:
    """The Verifier Agent scores Faithfulness/Relevancy, independently of Generate."""
    context = [doc["content"] for doc in state.get("retrieved_docs") or []]
    context.extend(prompts.format_unit_for_verifier(unit) for unit in state.get("inventory_units") or [])
    # Same history-expanded query as retrieval (see _retrieval_query) — otherwise the judge
    # sees a bare "có" as "the question" next to a correct, on-topic draft answer about
    # chiết khấu, marks it irrelevant to "có", and the pipeline discards a good answer for
    # the low-confidence fallback. The judge needs the same context a human reading the
    # transcript would have: what "có" is actually saying yes to.
    query = _retrieval_query(state["query"], state.get("history"))
    result = verifier_service.score_answer(query, state.get("draft_answer", ""), context)

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

    # No documents, no inventory units — the only way Generate is reached with both empty
    # is the "nothing specific was asked for" fallthrough in _retrieve (see
    # names_specific_document_topic there). Verify scores faithfulness against context
    # that doesn't exist, which is always 0.0 regardless of answer quality — that would
    # send every ordinary "tư vấn giúp em" opener through a retry and then the low-
    # confidence wall, exactly the canned-answer problem this fallthrough exists to avoid.
    # Same reasoning as the images branch above: nothing here for Verify to check.
    if not state.get("retrieved_docs") and not state.get("inventory_units"):
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
    clearance: DocumentVisibility = DocumentVisibility.INTERNAL,
    history: list[dict] | None = None,
) -> PipelineResult:
    """Entry point for the Sale and customer chat flows.

    `clearance` is the asker's RBAC tier for retrieval and the semantic cache — INTERNAL
    (default, used by `sale_chat.py`) can read internal+public documents; the customer
    chat flow (`customer_chat.py`) always passes PUBLIC, anonymous or logged-in alike.

    `db` is only used by the image tool, to read the project catalogue. It is optional so
    callers with no session (unit tests driving the pipeline directly) keep working; those
    simply get an answer with no photos attached.

    `history` is the session's prior turns, oldest first — [{"sender": ..., "content":
    ...}, ...] — from BEFORE this `query` (the caller persists the new turn separately;
    passing it here too would just show the model its own current question twice). `None`/
    empty means either a brand-new session or a caller that hasn't been updated to fetch
    it yet — both read identically to the pipeline: no context, cache eligible, exactly
    the old behaviour. Capped to the most recent `MAX_HISTORY_MESSAGES` here so a caller
    can pass a whole session's history without thinking about the limit itself.

    Never raises under any circumstance — the router calls this directly to build the
    response message, so every failure must collapse into a readable `PipelineResult`.
    """
    if not query or not query.strip():
        return PipelineResult(_empty_state_message(clearance), [], 0.0, False, emotion=MessageEmotion.REGRETFUL)

    initial: PipelineState = {
        "query": query.strip(),
        "project_id": project_id,
        "clearance": clearance,
        "history": (history or [])[-MAX_HISTORY_MESSAGES:],
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
        return PipelineResult(GENERATION_ERROR_MESSAGE, [], 0.0, False, emotion=MessageEmotion.REGRETFUL)

    notice = state.get("notice")
    if notice:
        # Edge-case branch: a message instead of an answer, with no citations and always
        # score 0 so the Admin dashboard correctly counts it as a failed answer.
        #
        # Photos still ride along. They were requested explicitly and assert nothing, so
        # withholding them because the *text* could not be verified helps nobody.
        return PipelineResult(
            notice,
            [],
            0.0,
            False,
            images=state.get("images") or [],
            emotion=state.get("notice_emotion", MessageEmotion.REGRETFUL),
        )

    result = PipelineResult(
        draft_answer=state.get("draft_answer", ""),
        citations=state.get("citations") or [],
        quick_replies=state.get("quick_replies") or [],
        verifier_score=state.get("verifier_score", 0.0),
        requires_hitl=state.get("requires_hitl", False),
        used_cache=state.get("used_cache", False),
        faithfulness=state.get("faithfulness"),
        answer_relevancy=state.get("answer_relevancy"),
        images=state.get("images") or [],
        # Every path that gets here made it past Generate/Verify with a real answer — a
        # cache hit is exactly the same in spirit (an answer that already cleared this bar
        # once). requires_hitl doesn't downgrade this: Sale/Admin still gets the HITL card
        # regardless of avatar mood, and the customer flow never reaches this line for a
        # requires_hitl PUBLIC-tier answer (see the belt-and-suspenders check in
        # customer_chat.py, which intercepts it before persisting).
        emotion=MessageEmotion.HAPPY,
    )

    # Matches the read-side guard in _cache_check: a context-dependent answer must never
    # be stored for an unrelated later conversation to hit.
    if not result.used_cache and not initial["history"]:
        _store_cache(query, result, project_id, clearance)

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
