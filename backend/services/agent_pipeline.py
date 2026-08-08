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

from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.core.enums import DocumentVisibility
from backend.core.gemini_client import generate_text
from backend.services import cache_service, risk_service, verifier_service
from backend.services.inventory_service import InventoryApiError, InventoryUnit, lookup_inventory
from backend.services.rag_service import RetrievalError, retrieve
from backend.utils.text import strip_diacritics, strip_markdown

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

# Vai trò được mô tả trước, ràng buộc grounding đặt sau và diễn đạt tuyệt đối: model
# đọc "chuyên viên bất động sản" rất dễ trượt sang giọng chào hàng và tự bù số liệu
# thị trường mà nó "biết" từ pre-training. Giữ nguyên thứ tự này khi chỉnh sửa.
_SYSTEM_INSTRUCTION = (
    "Bạn là chuyên viên tư vấn bất động sản cao cấp, đang hỗ trợ đồng nghiệp trong đội sale "
    "chuẩn bị nội dung tư vấn cho khách hàng.\n"
    "\n"
    "PHONG CÁCH TRẢ LỜI:\n"
    "- Viết như đang nói với đồng nghiệp: thành câu, có mạch, tự nhiên. Ưu tiên văn xuôi liền mạch "
    "thay vì bổ nhỏ mọi thứ thành danh sách.\n"
    "- Mặc định trả lời bằng 2-5 câu văn xuôi. Chỉ tách gạch đầu dòng khi thực sự đang liệt kê "
    "nhiều mục song song cần đối chiếu (ví dụ bảng giá theo từng loại căn), và tối đa 5 dòng.\n"
    "- Khi ngữ cảnh có quá nhiều mục, đừng liệt kê hết: tóm tắt nhóm chính và nêu vài mục tiêu biểu, "
    "kết lại bằng tổng số. Sale cần nắm nhanh, không cần bản kê khai đầy đủ.\n"
    "- Dẫn dắt theo logic tư vấn: thông tin chính trước (giá, diện tích, loại căn), rồi điều kiện "
    "đi kèm, cuối cùng là lưu ý nếu có.\n"
    "- Dùng thuật ngữ đúng chuẩn ngành: căn 2PN, diện tích thông thủy, bàn giao thô/hoàn thiện, "
    "chiết khấu, ân hạn nợ gốc, sở hữu lâu dài.\n"
    "- Nêu số liệu kèm đơn vị (m², tỷ đồng, %).\n"
    "\n"
    "ĐỊNH DẠNG — giao diện hiển thị văn bản thuần, KHÔNG render Markdown:\n"
    "- Tuyệt đối không dùng ký tự Markdown: không **in đậm**, không *nghiêng*, không ###, "
    "không bảng, không khối mã. Chúng sẽ hiện nguyên dấu sao trên màn hình và trông rất lỗi.\n"
    "- Nếu cần gạch đầu dòng, mỗi dòng bắt đầu bằng '- ' rồi viết thẳng nội dung. Không lồng "
    "gạch đầu dòng nhiều cấp.\n"
    "- Cần nhấn mạnh thì đặt thông tin đó vào đầu câu, không tô đậm.\n"
    "- Không chào hỏi dài dòng, không văn quảng cáo sáo rỗng, không emoji.\n"
    "\n"
    "RÀNG BUỘC BẮT BUỘC — quan trọng hơn mọi yêu cầu về phong cách:\n"
    "- CHỈ dùng thông tin có trong NGỮ CẢNH được cung cấp. Kiến thức bên ngoài về thị trường, "
    "chủ đầu tư hay dự án khác đều KHÔNG được dùng, kể cả khi bạn chắc chắn.\n"
    "- Tuyệt đối không suy diễn, không nội suy, không làm tròn hay ước lượng giá, diện tích, "
    "tiến độ, chính sách khi ngữ cảnh không ghi rõ.\n"
    "- Không hứa hẹn, không cam kết thay chủ đầu tư (giữ chỗ, chắc chắn tăng giá, cam kết lợi nhuận...).\n"
    "- Nếu ngữ cảnh thiếu thông tin để trả lời, nói thẳng phần nào chưa có dữ liệu và đề nghị "
    "kiểm tra lại với Admin — không lấp đầy bằng phỏng đoán.\n"
    "- Khi ngữ cảnh có nhiều số liệu mâu thuẫn, nêu rõ sự khác biệt kèm nguồn thay vì tự chọn một số."
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


class PipelineState(TypedDict, total=False):
    """State threaded through the nodes — as described in ARCHITECTURE.md §3."""

    query: str
    project_id: str | None
    retrieved_docs: list[dict]
    needs_realtime: bool
    inventory_units: list[InventoryUnit]
    inventory_failed: bool
    draft_answer: str
    citations: list[dict]
    verifier_score: float
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

    try:
        hits = retrieve(query, DocumentVisibility.INTERNAL, state.get("project_id"), RETRIEVAL_TOP_K)
    except RetrievalError:
        return {"notice": RETRIEVAL_ERROR_MESSAGE}

    needs_realtime = _needs_realtime(query)

    if not hits and not needs_realtime:
        # No documents ingested yet and the question is not an inventory lookup ->
        # Empty State, not a system error.
        return {"notice": EMPTY_STATE_MESSAGE}

    return {"retrieved_docs": hits, "needs_realtime": needs_realtime}


def _tool_call(state: PipelineState) -> dict[str, Any]:
    """Function Calling into the internal inventory API for constantly changing data."""
    project_id = state.get("project_id")

    if not project_id:
        # Without knowing which project's inventory to query there is nothing to look up.
        # Return the inventory message rather than quietly answering from static docs —
        # unit counts in a PDF are stale by definition.
        return {"inventory_failed": True, "notice": INVENTORY_UNAVAILABLE_MESSAGE}

    try:
        units = lookup_inventory(project_id, state["query"])
    except InventoryApiError:
        return {"inventory_failed": True, "notice": INVENTORY_UNAVAILABLE_MESSAGE}

    # An empty `units` list is a valid answer ("no 2PN units left"), not a failure —
    # inventory_service keeps those two cases distinct.
    return {"inventory_units": units, "inventory_failed": False}


def _generate(state: PipelineState) -> dict[str, Any]:
    """Generate an answer with citations from the collected context."""
    docs = state.get("retrieved_docs") or []
    units = state.get("inventory_units") or []

    prompt = _build_prompt(state["query"], docs, units, state.get("needs_realtime", False))

    try:
        answer = generate_text(prompt, system_instruction=_SYSTEM_INSTRUCTION)
    except Exception:
        return {"notice": GENERATION_ERROR_MESSAGE}

    # Làm sạch trước khi kiểm tra rỗng: một câu trả lời chỉ gồm ký tự Markdown là rỗng
    # trên màn hình, nên phải rơi vào nhánh lỗi thay vì gửi bong bóng chat trắng cho Sale.
    answer = strip_markdown(answer)

    if not answer:
        return {"notice": GENERATION_ERROR_MESSAGE}

    return {"draft_answer": answer, "citations": _build_citations(docs)}


def _verify(state: PipelineState) -> dict[str, Any]:
    """The Verifier Agent scores Faithfulness/Relevancy, independently of Generate."""
    context = [doc["content"] for doc in state.get("retrieved_docs") or []]
    result = verifier_service.score_answer(state["query"], state.get("draft_answer", ""), context)

    return {"verifier_score": round(result.score, 4)}


def _risk_check(state: PipelineState) -> dict[str, Any]:
    """Touches price/commitment -> raise the HITL flag so the Sale must read and confirm."""
    return {"requires_hitl": risk_service.detect_commitment_risk(state.get("draft_answer", ""))}


# --------------------------------------------------------------------------- routing


def _route_after_cache(state: PipelineState) -> str:
    return "hit" if state.get("used_cache") else "miss"


def _route_after_retrieve(state: PipelineState) -> str:
    if state.get("notice"):
        return "stop"
    return "tool_call" if state.get("needs_realtime") else "generate"


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


def _needs_realtime(query: str) -> bool:
    """Diacritic-insensitive matching: a Sale typing fast on a phone rarely uses accents.

    "con can 2pn nao trong khong" must be recognised as an inventory question exactly
    like its fully accented form — otherwise the Agent quietly answers with stale unit
    counts from a PDF.
    """
    normalized = strip_diacritics(query)
    return any(strip_diacritics(keyword) in normalized for keyword in _REALTIME_INTENT_KEYWORDS)


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


def _build_prompt(query: str, docs: list[dict], units: list[InventoryUnit], needs_realtime: bool) -> str:
    sections = [f"CÂU HỎI CỦA SALE:\n{query}"]

    if docs:
        context = "\n\n".join(_format_doc_for_prompt(index, doc) for index, doc in enumerate(docs, start=1))
        sections.append(f"NGỮ CẢNH TỪ TÀI LIỆU DỰ ÁN:\n{context}")

    if needs_realtime:
        sections.append(f"TỒN KHO REAL-TIME:\n{_format_units(units)}")

    sections.append(
        "Trả lời câu hỏi trên với tư cách chuyên viên tư vấn dự án. Viết văn xuôi tự nhiên, "
        "văn bản thuần, không dùng ký tự Markdown nào (không dấu sao, không thăng). "
        "Bám sát đúng loại căn / phân khu / tòa mà câu hỏi nhắc tới, đừng trả lời chung chung "
        "cho cả dự án khi Sale đang hỏi một loại căn cụ thể. Nêu kèm điều kiện đi cùng con số "
        "nếu ngữ cảnh có ghi, dẫn tên tài liệu nguồn cho số liệu quan trọng, và nói rõ phần nào "
        "chưa có dữ liệu thay vì suy đoán."
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
