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

from backend.core.enums import DocumentVisibility
from backend.core.gemini_client import generate_text
from backend.services import answer_images_service, cache_service, risk_service, verifier_service
from backend.services.inventory_service import InventoryApiError, InventoryUnit, lookup_inventory
from backend.services.rag_service import RetrievalError, retrieve
from backend.utils.text import strip_diacritics, strip_markdown

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

# Signals that a question needs the real-time inventory table rather than static docs.
# Deliberately keyed on *inventory intent* instead of merely spotting a unit type
# ("2PN"): "giá căn 2PN?" mentions a unit type, but its answer lives in the ingested
# price list.
_REALTIME_INTENT_KEYWORDS = (
    "còn căn",
    "còn bao nhiêu",
    "còn không",
    "còn trống",
    "trống không",
    "tồn kho",
    "bảng hàng",
    "sẵn hàng",
    "còn hàng",
    "hết hàng",
    "đã bán",
    "chưa bán",
    "giữ chỗ",
    "căn nào",
    "suất nào",
)

_DOCUMENT_INTENT_KEYWORDS = (
    "chinh sach",
    "chính sách",
    "csbh",
    "chiet khau",
    "chiết khấu",
    "uu dai",
    "ưu đãi",
    "khuyen mai",
    "khuyến mại",
    "thanh toan",
    "thanh toán",
    "phap ly",
    "pháp lý",
    "hop dong",
    "hợp đồng",
    "bang gia",
    "bảng giá",
)
# Block order is deliberate and should not be reshuffled: role -> length -> layout ->
# required content -> format -> grounding constraints. A model reading "senior
# real-estate consultant" slides easily into a sales pitch and fills in market figures
# it "knows" from pre-training, so the grounding block comes last and is phrased
# absolutely, overriding every requirement above it.
#
# The length ceiling sits near the top on purpose. An earlier revision opened with
# "answer fully, in detail, better long than incomplete" and produced walls of prose a
# Sale could not skim in front of a customer. The cap has to be read before the list of
# what must be covered, not after it.
_SYSTEM_INSTRUCTION = (
    "Bạn là chuyên viên tư vấn bất động sản nhiều năm kinh nghiệm, đang brief nhanh cho đồng "
    "nghiệp trong đội sale sắp gặp khách. Họ đọc câu trả lời của bạn ngay trước mặt khách, nên "
    "phải nắm được ý trong vài giây.\n"
    "\n"
    "ĐỘ DÀI — ưu tiên hàng đầu:\n"
    "- Tối đa 6 gạch đầu dòng, mỗi dòng 1-2 câu. Câu hỏi đơn giản chỉ cần 2-3 dòng.\n"
    "- Ngắn nhưng không thiếu ý chính. Nếu phải cắt, giữ lại con số và điều kiện kèm theo, "
    "bỏ phần diễn giải.\n"
    "- Không lặp lại câu hỏi, không mở bài, không tóm tắt lại ở cuối, không khuyên chung chung "
    "kiểu 'nên tư vấn kỹ cho khách'.\n"
    "\n"
    "TRÌNH BÀY — luôn dùng gạch đầu dòng:\n"
    "- Mỗi ý một dòng, bắt đầu bằng '- '. Không viết đoạn văn xuôi dài.\n"
    "- Dòng đầu tiên chứa con số hoặc thông tin chính mà Sale hỏi.\n"
    "- Mỗi dòng nêu trọn một ý, không cắt ngang câu sang dòng khác.\n"
    "- Không lồng gạch đầu dòng nhiều cấp.\n"
    "\n"
    "NỘI DUNG BẮT BUỘC — dù ngắn vẫn phải có, khi ngữ cảnh cung cấp:\n"
    "- Con số chính (giá, diện tích, tiến độ) và nó áp dụng cho loại căn / phân khu / tòa nào.\n"
    "- Điều kiện đi kèm: đã gồm hay chưa gồm VAT, tính trên diện tích nào, điều kiện hưởng "
    "chiết khấu, mốc thời gian hết hạn chính sách.\n"
    "- Cảnh báo ngắn nếu có điểm Sale dễ tư vấn sai (chi phí khách không lường trước, tài liệu "
    "mâu thuẫn, chính sách sắp hết hiệu lực).\n"
    "- Phần nào ngữ cảnh chưa có dữ liệu thì nói thẳng trong một dòng.\n"
    "- Chỉ nêu thông tin liên quan trực tiếp tới câu hỏi. Không kể thêm tiện ích, chính sách hay "
    "loại căn khác mà Sale không hỏi.\n"
    "\n"
    "GIỌNG VĂN:\n"
    "- Như nói với đồng nghiệp có nghề: thành câu, tự nhiên, không máy móc.\n"
    "- Thuật ngữ đúng chuẩn ngành: căn 2PN, diện tích thông thủy, bàn giao thô/hoàn thiện, "
    "chiết khấu, ân hạn nợ gốc, sở hữu lâu dài, tiến độ thanh toán.\n"
    "- Số liệu kèm đơn vị (m², tỷ đồng, triệu đồng/m², %).\n"
    "- Giao diện đã hiện danh sách tài liệu nguồn ngay dưới câu trả lời, nên KHÔNG viết tên tài "
    "liệu, số trang hay số thứ tự khối ngữ cảnh vào trong câu trả lời. Tuyệt đối không mở đầu "
    "dòng bằng [1], [2], và không viết '(theo trang 3)' hay '(Tồn kho real-time)'.\n"
    "- Không lặp lại thông tin đã nêu ở dòng trước. Nếu cả nhóm cùng một trạng thái hay một "
    "loại căn, nói một lần ở dòng mở đầu rồi thôi.\n"
    "- Trạng thái tồn kho viết bằng tiếng Việt (còn trống, đã đặt chỗ, đã bán), không để nguyên "
    "mã tiếng Anh của API.\n"
    "\n"
    "ĐỊNH DẠNG — giao diện hiển thị văn bản thuần, KHÔNG render Markdown:\n"
    "- Tuyệt đối không dùng ký tự Markdown: không **in đậm**, không *nghiêng*, không ###, "
    "không bảng, không khối mã. Chúng sẽ hiện nguyên dấu sao trên màn hình và trông rất lỗi.\n"
    "- Cần nhấn mạnh thì đặt thông tin đó ở đầu dòng, không tô đậm.\n"
    "- Không chào hỏi, không văn quảng cáo sáo rỗng, không emoji.\n"
    "\n"
    "RÀNG BUỘC BẮT BUỘC — quan trọng hơn mọi yêu cầu về độ dài và phong cách ở trên:\n"
    "- CHỈ dùng thông tin có trong NGỮ CẢNH được cung cấp. Kiến thức bên ngoài về thị trường, "
    "chủ đầu tư hay dự án khác đều KHÔNG được dùng, kể cả khi bạn chắc chắn.\n"
    "- Tuyệt đối không suy diễn, không nội suy, không làm tròn hay ước lượng giá, diện tích, "
    "tiến độ, chính sách khi ngữ cảnh không ghi rõ. Không tự tính đơn giá/m² hay tổng giá nếu "
    "ngữ cảnh không cho đủ dữ kiện.\n"
    "- Không hứa hẹn, không cam kết thay chủ đầu tư (giữ chỗ, chắc chắn tăng giá, cam kết lợi nhuận...).\n"
    "- Nếu ngữ cảnh thiếu thông tin, nói thẳng trong một dòng là chưa có dữ liệu và đề nghị kiểm "
    "tra với Admin — không lấp đầy bằng phỏng đoán, cũng không viết dài ra để che chỗ thiếu.\n"
    "- Khi ngữ cảnh có nhiều số liệu mâu thuẫn, nêu rõ sự khác biệt kèm nguồn của từng tài liệu, "
    "thay vì tự chọn một số."
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

    needs_inventory = _needs_inventory(query)
    needs_document_retrieval = _needs_document_retrieval(query)
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

    prompt = _build_prompt(
        state["query"],
        docs,
        units,
        state.get("needs_inventory", False),
        state.get("inventory_failed", False),
        state.get("images") or [],
    )

    try:
        answer = generate_text(prompt, system_instruction=_SYSTEM_INSTRUCTION)
    except Exception:
        logger.exception(
            "Sinh cau tra loi that bai.",
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

    answer = _drop_image_denials(answer, state.get("images") or [])

    return {"draft_answer": answer, "citations": _build_citations(docs)}


def _verify(state: PipelineState) -> dict[str, Any]:
    """The Verifier Agent scores Faithfulness/Relevancy, independently of Generate."""
    context = [doc["content"] for doc in state.get("retrieved_docs") or []]
    context.extend(_format_unit_for_verifier(unit) for unit in state.get("inventory_units") or [])
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


def _needs_inventory(query: str) -> bool:
    """Diacritic-insensitive matching: a Sale typing fast on a phone rarely uses accents.

    "con can 2pn nao trong khong" must be recognised as an inventory question exactly
    like its fully accented form — otherwise the Agent quietly answers with stale unit
    counts from a PDF.
    """
    normalized = strip_diacritics(query)
    return any(strip_diacritics(keyword) in normalized for keyword in _REALTIME_INTENT_KEYWORDS)


def _needs_document_retrieval(query: str) -> bool:
    """Keep policy/legal RAG independent from the live-inventory decision."""
    normalized = strip_diacritics(query)
    return (
        any(strip_diacritics(keyword) in normalized for keyword in _DOCUMENT_INTENT_KEYWORDS)
        or not _needs_inventory(query)
    )


# Phrases in which the model denies having images. It emits these even when told not to,
# because the retrieved PDFs genuinely contain no image files — it is describing its own
# context, not the screen. Prompting alone proved unreliable, so the line is removed.
_IMAGE_DENIAL_MARKERS = (
    "khong chua hinh anh",
    "khong co hinh anh",
    "khong co anh",
    "khong co tep anh",
    "khong co file anh",
    "chua co hinh anh",
    "chua co anh",
    "khong hien thi duoc anh",
    "khong co hinh anh truc quan",
    "hinh anh truc quan de hien thi",
    "xin anh",
)


def _drop_image_denials(answer: str, images: list[dict]) -> str:
    """Strip lines claiming there are no images, when there demonstrably are.

    Only runs when photos are attached, so an honest "chưa có ảnh cho hạng mục này" on a
    question that found none is left untouched. If every line is a denial, a plain factual
    line replaces them rather than returning an empty bubble.
    """
    if not images:
        return answer

    kept = [
        line
        for line in answer.splitlines()
        if not any(marker in strip_diacritics(line).lower() for marker in _IMAGE_DENIAL_MARKERS)
    ]
    cleaned = "\n".join(kept).strip()
    if cleaned:
        return cleaned

    return f"- Đang hiển thị {len(images)} ảnh {images[0].get('project_name') or 'dự án'} bên dưới."


def _build_citations(docs: list[dict]) -> list[dict]:
    """Normalise citations into the exact shape of the `Citation` schema.

    One chip per file, not per page: retrieval routinely returns several chunks of the
    same PDF, and listing "Bảng giá · tr.1, Bảng giá · tr.2, Bảng giá · tr.10" told the Sale
    nothing they could act on while crowding the answer. The file name is the useful part.

    Deduplication is by title rather than by `document_id` on purpose: the same file
    uploaded twice becomes two documents with two ids, and keying on the id would put the
    identical name on screen twice — exactly the clutter this is meant to remove.

    Filtering is mandatory: `document_id` from a Qdrant payload may be None, while
    `Citation` declares a non-nullable `document_id: int` — letting one through becomes a
    ValidationError 500 while serializing the response. `content`/`score` are dropped too,
    since the schema does not accept those fields.
    """
    citations: list[dict] = []
    seen: set[str] = set()

    for doc in docs:
        document_id = doc.get("document_id")
        if document_id is None:
            continue

        title = doc.get("title") or "Tài liệu"
        key = title.strip().casefold()
        if key in seen:
            continue
        seen.add(key)

        citations.append({"document_id": document_id, "title": title})

    return citations


def _build_prompt(
    query: str,
    docs: list[dict],
    units: list[InventoryUnit],
    needs_inventory: bool,
    inventory_failed: bool,
    images: list[dict] | None = None,
) -> str:
    sections = [f"CÂU HỎI CỦA SALE:\n{query}"]

    if docs:
        context = "\n\n".join(_format_doc_for_prompt(index, doc) for index, doc in enumerate(docs, start=1))
        sections.append(f"NGỮ CẢNH TỪ TÀI LIỆU DỰ ÁN:\n{context}")

    if needs_inventory and not inventory_failed:
        sections.append(f"TỒN KHO REAL-TIME:\n{_format_units(units)}")

    sections.append(
        "Trả lời câu hỏi trên với tư cách chuyên viên tư vấn dự án, ngắn gọn và đúng trọng tâm "
        "như đang brief cho đồng nghiệp sắp gặp khách. Văn bản thuần, không dùng ký tự Markdown "
        "nào (không dấu sao, không thăng).\n"
        "- Trình bày bằng gạch đầu dòng, mỗi dòng bắt đầu bằng '- '. Tối đa 6 dòng.\n"
        "- Dòng đầu tiên trả lời thẳng điều Sale hỏi, kèm con số chính.\n"
        "- Bám đúng loại căn / phân khu / tòa mà câu hỏi nhắc tới, đừng trả lời chung chung cho "
        "cả dự án khi Sale đang hỏi một loại căn cụ thể.\n"
        "- Kèm điều kiện áp dụng của con số (VAT, diện tích tính theo, mốc thời gian) ngay trong "
        "dòng nêu con số đó, thay vì tách thành dòng riêng.\n"
        "- Không viết tên tài liệu, số trang hay số thứ tự khối ngữ cảnh ([1], [2]) vào câu trả "
        "lời — giao diện đã hiện phần nguồn riêng bên dưới.\n"
        "- Nếu ngữ cảnh chưa có dữ liệu cho phần nào, nói thẳng trong một dòng thay vì suy đoán."
    )

    if images:
        # The tool has already run, so this states a fact rather than a promise. Without it
        # the model reads "no images in the context" off its own prompt and tells the Sale
        # to ask Admin for pictures — printed directly above a strip of those pictures.
        project_name = images[0].get("project_name") or "dự án"
        sections.append(
            f"ẢNH ĐÃ ĐÍNH KÈM: {len(images)} ảnh {project_name} ĐANG hiển thị trên màn hình của "
            "Sale, ngay dưới câu trả lời này. CẤM tuyệt đối mọi câu phủ nhận điều đó — không viết "
            "'không có hình ảnh', 'không có tệp ảnh', 'tài liệu không chứa ảnh', 'không hiển thị "
            "được ảnh', và không bảo Sale hỏi Admin xin ảnh. Không mô tả từng ảnh. Phần chữ chỉ "
            "tóm tắt 2-3 dòng về hạng mục được hỏi dựa trên ngữ cảnh."
        )
    elif answer_images_service.wants_images(query):
        sections.append(
            "ẢNH: catalogue không có ảnh nào khớp yêu cầu này. Nói ngắn gọn trong một dòng là "
            "chưa có ảnh cho hạng mục được hỏi."
        )

    if needs_inventory and inventory_failed:
        sections.append(
            "LIVE INVENTORY STATUS: unavailable. Do not infer stock from project documents; "
            "state that live inventory could not be checked."
        )

    return "\n\n".join(sections)


def _format_doc_for_prompt(index: int, doc: dict) -> str:
    """One context block: index + document title + page so the LLM can cite down to the page."""
    title = doc.get("title") or "Tài liệu"
    page = doc.get("page")
    header = f"[{index}] {title}" + (f" (trang {page})" if page else "")
    return f"{header}\n{doc.get('content') or ''}"


def _format_units(units: list[InventoryUnit]) -> str:
    if not units:
        return "Hiện không còn căn nào khớp với yêu cầu."

    return "\n".join(
        f"- {unit.unit_code} | loại {unit.unit_type or 'không rõ'} | "
        f"giá {f'{unit.price:,.0f} VNĐ' if unit.price is not None else 'chưa có'} | {unit.status}"
        for unit in units
    )


def _format_unit_for_verifier(unit: InventoryUnit) -> str:
    """Give the verifier the same live facts that were supplied to the LLM."""
    return (
        f"Live inventory: {unit.unit_code}; type {unit.unit_type or 'unknown'}; "
        f"price {unit.price if unit.price is not None else 'unknown'}; status {unit.status}."
    )
