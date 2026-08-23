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
import re
import time
from dataclasses import dataclass, field
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from backend.ai import prompts
from backend.ai.answer_cleanup import drop_false_image_confirmations, drop_image_denials
from backend.ai.citations import build_citations
from backend.ai.intent import (
    is_catalog_overview_query,
    is_conversation_meta_query,
    is_customer_memory_query,
    is_search_refinement,
    mentions_inventory_followup_field,
    names_specific_document_topic,
    preflight_policy,
)
from backend.ai.intent import needs_document_retrieval as query_needs_documents
from backend.ai.intent import needs_inventory as query_needs_inventory
from backend.core import tracing
from backend.core.config import get_settings
from backend.core.enums import DocumentVisibility, MessageEmotion, MessageSender
from backend.core.gemini_client import generate_json
from backend.models.project import Project
from backend.services import (
    answer_images_service,
    cache_service,
    catalog_context_service,
    catalog_offer_service,
    memory_service,
    reflection_memory,
    risk_service,
    search_criteria,
    verifier_service,
)
from backend.services.inventory_service import (
    InventoryApiError,
    InventoryProjectUnresolvedError,
    InventoryUnit,
    apply_criteria,
    fetch_units,
    format_preference_coverage,
    has_exact_project_mapping,
    lookup_inventory,
)
from backend.services.rag_service import RetrievalError, retrieve
from backend.utils.text import strip_diacritics, strip_markdown

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
PREFLIGHT_MESSAGES = {
    "illegal_request": (
        "Mình không thể hỗ trợ lách luật, trốn thuế hoặc làm giả hồ sơ. Mình có thể giúp "
        "anh/chị kiểm tra quy trình giao dịch và các giấy tờ cần chuẩn bị theo hướng hợp pháp."
    ),
    "privacy_request": (
        "Mình không thể cung cấp thông tin cá nhân chưa được phép công khai của chủ nhà hoặc cư dân. "
        "Anh/chị có thể liên hệ qua kênh chính thức của dự án để được kết nối đúng người phụ trách."
    ),
    "discrimination_request": (
        "Mình không thể lọc hoặc đánh giá nơi ở theo dân tộc, tôn giáo hay quốc tịch của cư dân. "
        "Mình có thể giúp so sánh theo các tiêu chí phù hợp như an ninh, tiện ích, ngân sách và thời gian di chuyển."
    ),
    "scam_warning": (
        "Đây là dấu hiệu giao dịch có rủi ro. Anh/chị chưa nên chuyển tiền; hãy kiểm tra giấy tờ gốc, "
        "đối chiếu người nhận tiền với chủ thể có quyền giao dịch và chỉ ký/cọc khi điều khoản, căn hộ và "
        "tài khoản nhận tiền đã được xác minh qua kênh chính thức."
    ),
    "rental_out_of_scope": (
        "Hiện Auremont chỉ có dữ liệu căn hộ dự án đang bán, chưa có nguồn nhà cho thuê để lọc chính xác. "
        "Nếu anh/chị cân nhắc mua để ở hoặc mua đầu tư, mình có thể tiếp tục tư vấn theo ngân sách."
    ),
}

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
    # Short reply options the customer can tap — only ever non-empty on a PUBLIC-clearance
    # answer (see prompts.ConsultAnswer); Sale/INTERNAL answers keep this empty (see
    # prompts.SaleAnswer).
    quick_replies: list[str] = field(default_factory=list)
    # Recommended units rendered as their own cards — see PipelineState.listings above.
    listings: list[dict] = field(default_factory=list)
    # Plausible NEXT questions about the topic already on the table, for both audiences.
    # Distinct from `quick_replies`, which answer a question the assistant just asked —
    # see prompts.ConsultAnswer.
    suggested_questions: list[str] = field(default_factory=list)


class PipelineState(TypedDict, total=False):
    """State threaded through the nodes — as described in ARCHITECTURE.md §3."""

    query: str
    session_id: int | None
    project_id: str | None
    resolved_project_ids: list[str]
    excluded_project_ids: list[str]
    # Long-term memory, already rendered by memory_service.format_profile.
    memory_profile: str
    # Structured twin used only by the deterministic customer-profile recall path.
    memory_profile_data: memory_service.UserProfile
    # A deterministic answer sourced only from this session's customer profile. When
    # true, Preflight ends the graph before cache/retrieval/model calls.
    answered_from_memory: bool
    # Lessons the agent learned from its own earlier mistakes, already rendered by
    # reflection_memory.format_lessons. Unlike memory_profile this is about the agent,
    # not the asker — see backend/services/reflection_memory.py.
    reflection_lessons: str
    # Optional isolation boundary for learned lessons. Sale chat supplies one scope per
    # consultation session so one customer's lessons cannot affect another customer.
    reflection_scope: str | None
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
    # Exact tower-level facts from Project.details. This complements RAG documents that
    # may only describe an aggregate range for the whole cluster.
    catalog_context: str
    # True only when the structured tower record has every field this query asks for.
    # Aggregate document chunks are excluded only in that case.
    catalog_context_complete: bool
    # Structured price/type ranges from every matching Project.details.pricing row.
    catalog_offers: list[catalog_offer_service.CatalogOffer]
    catalog_offer_context: str
    # A full project-by-category index, built straight from every Project row rather than
    # retrieval — only set for a broad "what do you have at all" survey question, where
    # RAG's top-k semantic search would otherwise return an arbitrary, incomplete subset
    # (see catalog_offer_service.build_catalog_overview).
    catalog_overview_context: str
    needs_inventory: bool
    needs_document_retrieval: bool
    inventory_units: list[InventoryUnit]
    # Raw inventory is retained only for deterministic zero-result diagnosis. It never
    # enters the generation prompt, which receives only the filtered subset below.
    all_units: list[InventoryUnit]
    inventory_failed: bool
    criteria: search_criteria.SearchCriteria
    zero_result_diagnosis: search_criteria.ZeroResultDiagnosis
    draft_answer: str
    citations: list[dict]
    quick_replies: list[str]
    # Recommended units rendered as their own cards (with paging arrows) instead of as
    # bullet lines in draft_answer — see prompts.PropertyListing and the LISTINGS block in
    # SYSTEM_INSTRUCTION_PUBLIC. Each dict already carries a resolved image_url/project_id
    # (see _resolve_listing_images), never the model's own guess.
    listings: list[dict]
    suggested_questions: list[str]
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
    # Set by `_image_tool` — see answer_images_service.floor_plan_only_towers. None means
    # nothing extra to tell Generate; a list (possibly empty) means the resolved project has
    # no per-unit-type floor-plan photo, only tower-wide sheets (or none at all).
    floor_plan_towers_only: list[str] | None
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


def _preflight(state: PipelineState) -> dict[str, Any]:
    """Stop unsafe or unsupported requests before cache, retrieval, and model calls."""
    policy = preflight_policy(state["query"])
    if policy is None:
        if is_customer_memory_query(state["query"]):
            answer = memory_service.format_recall_answer(
                state["query"], state.get("memory_profile_data") or memory_service.UserProfile()
            )
            tracing.step("preflight", decision="memory_recall", has_profile=bool(state.get("memory_profile")))
            return {
                "draft_answer": answer,
                "answered_from_memory": True,
                "verifier_score": 1.0,
                "requires_hitl": False,
            }
        return {}
    tracing.step("preflight", policy=policy)
    return {
        "notice": PREFLIGHT_MESSAGES[policy],
        "notice_emotion": MessageEmotion.RESPECTFUL,
    }


def _scope_resolve(state: PipelineState) -> dict[str, Any]:
    """Resolve project, sub-zone or tower names before cache/RAG/tool selection."""
    db = state.get("db")
    current = state.get("project_id")
    if db is None:
        return {"resolved_project_ids": [current] if current else []}

    references = answer_images_service.resolve_project_references(db, state["query"])
    project_ids = list(references.included_ids)
    excluded_project_ids = list(references.excluded_ids)
    if not project_ids:
        stale_ids: list[str] = []
        for turn in reversed(state.get("history") or []):
            if turn.get("sender") == MessageSender.AGENT:
                continue
            stale_ids = answer_images_service.resolve_project_ids(db, turn.get("content", ""))
            if stale_ids:
                break
        if not stale_ids and current:
            stale_ids = [current]

        # A stale project (named earlier in history, or pinned on the session) is only
        # trustworthy if this turn is still on the same topic. When the CURRENT query
        # names a product category ("biệt thự") that conflicts with every stale
        # candidate's own category, the conversation has switched topic entirely —
        # inheriting an apartment project's scope onto a villa question either answers
        # from the wrong project's documents, or has the model correctly-but-uselessly
        # report "that apartment project has no villa data" instead of the villa
        # sub-zones the asker actually wants. Drop the stale scope and let retrieval/
        # catalogue search run unscoped across every project instead.
        category = answer_images_service.named_category(state["query"])
        if category is not None and stale_ids:
            stale_ids = [
                pid
                for pid in stale_ids
                if (project := db.get(Project, pid)) is not None
                and category in answer_images_service.project_categories(project)
            ]

        project_ids = stale_ids

    # A single project can safely hard-scope Qdrant. A comparison retains all ids for
    # catalogue filtering but leaves RAG unscoped so both projects can contribute.
    rag_project_id = project_ids[0] if len(project_ids) == 1 else None
    tracing.step("scope.resolve", project_ids=project_ids, rag_project_id=rag_project_id)
    return {
        "project_id": rag_project_id,
        "resolved_project_ids": project_ids,
        "excluded_project_ids": excluded_project_ids,
    }


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
        tracing.step("cache_check", hit=False, skipped="has_history")
        return {"used_cache": False}

    # Same reasoning for long-term memory: the cache is shared across everyone, but a
    # personalised answer was shaped by one person's profile. Serving it to the next
    # person who happens to ask the same words would leak that shaping.
    if state.get("memory_profile"):
        tracing.step("cache_check", hit=False, skipped="has_memory_profile")
        return {"used_cache": False}

    # A shared semantic-cache key knows nothing about this session's accumulated unit
    # filters. The same words under a 2PN search and a 3PN search are different questions,
    # so replaying either answer into the other session would leak context silently.
    session_id = state.get("session_id")
    if session_id is not None and get_settings().search_criteria_enabled:
        criteria, _ = search_criteria.load(session_id)
        if not criteria.is_empty():
            tracing.step("cache_check", hit=False, skipped="has_search_criteria")
            return {"used_cache": False, "criteria": criteria}

    clearance = state.get("clearance", DocumentVisibility.INTERNAL)
    cached = cache_service.lookup_cache(state["query"], state.get("project_id"), clearance)
    if cached is None:
        tracing.step("cache_check", hit=False)
        return {"used_cache": False}

    # RiskCheck is re-run here, on the cached text, rather than trusting a flag stored
    # alongside it. A cache hit routes straight to END (see `_route_after_cache`), so this
    # is the ONLY place the HITL gate can still fire for a cached answer — and the gate is
    # the whole safety story for price and commitment wording. `detect_commitment_risk` is
    # a deterministic regex over the answer text with no model call behind it, so it costs
    # nothing here and returns exactly the verdict the original generation got.
    #
    # This is what makes caching price answers safe at all: before it, `_store_cache`
    # refused every `requires_hitl` answer, which in a real-estate corpus is nearly all of
    # them — the cache collection was never even created in practice.
    requires_hitl = risk_service.detect_commitment_risk(cached.answer)

    tracing.step("cache_check", hit=True, verifier_score=cached.verifier_score, requires_hitl=requires_hitl)
    return {
        "used_cache": True,
        "draft_answer": cached.answer,
        "citations": cached.citations,
        "verifier_score": cached.verifier_score,
        "requires_hitl": requires_hitl,
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
    project_id = state.get("project_id")

    # Keyword classification stays on the bare current-turn query — expanding it here
    # would let an old turn's inventory/document keywords leak into a question that no
    # longer needs them. Only the string actually embedded for retrieval is expanded.
    inventory_context_queries = _inventory_context_queries(state.get("history"))
    continues_inventory_lookup = bool(
        inventory_context_queries
        and mentions_inventory_followup_field(query)
        and any(query_needs_inventory(context_query) for context_query in inventory_context_queries)
    )
    needs_inventory = query_needs_inventory(query) or continues_inventory_lookup
    needs_document_retrieval = query_needs_documents(query)
    catalog_overview_context = (
        catalog_offer_service.build_catalog_overview(state.get("db")) if is_catalog_overview_query(query) else ""
    )
    catalog = catalog_context_service.resolve_tower_context(
        state.get("db"), state.get("project_id"), query
    )
    catalog_context = catalog.text
    hits: list[dict] = []

    # Retrieval embeds the question expanded with the previous one, so a bare follow-up
    # ("còn 3PN thì sao?") still carries the project and topic into the vector. Intent
    # detection above deliberately keeps reading the raw query: the question at hand
    # decides whether inventory is needed, not the one before it.
    retrieval_query = _retrieval_query(query, state.get("history"))

    # A customer-chat session carries no project by default (see _tool_call's docstring:
    # "the picker was dropped from session creation") — the only place a project the
    # customer named ever appears is inside the conversation itself. Without this, a
    # session can never answer an inventory question at all: `_tool_call` keeps raising
    # InventoryProjectUnresolvedError and asking "which project?" forever, even several
    # turns after the customer already named one ("Ocean Park 1"). Resolved from the same
    # history-folded string as retrieval, so a project named a turn or two back still
    # scopes this turn.
    #
    # Deliberately kept OUT of the Qdrant call below (separate `inventory_project_id`, not
    # `project_id`): every ingested chunk's `project_id` payload field is still NULL as of
    # 2026-08-22 (an ingestion-pipeline gap, documents are never linked to a project on
    # upload) — passing a resolved id into `retrieve()`'s hard payload filter would match
    # zero chunks and silently turn a working unscoped search into an empty one. Once
    # ingestion starts tagging `project_id`, this can be threaded into `retrieve()` too.
    inventory_project_id = project_id
    if inventory_project_id is None:
        db = state.get("db")
        if db is not None:
            inventory_project_id = answer_images_service.resolve_project_id(db, retrieval_query)

    # The routing decision itself, recorded before it is acted on: "why did this question
    # never call the inventory API?" is otherwise unanswerable after the fact.
    tracing.step(
        "intent",
        needs_inventory=needs_inventory,
        needs_document_retrieval=needs_document_retrieval,
        clearance=str(clearance),
    )

    if needs_document_retrieval:
        started = time.perf_counter()
        try:
            hits = retrieve(
                retrieval_query,
                clearance,
                project_id,
                RETRIEVAL_TOP_K,
                # Embedding/reranking needs history to resolve a follow-up, but exact
                # identifier constraints must come from the current turn. Otherwise a
                # previous "2PN" contaminates "còn 3PN thì sao?" and both look required.
                focus_query=query,
                # A parent catalogue scope includes documents assigned to its child
                # subdivisions. The relationship comes from catalogue metadata rather
                # than a project-name list in code.
                project_ids=_rag_project_scope_ids(state.get("db"), state.get("project_id")),
                excluded_project_ids=state.get("excluded_project_ids") or None,
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
            tracing.step(
                "retrieve",
                ok=False,
                error="qdrant_unavailable",
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            # A combined inventory + policy question can still answer from its
            # live source when Qdrant is temporarily unavailable.
            if not needs_inventory and not catalog_context:
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
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )

    if not hits and not needs_inventory and not catalog_context and names_specific_document_topic(query):
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
        tracing.step("empty_state")
        return {"notice": _empty_state_message(clearance)}

    return {
        "retrieved_docs": hits,
        "catalog_context": catalog_context,
        "catalog_context_complete": catalog.complete,
        "catalog_overview_context": catalog_overview_context,
        "needs_inventory": needs_inventory,
        "needs_document_retrieval": needs_document_retrieval,
        "project_id": inventory_project_id,
    }


def _rag_project_scope_ids(db: Session | None, project_id: str | None) -> list[str] | None:
    """The named catalogue project plus every direct child stored beneath it."""
    if not project_id:
        return None
    if db is None:
        return [project_id]

    try:
        ids = [project_id]
        for project in db.query(Project).all():
            info = (project.details or {}).get("project") or {}
            if info.get("parent_project_id") == project_id:
                ids.append(project.id)
        return list(dict.fromkeys(ids))
    except Exception:
        logger.exception(
            "Could not expand parent project scope; using the exact project only.",
            extra={"event": "pipeline.scope.expand.failed", "project_id": project_id},
        )
        return [project_id]


def _criteria_resolve(state: PipelineState) -> dict[str, Any]:
    """Merge this turn's unit filters with the session's working search state."""
    if state.get("session_id") is None or not get_settings().search_criteria_enabled:
        criteria = search_criteria.merge_criteria(
            search_criteria.SearchCriteria(), search_criteria.parse_criteria(state["query"])
        )
        return _catalog_search_result(state, criteria)
    if not state.get("needs_inventory") and not is_search_refinement(state["query"]):
        # Not a refinement of the session's ongoing search, so this turn's criteria are
        # deliberately NOT merged into persisted session state (search_criteria.resolve) —
        # that stays reserved for actual refinements. But the query can still carry its own
        # standalone, parseable criteria worth a one-off catalogue lookup — e.g. "có biệt
        # thự không" parses to a unit_types=BIETTHU constraint even though it opens a new
        # topic rather than refining one. Passing a hardcoded empty SearchCriteria() here
        # (as before) silently discarded that and left catalog_offer_context unbuilt for
        # every first-mention product-type question, not just villas.
        standalone_criteria = search_criteria.merge_criteria(
            search_criteria.SearchCriteria(), search_criteria.parse_criteria(state["query"])
        )
        return _catalog_search_result(state, standalone_criteria)

    criteria, delta = search_criteria.resolve(state["session_id"], state["query"])
    conflict = search_criteria.detect_conflict(criteria)
    if conflict:
        tracing.step("criteria", ok=False, conflict=True)
        return {
            "criteria": criteria,
            "notice": conflict,
            "notice_emotion": MessageEmotion.RESPECTFUL,
        }

    # A comparative such as "giá mềm" has no deterministic meaning until an earlier
    # numeric bound exists. Ask one focused question instead of inventing a budget.
    if delta.unresolved_vague and criteria.is_empty():
        topic = delta.unresolved_vague[0]
        question = (
            "Anh/chị dự kiến ngân sách tối đa khoảng bao nhiêu ạ?"
            if topic == "giá"
            else "Anh/chị mong muốn diện tích tối thiểu khoảng bao nhiêu m² ạ?"
        )
        tracing.step("criteria", ok=False, unresolved=topic)
        return {
            "criteria": criteria,
            "notice": question,
            "notice_emotion": MessageEmotion.RESPECTFUL,
        }

    tracing.step("criteria", ok=True, constraint_count=len(criteria.constraints))
    return {
        "criteria": criteria,
        "needs_inventory": True,
        **_catalog_search_result(state, criteria),
    }


def _catalog_search_result(
    state: PipelineState, criteria: search_criteria.SearchCriteria
) -> dict[str, Any]:
    """Attach structured catalogue tiers for property-search questions."""
    if not state.get("needs_inventory") and criteria.is_empty():
        return {}
    offers = catalog_offer_service.search_offers(
        state.get("db"),
        state["query"],
        project_ids=state.get("resolved_project_ids") or None,
        excluded_project_ids=state.get("excluded_project_ids") or None,
        criteria=criteria,
    )
    tracing.step("catalog.search", offer_count=len(offers))
    return {
        "catalog_offers": offers,
        "catalog_offer_context": catalog_offer_service.format_offers(offers, criteria),
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
    started = time.perf_counter()

    session_id = state.get("session_id")
    stateful = session_id is not None and get_settings().search_criteria_enabled
    all_units: list[InventoryUnit] = []
    if (
        state.get("db") is not None
        and project_id
        and state.get("resolved_project_ids")
        and not has_exact_project_mapping(project_id)
    ):
        # Never relabel rows obtained through the '*' demo/default mapping as stock for a
        # named catalogue subdivision. The structured catalogue remains available below.
        tracing.step("tool.inventory", ok=False, skipped="no_exact_project_mapping")
        return {"inventory_failed": True, "inventory_units": [], "all_units": []}
    try:
        if stateful:
            all_units = fetch_units(project_id)
            criteria = state.get("criteria") or search_criteria.SearchCriteria()

            # Subdivision names are project data, so they can only be recognized after
            # the raw inventory arrives. Enrich the already-resolved logical turn without
            # adding a second undo snapshot.
            known = sorted({unit.subdivision for unit in all_units if unit.subdivision})
            enriched = search_criteria.merge_criteria(
                criteria, search_criteria.parse_criteria(state["query"], known)
            )
            conflict = search_criteria.detect_conflict(enriched)
            if conflict:
                return {
                    "criteria": enriched,
                    "all_units": all_units,
                    "notice": conflict,
                    "notice_emotion": MessageEmotion.RESPECTFUL,
                }
            if enriched != criteria:
                # `stateful` implies this, but spelling it out keeps the narrowing local
                # and protects a future edit from accidentally calling Redis with None.
                assert session_id is not None
                _, history = search_criteria.load(session_id)
                search_criteria.save(session_id, enriched, history)
                criteria = enriched
            units = apply_criteria(all_units, criteria)
        else:
            # Exact legacy path for callers without a session or when the feature flag is
            # off. Preserve the recent-human-query fallback used by non-session callers.
            context_queries = _inventory_context_queries(state.get("history"))
            units = (
                lookup_inventory(project_id, state["query"], context_queries)
                if context_queries
                else lookup_inventory(project_id, state["query"])
            )
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
        # Latency is recorded on the failure path too: a timeout and an instant refusal
        # are different faults, and only the duration tells them apart.
        tracing.step(
            "tool.inventory",
            ok=False,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        if state.get("retrieved_docs"):
            return {"inventory_failed": True, "inventory_units": [], "all_units": []}
        return {"inventory_failed": True, "notice": INVENTORY_UNAVAILABLE_MESSAGE}

    tracing.step(
        "tool.inventory",
        ok=True,
        unit_count=len(units),
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )
    # An empty `units` list is a valid answer ("no 2PN units left"), not a failure —
    # inventory_service keeps those two cases distinct.
    result: dict[str, Any] = {"inventory_units": units, "inventory_failed": False}
    if stateful:
        result.update({"all_units": all_units, "criteria": criteria})
    return result


def _criteria_diagnose(state: PipelineState) -> dict[str, Any]:
    """Explain an empty filtered set using leave-one-out counts over raw inventory."""
    if state.get("inventory_failed") or state.get("inventory_units"):
        return {}
    criteria = state.get("criteria")
    all_units = state.get("all_units") or []
    if criteria is None or not all_units:
        return {}
    diagnosis = search_criteria.diagnose_zero_results(all_units, criteria)
    if diagnosis is None:
        return {}
    tracing.step(
        "criteria.diagnose",
        active_count=len(diagnosis.active_constraints),
        option_count=len(diagnosis.relax_options),
    )
    return {"zero_result_diagnosis": diagnosis}


def _inventory_context_queries(history: list[dict] | None) -> list[str]:
    """Recent human inventory constraints, newest first, without AI-generated figures."""

    if not history:
        return []
    human_queries = [
        str(turn.get("content", "")).strip()
        for turn in reversed(history)
        if turn.get("sender") != MessageSender.AGENT and str(turn.get("content", "")).strip()
    ]
    # Two human turns cover the common chain: project/type -> area -> price. Keeping the
    # window deliberately small prevents an old customer requirement from resurfacing.
    return human_queries[:2]


def _generate(state: PipelineState) -> dict[str, Any]:
    """Generate an answer with citations from the collected context."""
    docs = state.get("retrieved_docs") or []
    # Exact tower identity/height/location questions are fully covered by the structured
    # catalogue record. Feeding aggregate PDF chunks too reintroduced "30-32 tầng" and
    # unrelated density/layout fields into an otherwise exact P4 answer. Mixed questions
    # retain the documents so price/policy/etc. can still be answered.
    prompt_docs = (
        []
        if state.get("catalog_context_complete") and catalog_context_service.is_tower_profile_query(state["query"])
        else docs
    )
    units = state.get("inventory_units") or []
    # A broad "find me a home" request means stock that can still be offered. Keep
    # unavailable rows in the pipeline state for diagnosis/audit, but do not expose them
    # to the generator unless the person explicitly asked for a status such as sold or
    # reserved. This is deterministic protection around the prompt rule: the model cannot
    # accidentally recommend an unavailable unit it never received.
    if units:
        criteria = state.get("criteria")
        if criteria is not None:
            status_requested = criteria.get(search_criteria.FIELD_STATUSES) is not None
        else:
            turn = search_criteria.parse_criteria(state["query"])
            status_requested = any(
                constraint.field == search_criteria.FIELD_STATUSES for constraint in turn.constraints
            )
        if not status_requested:
            units = [unit for unit in units if unit.status.strip().lower() == "available"]
    is_public = state.get("clearance", DocumentVisibility.INTERNAL) == DocumentVisibility.PUBLIC
    criteria = state.get("criteria") or search_criteria.SearchCriteria()
    inventory_coverage = format_preference_coverage(units, criteria)
    structured_context = "\n\n".join(
        part for part in (state.get("catalog_context") or "", inventory_coverage) if part
    )

    prompt = prompts.build_prompt(
        state["query"],
        prompt_docs,
        units,
        state.get("needs_inventory", False),
        state.get("inventory_failed", False),
        state.get("images") or [],
        state.get("history") or [],
        state.get("memory_profile") or "",
        is_public=is_public,
        correction=state.get("verifier_feedback") or "",
        lessons=state.get("reflection_lessons") or "",
        criteria_summary=search_criteria.format_criteria(criteria),
        zero_result=state.get("zero_result_diagnosis"),
        catalog_context=structured_context,
        catalog_offer_context=state.get("catalog_offer_context") or "",
        catalog_overview_context=state.get("catalog_overview_context") or "",
        floor_plan_towers_only=state.get("floor_plan_towers_only"),
    )
    quick_replies: list[str] = []
    listings: list[dict] = []
    suggested_questions: list[str] = []
    attempt = state.get("retry_count", 0) + 1
    started = time.perf_counter()

    parsed: prompts.ConsultAnswer | prompts.SaleAnswer | None
    try:
        # Structured output on the SAME call (schema-constrained decoding), not a second
        # LLM call — see prompts.ConsultAnswer/SaleAnswer. Both audiences are structured
        # now: INTERNAL moved off plain generate_text once it gained follow-up suggestions
        # to render, and it carries no quick_replies (see SaleAnswer for why).
        if is_public:
            parsed = generate_json(prompt, prompts.ConsultAnswer, system_instruction=prompts.SYSTEM_INSTRUCTION_PUBLIC)
        else:
            parsed = generate_json(prompt, prompts.SaleAnswer, system_instruction=prompts.SYSTEM_INSTRUCTION)
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
        tracing.step(
            "generate",
            attempt=attempt,
            ok=False,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return {"notice": GENERATION_ERROR_MESSAGE}

    if parsed is None:
        # Same fail-closed posture as verifier_service: a consult call that returns
        # nothing parseable is a generation failure, not an empty answer.
        logger.warning(
            "Consult LLM returned no parseable answer.",
            extra={"event": "pipeline.generate.unparseable", "project_id": state.get("project_id")},
        )
        tracing.step(
            "generate",
            attempt=attempt,
            ok=False,
            empty=True,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return {"notice": GENERATION_ERROR_MESSAGE}

    answer = parsed.text
    suggested_questions = parsed.suggested_questions
    # Only the customer-facing schema carries these; SaleAnswer has no such field.
    quick_replies = getattr(parsed, "quick_replies", [])
    # Both schemas carry `listings` now (see prompts.SaleAnswer) — a Sale asking the same
    # recommendation question a customer would ask gets the same photo-carrying cards back.
    if isinstance(parsed, prompts.ConsultAnswer | prompts.SaleAnswer):
        listings = _resolve_listing_images(state.get("db"), parsed.listings)

    # Strip before checking for emptiness: an answer made up of only Markdown characters
    # renders as blank on screen, so it must fall into the error branch instead of
    # sending the Sale an empty chat bubble.
    answer = strip_markdown(answer)

    if not answer:
        tracing.step(
            "generate",
            attempt=attempt,
            ok=False,
            empty=True,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return {"notice": GENERATION_ERROR_MESSAGE}

    answer = drop_image_denials(answer, state.get("images") or [])
    answer = drop_false_image_confirmations(answer, state.get("images") or [])

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
        # Whether reflection memory contributed to this attempt, so the eval set can ask
        # whether lessons actually reduce repeat failures rather than just costing tokens.
        with_lessons=bool(state.get("reflection_lessons")),
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )
    return {
        "draft_answer": answer,
        "citations": _citations_for(prompt_docs, answer=answer),
        "quick_replies": quick_replies,
        "listings": listings,
        "suggested_questions": suggested_questions,
        # `images` (state["images"], set earlier by _image_tool, before listings existed
        # to check against) is the generic auto-attached strip — the same project's photos
        # a listing card already carries in its own image_urls. Showing both stacks two
        # redundant photo blocks for the same project on screen; the listing card wins.
        "images": [] if listings else state.get("images") or [],
    }


def _resolve_listing_images(db: Session | None, listings: list["prompts.PropertyListing"]) -> list[dict]:
    """Attach real subdivision photos and amenities to each model-proposed listing.

    The model only ever supplies text fields (project_name, unit_type, area_range,
    price_range) — never an image URL or an amenity name, so it cannot hallucinate either.
    This resolves the project the same way `answer_images_service.resolve_project_id`
    already does for memory/images, then picks a few photos matching the unit type (falling
    back to the subdivision's own overview shots) via `select_listing_images`, and a few
    named amenities straight from the catalogue record via `select_listing_amenities`. A
    listing whose project can't be resolved is still kept, just with both empty — the
    frontend renders a placeholder rather than losing the listing entirely over that.
    """
    resolved: list[dict] = []
    for listing in listings:
        image_urls: list[str] = []
        amenities: list[str] = []
        project_id: str | None = None
        if db is not None:
            try:
                project_id = answer_images_service.resolve_project_id(db, listing.project_name)
                project = db.get(Project, project_id) if project_id else None
                if project is not None:
                    gallery = ((project.details or {}).get("images") or {}).get("gallery") or []
                    gallery = [url for url in gallery if isinstance(url, str)]
                    # Same normalisation as answer_images_service.collect_images — a stored
                    # gallery entry is often a bare MinIO object key with a stray leading
                    # slash, not a browser-loadable URL on its own.
                    image_urls = [
                        answer_images_service.public_gallery_url(url)
                        for url in answer_images_service.select_listing_images(
                            gallery, listing.unit_type, project_name=listing.project_name
                        )
                    ]
                    amenities = answer_images_service.select_listing_amenities(project)
            except Exception:
                logger.exception(
                    "Could not resolve a listing's photos/amenities; keeping the listing without them.",
                    extra={"event": "pipeline.listing_image.failed", "project_name": listing.project_name},
                )
        resolved.append(
            {
                "project_name": listing.project_name,
                "unit_type": listing.unit_type,
                "area_range": listing.area_range,
                "price_range": listing.price_range,
                "image_urls": image_urls,
                "amenities": amenities,
                "project_id": project_id,
                "unit_code": listing.unit_code,
                "status": listing.status,
            }
        )
    return resolved


_CITATION_TOKEN_PATTERN = re.compile(r"\d+(?:[.,]\d+)*|[^\W\d_]+(?:\+\d+)?", re.UNICODE)


def _citations_for(docs: list[dict], *, answer: str = "") -> list[dict]:
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
    return build_citations(_rank_citation_evidence(docs, answer))


def _rank_citation_evidence(docs: list[dict], answer: str) -> list[dict]:
    """Put the passage that best supports the generated claims first per document.

    ``build_citations`` intentionally emits one chip per source file. Retrieval order is
    not sufficient for choosing that chip's page: a broad overview can rank first while
    the answer's exact price or area came from a later table chunk. Shared numeric tokens
    are weighted more heavily than prose because they are the facts for which a precise
    page anchor matters most. Sorting is stable, so answers without useful overlap retain
    retrieval order.
    """
    answer_tokens = _citation_tokens(answer)
    if not answer_tokens:
        return docs

    def evidence_score(doc: dict) -> tuple[int, int, float]:
        shared = answer_tokens & _citation_tokens(str(doc.get("content") or ""))
        numeric = sum(any(character.isdigit() for character in token) for token in shared)
        lexical = len(shared) - numeric
        retrieval_score = doc.get("score")
        return (
            numeric,
            lexical,
            float(retrieval_score) if isinstance(retrieval_score, int | float) else 0.0,
        )

    return sorted(docs, key=evidence_score, reverse=True)


def _citation_tokens(text: str) -> set[str]:
    return set(_CITATION_TOKEN_PATTERN.findall(strip_diacritics(text)))


def _verify(state: PipelineState) -> dict[str, Any]:
    """The Verifier Agent scores the draft independently of Generate.

    Returns the three numeric criteria plus the structured verdict (`failure_mode`,
    `verifier_feedback`, `next_action`). The feedback is what `_generate` reads on a
    retry, so a regeneration is aimed at the specific defect rather than blind.
    """
    docs = state.get("retrieved_docs") or []
    if state.get("catalog_context_complete") and catalog_context_service.is_tower_profile_query(state["query"]):
        docs = []
    context = [doc["content"] for doc in docs]
    if state.get("catalog_context"):
        context.append(state["catalog_context"])
    if state.get("catalog_offer_context"):
        context.append(state["catalog_offer_context"])
    coverage = format_preference_coverage(
        state.get("inventory_units") or [],
        state.get("criteria") or search_criteria.SearchCriteria(),
    )
    if coverage:
        context.append(coverage)
    if state.get("catalog_overview_context"):
        context.append(state["catalog_overview_context"])
    context.extend(prompts.format_unit_for_verifier(unit) for unit in state.get("inventory_units") or [])
    diagnosis = state.get("zero_result_diagnosis")
    if diagnosis is not None:
        context.append(search_criteria.format_diagnosis_for_verifier(diagnosis))
    # Same history-expanded query as retrieval (see _retrieval_query) — otherwise the judge
    # sees a bare "có" as "the question" next to a correct, on-topic draft answer about
    # chiết khấu, marks it irrelevant to "có", and the pipeline discards a good answer for
    # the low-confidence fallback. The judge needs the same context a human reading the
    # transcript would have: what "có" is actually saying yes to.
    query = _retrieval_query(state["query"], state.get("history"))
    started = time.perf_counter()
    # Same reasoning as _risk_check: a recommendation's numbers now live in `listings`
    # cards, not in `draft_answer`'s prose (see prompts.PropertyListing). A Verifier that
    # only reads `draft_answer` sees a short, deliberately number-free lead-in sentence and
    # scores it "incomplete" for not naming the units it recommends — even though the
    # customer sees both the sentence and the cards together. Appending a compact summary
    # of the cards lets the judge score what the customer actually sees as one answer,
    # without touching `draft_answer` itself (that stays exactly what gets sent/stored).
    listings_summary = "; ".join(
        f"{listing.get('project_name', '')} {listing.get('unit_type', '')} "
        f"{listing.get('area_range', '')} {listing.get('price_range', '')}".strip()
        for listing in state.get("listings") or []
    )
    answer_for_verification = state.get("draft_answer", "")
    if listings_summary:
        answer_for_verification = f"{answer_for_verification}\n[Thẻ căn hộ kèm theo, khách đã thấy]: {listings_summary}"
    result = verifier_service.score_answer(query, answer_for_verification, context)

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

    if _reflection_enabled() and result.failure_mode is not verifier_service.FailureMode.NONE:
        # Learn from the rejection so a later question of the same shape gets the lesson
        # before generating, rather than re-earning it. Fails open inside.
        reflection_memory.record_lesson(
            query=state["query"],
            failure_mode=result.failure_mode.value,
            feedback=result.feedback,
            scope=state.get("reflection_scope"),
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
    """Touches price/commitment -> raise the HITL flag so the Sale must read and confirm.

    Scans `listings` alongside `draft_answer`: a recommendation's price/area now lives in
    those structured cards rather than in the prose text (see prompts.PropertyListing), and
    a risk check that only read `draft_answer` would miss it entirely — the exact class of
    answer this flag exists to catch.
    """
    listings_text = " ".join(
        f"{listing.get('price_range', '')} {listing.get('area_range', '')}" for listing in state.get("listings") or []
    )
    requires_hitl = risk_service.detect_commitment_risk(f"{state.get('draft_answer', '')} {listings_text}")
    tracing.step("risk_check", requires_hitl=requires_hitl)
    return {"requires_hitl": requires_hitl}


def _image_tool(state: PipelineState) -> dict[str, Any]:
    """Fetch the project photos that belong under this answer.

    Covers both routes in answer_images_service: photos a question explicitly asked to
    see, and photos attached automatically to illustrate an answer that only asked to
    know something. That service decides which applies and how strictly to filter.

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
        return {"images": [], "floor_plan_towers_only": None}

    started = time.perf_counter()
    context = "\n".join(
        f"{doc.get('title') or ''} {doc.get('content') or ''}" for doc in state.get("retrieved_docs") or []
    )
    # A pinned project_id is authoritative for an explicit "cho xem ảnh" request, or when
    # this turn's own retrieval actually grounded on something. But `_scope_resolve` also
    # fills `project_id` from the last project *named in conversation history* when the
    # current turn names none — trusting that for the auto-illustrate route on a turn that
    # retrieved nothing (a generic opener like "tư vấn cho tôi") attaches an earlier,
    # unrelated project's photo to an answer that never mentioned it. `collect_images`
    # still tries to resolve a project from the query text alone when project_id is None,
    # so an on-topic question ("giá The Beverly bao nhiêu") is unaffected either way.
    wants_explicit_images = answer_images_service.wants_images(state["query"])
    effective_project_id = state.get("project_id") if wants_explicit_images or context.strip() else None
    images = answer_images_service.collect_images(
        db, state["query"], context, project_id=effective_project_id
    )
    # None when the resolved project has real per-unit-type photos (nothing extra to say);
    # otherwise the tower codes of whatever tower-wide floor-plan sheet exists, so a
    # bedroom-count follow-up is not suggested where only a per-tower one has a photo —
    # see answer_images_service.floor_plan_only_towers.
    floor_plan_towers_only = answer_images_service.floor_plan_only_towers(
        db, state["query"], context, project_id=state.get("project_id")
    )
    tracing.step(
        "tool.images",
        ok=True,
        image_count=len(images),
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )
    return {"images": images, "floor_plan_towers_only": floor_plan_towers_only}


# --------------------------------------------------------------------------- routing


def _route_after_cache(state: PipelineState) -> str:
    return "hit" if state.get("used_cache") else "miss"


def _route_after_preflight(state: PipelineState) -> str:
    if state.get("notice"):
        return "stop"
    if state.get("answered_from_memory"):
        return "answer"
    return "continue"


def _route_after_retrieve(state: PipelineState) -> str:
    if state.get("notice"):
        return "stop"
    return "criteria_resolve"


def _route_after_criteria(state: PipelineState) -> str:
    if state.get("notice"):
        return "stop"
    return "tool_call" if state.get("needs_inventory") or is_search_refinement(state["query"]) else "generate"


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

    # A question about the conversation itself ("tôi vừa hỏi về phân khu nào") is answered
    # from the history block in the prompt, never from a document. Verify would score
    # faithfulness against retrieved documents that say nothing about what was asked two
    # turns ago — always 0.0, however correct the answer — and bury it under
    # "Không đủ thông tin, liên hệ Admin." Same reasoning as the images branch above:
    # there is nothing here for Verify to check against.
    #
    # Only applies once there IS history: without it the model has nothing to recall, and
    # whatever it produces should still face the normal checks rather than skip them.
    if state.get("history") and is_conversation_meta_query(state["query"]):
        tracing.step("route.after_generate", decision="skip_verify", reason="conversation_meta_query")
        return "risk_check"

    # No documents, no inventory units — the only way Generate is reached with both empty
    # is the "nothing specific was asked for" fallthrough in _retrieve (see
    # names_specific_document_topic there). Verify scores faithfulness against context
    # that doesn't exist, which is always 0.0 regardless of answer quality — that would
    # send every ordinary "tư vấn giúp em" opener through a retry and then the low-
    # confidence wall, exactly the canned-answer problem this fallthrough exists to avoid.
    # Same reasoning as the images branch above: nothing here for Verify to check.
    if (
        not state.get("retrieved_docs")
        and not state.get("inventory_units")
        and not state.get("zero_result_diagnosis")
        and not state.get("catalog_context")
        and not state.get("catalog_offer_context")
    ):
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

    graph.add_node("preflight", _preflight)
    graph.add_node("scope_resolve", _scope_resolve)
    graph.add_node("cache_check", _cache_check)
    graph.add_node("retrieve", _retrieve)
    graph.add_node("criteria_resolve", _criteria_resolve)
    graph.add_node("tool_call", _tool_call)
    graph.add_node("criteria_diagnose", _criteria_diagnose)
    graph.add_node("generate", _generate)
    graph.add_node("verify", _verify)
    graph.add_node("risk_check", _risk_check)
    graph.add_node("image_tool", _image_tool)
    graph.add_node("bump_retry", _bump_retry)
    graph.add_node("low_confidence", _low_confidence)

    graph.add_edge(START, "preflight")
    graph.add_conditional_edges(
        "preflight",
        _route_after_preflight,
        {"stop": END, "answer": END, "continue": "scope_resolve"},
    )
    graph.add_edge("scope_resolve", "cache_check")
    graph.add_conditional_edges("cache_check", _route_after_cache, {"hit": END, "miss": "retrieve"})
    graph.add_conditional_edges("retrieve", _route_after_retrieve, {"stop": END, "criteria_resolve": "criteria_resolve"})
    graph.add_conditional_edges(
        "criteria_resolve", _route_after_criteria, {"stop": END, "tool_call": "tool_call", "generate": "image_tool"}
    )
    graph.add_conditional_edges("tool_call", _route_after_tool_call, {"stop": END, "generate": "criteria_diagnose"})
    graph.add_edge("criteria_diagnose", "image_tool")
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
    history: list[dict] | None = None,
    memory_profile: str = "",
    clearance: DocumentVisibility = DocumentVisibility.INTERNAL,
    session_id: int | None = None,
    reflection_scope: str | None = None,
    memory_profile_data: memory_service.UserProfile | None = None,
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

    tracing.start_run(query_len=len(query), project_id=project_id, clearance=str(clearance))
    try:
        return _run_traced(
            query,
            project_id,
            db,
            history,
            memory_profile,
            clearance,
            session_id,
            reflection_scope,
            memory_profile_data,
        )
    finally:
        # In a `finally` so a trace is still written when the graph raises. The outcome
        # fields are read off the result inside `_run_traced`; this only guarantees the
        # record is closed and flushed exactly once per run.
        tracing.finish()


def _run_traced(
    query: str,
    project_id: str | None,
    db: Session | None,
    history: list[dict] | None,
    memory_profile: str,
    clearance: DocumentVisibility,
    session_id: int | None,
    reflection_scope: str | None,
    memory_profile_data: memory_service.UserProfile | None,
) -> PipelineResult:
    """The body of `run_pipeline`, split out so tracing can wrap every exit path."""
    # Preserve the legacy one-argument call when no namespace is requested. Besides
    # keeping older callers/mocks compatible, it makes the default global behaviour
    # explicit; Sale consultation sessions take the scoped branch.
    reflection_lessons = (
        _lessons_for(query, reflection_scope) if reflection_scope is not None else _lessons_for(query)
    )
    initial: PipelineState = {
        "query": query.strip(),
        "session_id": session_id,
        "project_id": project_id,
        "resolved_project_ids": [],
        "excluded_project_ids": [],
        "memory_profile": memory_profile,
        "memory_profile_data": memory_profile_data or memory_service.UserProfile(),
        "reflection_lessons": reflection_lessons,
        "reflection_scope": reflection_scope,
        "clearance": clearance,
        "history": (history or [])[-MAX_HISTORY_MESSAGES:],
        "retrieved_docs": [],
        "catalog_context": "",
        "catalog_context_complete": False,
        "catalog_offers": [],
        "catalog_offer_context": "",
        "catalog_overview_context": "",
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
        # Photos still ride along — but only for a genuine decline (low confidence/empty
        # state): they were requested explicitly and assert nothing, so withholding them
        # because the *text* could not be verified helps nobody. RETRIEVAL_ERROR_MESSAGE/
        # GENERATION_ERROR_MESSAGE are different in kind — a real system failure (Gemini
        # down/rate-limited, retrieval broken), not a considered decline — and showing
        # "temporarily unavailable" next to a photo strip reads as a broken, half-working
        # reply instead of a clean failure the asker knows to just retry.
        notice_is_system_failure = notice in (RETRIEVAL_ERROR_MESSAGE, GENERATION_ERROR_MESSAGE)
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
            images=[] if notice_is_system_failure else state.get("images") or [],
            # Carried even here — especially here. A declined answer is the case Admin most
            # needs to diagnose, and "which failure mode" is the whole diagnosis.
            failure_mode=state.get("failure_mode"),
            verifier_feedback=state.get("verifier_feedback"),
            emotion=state.get("notice_emotion", MessageEmotion.REGRETFUL),
        )

    result = PipelineResult(
        draft_answer=state.get("draft_answer", ""),
        citations=state.get("citations") or [],
        quick_replies=state.get("quick_replies") or [],
        listings=state.get("listings") or [],
        suggested_questions=state.get("suggested_questions") or [],
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

    # Mid-conversation answers are never written to the cache, mirroring the read-side
    # guard in `_cache_check`: the key would be the bare follow-up text, while the answer
    # only makes sense given the turns before it. Storing "còn 3PN thì sao?" would poison
    # the cache for every later session asking those same words.
    # `memory_profile` is excluded for the same reason: the answer was shaped by one
    # person's remembered preferences, so it is not a safe generic answer to replay.
    active_criteria = state.get("criteria")
    if (
        not result.used_cache
        and not initial["history"]
        and not memory_profile
        and (active_criteria is None or active_criteria.is_empty())
    ):
        _store_cache(query, result, state.get("project_id"), clearance)

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
    """Cache only answers that pass the Verifier and carry nothing question-specific.

    Price-touching answers ARE cached. They used to be refused outright, on the grounds
    that RiskCheck had to re-run for the HITL card to appear — but a cache hit routes
    straight to END, so the fix is to re-run RiskCheck there (see `_cache_check`), not to
    refuse the entry. Refusing it emptied the cache of nearly every real answer this
    corpus produces: in practice the cache collection was never created at all.

    Answers carrying photos are never cached either. The cache matches on meaning, and
    "cho xem hình ảnh The Palma" and "cho xem mặt bằng The Palma" are close enough to
    collide — which served the whole gallery to someone who asked only for floor plans.
    The photo set is chosen per question, so it cannot be shared between two questions.

    Keyed off `result.images` rather than off `wants_images(query)`: photos now also ride
    along automatically on questions that never asked for any (see
    answer_images_service's automatic route), and those are just as topic-specific — the
    amenity shots attached to "tiện ích có gì" must not be replayed under a cache-matched
    "mặt bằng thế nào".
    """
    if result.verifier_score < _threshold():
        return

    if result.images:
        return

    # Same reasoning as images, one step further: `listings` are the specific units that
    # matched THIS question, and `CachedAnswer` has no field to carry them. Cached, the
    # answer would come back saying "em gợi ý lựa chọn sau" above an empty space — and a
    # near-match ("còn căn 2PN nào" vs "còn căn 3PN nào") would show the wrong units.
    if result.listings:
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


def _reflection_enabled() -> bool:
    """Read at call time, for the same reason as `_threshold`."""
    from backend.core.config import get_settings

    return get_settings().reflection_memory_enabled


def _lessons_for(query: str, scope: str | None = None) -> str:
    """Lessons from earlier mistakes that apply to this question, rendered for the prompt.

    Never raises: reflection memory is an improvement layer, and a Redis problem here must
    cost the lesson, not the answer.
    """
    if not _reflection_enabled():
        return ""

    try:
        return reflection_memory.format_lessons(reflection_memory.relevant_lessons(query, scope=scope))
    except Exception:  # pragma: no cover - defensive; the service already fails open
        logger.warning(
            "Doc reflection memory that bai; tra loi khong kem bai hoc nao.",
            exc_info=True,
            extra={"event": "pipeline.reflection.failed"},
        )
        return ""
