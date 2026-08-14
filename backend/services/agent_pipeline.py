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
from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.core.enums import DocumentVisibility
from backend.core.gemini_client import generate_text
from backend.services import cache_service, risk_service, verifier_service
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
# The order of these blocks is deliberate and should not be reshuffled: role -> depth ->
# structure -> format -> grounding constraints. A model reading "senior real-estate
# consultant" slides easily into a sales pitch and fills in market figures it "knows"
# from pre-training, so the grounding-constraints block must come last and be phrased
# absolutely, so it overrides every requirement stated above it.
_SYSTEM_INSTRUCTION = (
    "Bạn là chuyên viên tư vấn bất động sản cao cấp với nhiều năm kinh nghiệm bán hàng dự án, "
    "đang hỗ trợ đồng nghiệp trong đội sale chuẩn bị nội dung tư vấn cho khách hàng. Đồng nghiệp "
    "sẽ dùng thẳng câu trả lời của bạn để nói với khách, nên nội dung phải đủ đầy đủ để họ không "
    "phải hỏi lại lần thứ hai.\n"
    "\n"
    "CHIỀU SÂU CHUYÊN MÔN — đây là yêu cầu quan trọng nhất về nội dung:\n"
    "- Trả lời đầy đủ, chi tiết, khai thác hết thông tin liên quan có trong ngữ cảnh. Thà dài mà "
    "đủ còn hơn ngắn mà Sale phải hỏi lại. Độ dài tự nhiên thường là 6-12 câu; câu hỏi phức tạp "
    "(so sánh nhiều loại căn, chính sách nhiều giai đoạn) thì viết dài hơn.\n"
    "- Không chỉ đưa con số: giải thích con số đó áp dụng cho loại căn / phân khu / tòa nào, "
    "kèm điều kiện gì, tính trên diện tích thông thủy hay tim tường, đã gồm hay chưa gồm VAT, "
    "phí bảo trì, nội thất.\n"
    "- Nêu đủ các thông tin đi kèm mà một chuyên viên giỏi luôn chủ động nói ra khi ngữ cảnh có: "
    "giá và đơn giá/m², diện tích, hướng, tầng, tiến độ thanh toán, chiết khấu và điều kiện hưởng, "
    "chính sách vay - ân hạn nợ gốc - hỗ trợ lãi suất, thời hạn áp dụng, thời điểm bàn giao, "
    "hình thức sở hữu, tình trạng pháp lý.\n"
    "- Chủ động cảnh báo những điểm Sale dễ tư vấn sai: điều kiện kèm theo, mốc thời gian hết hạn "
    "chính sách, khoản chi phí khách thường không lường trước, khác biệt giữa các phiên bản tài liệu.\n"
    "- Khi có thể so sánh (giữa các loại căn, các phương án thanh toán), hãy so sánh — đó là giá trị "
    "tư vấn thật sự, không chỉ tra cứu.\n"
    "- Nếu câu hỏi có phần chưa rõ (chưa nói rõ tòa, loại căn, phương án thanh toán), cứ trả lời "
    "đầy đủ cho các trường hợp phổ biến trong ngữ cảnh, rồi nêu rõ cần khách xác nhận thêm điều gì.\n"
    "\n"
    "CẤU TRÚC VÀ GIỌNG VĂN:\n"
    "- Viết như đang trao đổi với đồng nghiệp có nghề: thành câu, có mạch, tự nhiên, không máy móc.\n"
    "- Mở đầu bằng câu trả lời trực tiếp cho đúng điều Sale hỏi, rồi mới triển khai chi tiết. "
    "Không bắt Sale đọc hết đoạn mới thấy con số.\n"
    "- Trình bày theo logic tư vấn: thông tin chính (giá, diện tích, loại căn) trước, rồi điều kiện "
    "và chính sách đi kèm, cuối cùng là lưu ý và phần còn thiếu dữ liệu.\n"
    "- Dùng văn xuôi cho phần giải thích. Chỉ tách gạch đầu dòng khi liệt kê nhiều mục song song "
    "cần đối chiếu (bảng giá theo loại căn, các mốc thanh toán, các gói chính sách) — khi đó liệt kê "
    "đầy đủ các mục có trong ngữ cảnh, không cắt bớt.\n"
    "- Nếu số mục quá nhiều để liệt kê hết, nhóm theo tiêu chí (theo loại căn, theo khoảng giá, "
    "theo tòa), nêu dải giá trị của từng nhóm và tổng số mục, thay vì bỏ lửng.\n"
    "- Dùng thuật ngữ đúng chuẩn ngành: căn 2PN, diện tích thông thủy, bàn giao thô/hoàn thiện, "
    "chiết khấu, ân hạn nợ gốc, sở hữu lâu dài, tiến độ thanh toán.\n"
    "- Mọi số liệu phải kèm đơn vị (m², tỷ đồng, triệu đồng/m², %) và kèm tên tài liệu nguồn "
    "cho các con số quan trọng.\n"
    "\n"
    "ĐỊNH DẠNG — giao diện hiển thị văn bản thuần, KHÔNG render Markdown:\n"
    "- Tuyệt đối không dùng ký tự Markdown: không **in đậm**, không *nghiêng*, không ###, "
    "không bảng, không khối mã. Chúng sẽ hiện nguyên dấu sao trên màn hình và trông rất lỗi.\n"
    "- Nếu cần gạch đầu dòng, mỗi dòng bắt đầu bằng '- ' rồi viết thẳng nội dung. Không lồng "
    "gạch đầu dòng nhiều cấp.\n"
    "- Cần nhấn mạnh thì đặt thông tin đó vào đầu câu, không tô đậm.\n"
    "- Tách đoạn bằng dòng trống để dễ đọc khi câu trả lời dài.\n"
    "- Không chào hỏi dài dòng, không văn quảng cáo sáo rỗng, không emoji.\n"
    "\n"
    "RÀNG BUỘC BẮT BUỘC — quan trọng hơn mọi yêu cầu về chiều sâu và phong cách ở trên:\n"
    "- CHỈ dùng thông tin có trong NGỮ CẢNH được cung cấp. Kiến thức bên ngoài về thị trường, "
    "chủ đầu tư hay dự án khác đều KHÔNG được dùng, kể cả khi bạn chắc chắn.\n"
    "- Tuyệt đối không suy diễn, không nội suy, không làm tròn hay ước lượng giá, diện tích, "
    "tiến độ, chính sách khi ngữ cảnh không ghi rõ. Không tự tính đơn giá/m² hay tổng giá nếu "
    "ngữ cảnh không cho đủ dữ kiện.\n"
    "- Không hứa hẹn, không cam kết thay chủ đầu tư (giữ chỗ, chắc chắn tăng giá, cam kết lợi nhuận...).\n"
    "- Nếu ngữ cảnh thiếu thông tin để trả lời, nói thẳng phần nào chưa có dữ liệu và đề nghị "
    "kiểm tra lại với Admin — không lấp đầy bằng phỏng đoán. Một câu trả lời đầy đủ gồm cả việc "
    "chỉ rõ ranh giới của dữ liệu hiện có.\n"
    "- Khi ngữ cảnh có nhiều số liệu mâu thuẫn, nêu rõ sự khác biệt kèm nguồn và thời điểm của "
    "từng tài liệu, thay vì tự chọn một số."
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
    """Function Calling into the internal inventory API for constantly changing data."""
    project_id = state.get("project_id")

    if not project_id:
        # Without knowing which project's inventory to query there is nothing to look up.
        # Return the inventory message rather than quietly answering from static docs —
        # unit counts in a PDF are stale by definition.
        if state.get("retrieved_docs"):
            return {"inventory_failed": True, "inventory_units": []}
        return {"inventory_failed": True, "notice": INVENTORY_UNAVAILABLE_MESSAGE}

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
    return "stop" if state.get("notice") else "verify"


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
    graph.add_node("bump_retry", _bump_retry)
    graph.add_node("low_confidence", _low_confidence)

    graph.add_edge(START, "cache_check")
    graph.add_conditional_edges("cache_check", _route_after_cache, {"hit": END, "miss": "retrieve"})
    graph.add_conditional_edges(
        "retrieve", _route_after_retrieve, {"stop": END, "tool_call": "tool_call", "generate": "generate"}
    )
    graph.add_conditional_edges("tool_call", _route_after_tool_call, {"stop": END, "generate": "generate"})
    graph.add_conditional_edges("generate", _route_after_generate, {"stop": END, "verify": "verify"})
    graph.add_conditional_edges(
        "verify",
        _route_after_verify,
        {"risk_check": "risk_check", "retry": "bump_retry", "low_confidence": "low_confidence"},
    )
    graph.add_edge("bump_retry", "generate")
    graph.add_edge("low_confidence", END)
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


def run_pipeline(query: str, project_id: str | None = None) -> PipelineResult:
    """Entry point for the Sale chat flow.

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
        return PipelineResult(notice, [], 0.0, False)

    result = PipelineResult(
        draft_answer=state.get("draft_answer", ""),
        citations=state.get("citations") or [],
        verifier_score=state.get("verifier_score", 0.0),
        requires_hitl=state.get("requires_hitl", False),
        used_cache=state.get("used_cache", False),
        faithfulness=state.get("faithfulness"),
        answer_relevancy=state.get("answer_relevancy"),
    )

    if not result.used_cache:
        _store_cache(query, result, project_id)

    return result


def _store_cache(query: str, result: PipelineResult, project_id: str | None) -> None:
    """Cache only clean answers: above the Verifier threshold and free of price/commitment.

    Price-touching answers must re-run RiskCheck every time so the Sale always gets the
    HITL card — serving them from cache would skip that mandatory confirmation step.
    """
    if result.requires_hitl or result.verifier_score < _threshold():
        return

    cache_service.store_cache(
        query=query,
        answer=result.draft_answer,
        citations=result.citations,
        verifier_score=result.verifier_score,
        project_id=project_id,
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


def _build_citations(docs: list[dict]) -> list[dict]:
    """Normalise citations into the exact shape of the `Citation` schema.

    Filtering is mandatory: `document_id` from a Qdrant payload may be None, while
    `Citation` declares a non-nullable `document_id: int` — letting one through becomes a
    ValidationError 500 while serializing the response. `content`/`score` are dropped too,
    since the schema does not accept those fields.
    """
    citations: list[dict] = []
    seen: set[tuple[int, Any]] = set()

    for doc in docs:
        document_id = doc.get("document_id")
        if document_id is None:
            continue

        key = (document_id, doc.get("page"))
        if key in seen:
            continue
        seen.add(key)

        citations.append(
            {
                "document_id": document_id,
                "title": doc.get("title") or "Tài liệu",
                "page": doc.get("page"),
            }
        )

    return citations


def _build_prompt(
    query: str,
    docs: list[dict],
    units: list[InventoryUnit],
    needs_inventory: bool,
    inventory_failed: bool,
) -> str:
    sections = [f"CÂU HỎI CỦA SALE:\n{query}"]

    if docs:
        context = "\n\n".join(_format_doc_for_prompt(index, doc) for index, doc in enumerate(docs, start=1))
        sections.append(f"NGỮ CẢNH TỪ TÀI LIỆU DỰ ÁN:\n{context}")

    if needs_inventory and not inventory_failed:
        sections.append(f"TỒN KHO REAL-TIME:\n{_format_units(units)}")

    sections.append(
        "Trả lời câu hỏi trên với tư cách chuyên viên tư vấn dự án, đầy đủ và chi tiết như đang "
        "brief cho đồng nghiệp sắp gặp khách. Viết văn xuôi tự nhiên, văn bản thuần, không dùng "
        "ký tự Markdown nào (không dấu sao, không thăng).\n"
        "- Bám sát đúng loại căn / phân khu / tòa mà câu hỏi nhắc tới, đừng trả lời chung chung "
        "cho cả dự án khi Sale đang hỏi một loại căn cụ thể.\n"
        "- Rà lại toàn bộ ngữ cảnh ở trên và đưa vào mọi chi tiết liên quan tới câu hỏi: con số, "
        "điều kiện áp dụng, mốc thời gian, chính sách và ưu đãi đi kèm. Đừng dừng lại ở một con số "
        "trần trụi khi ngữ cảnh còn nói thêm điều kiện.\n"
        "- Dẫn tên tài liệu nguồn (và trang nếu có) cho từng số liệu quan trọng.\n"
        "- Nêu rõ phần nào ngữ cảnh chưa có dữ liệu thay vì suy đoán, và gợi ý Sale cần xác nhận "
        "thêm điều gì với khách hoặc với Admin."
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
