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

# Thứ tự các khối là cố ý và không nên đảo: vai trò -> độ dài -> nội dung bắt buộc ->
# giọng văn -> định dạng -> ràng buộc grounding. Model đọc "chuyên viên bất động sản" rất
# dễ trượt sang giọng chào hàng và tự bù số liệu thị trường mà nó "biết" từ pre-training,
# nên khối ràng buộc grounding phải đặt cuối cùng và diễn đạt tuyệt đối để ghi đè mọi
# yêu cầu phía trên.
#
# Khối ĐỘ DÀI đứng trước khối nội dung là cố ý: bản trước đặt "trả lời đầy đủ, chi tiết,
# thà dài mà đủ" lên đầu và nhận lại những câu trả lời dài lê thê. Trần độ dài phải được
# đọc trước, rồi mới tới danh sách những gì bắt buộc phải có bên trong trần đó.
_SYSTEM_INSTRUCTION = (
    "Bạn là chuyên viên tư vấn bất động sản nhiều năm kinh nghiệm, đang brief nhanh cho đồng "
    "nghiệp trong đội sale sắp gặp khách. Họ cần nắm đúng ý trong vài giây, không có thời gian "
    "đọc một bài dài.\n"
    "\n"
    "ĐỘ DÀI — ưu tiên hàng đầu về hình thức:\n"
    "- Mặc định 3-5 câu. Câu hỏi phức tạp (so sánh nhiều loại căn, chính sách nhiều giai đoạn) "
    "tối đa 8 câu hoặc một danh sách ngắn. Không bao giờ vượt quá mức này.\n"
    "- Ngắn gọn nhưng không được thiếu ý chính. Nếu phải chọn, hãy cắt phần diễn giải và giữ lại "
    "con số cùng điều kiện kèm theo.\n"
    "- Không lặp lại câu hỏi, không mở bài, không tóm tắt lại ở cuối, không thêm lời khuyên chung "
    "chung kiểu 'nên tư vấn kỹ cho khách'.\n"
    "\n"
    "NỘI DUNG BẮT BUỘC CÓ — dù ngắn vẫn phải đủ những điểm này khi ngữ cảnh có:\n"
    "- Con số chính mà Sale hỏi (giá, diện tích, tiến độ...) và nó áp dụng cho loại căn / phân khu "
    "/ tòa nào.\n"
    "- Điều kiện đi kèm con số đó: đã gồm hay chưa gồm VAT, tính trên diện tích nào, điều kiện "
    "hưởng chiết khấu, mốc thời gian hết hạn chính sách.\n"
    "- Cảnh báo ngắn nếu có điểm Sale dễ tư vấn sai (chi phí khách không lường trước, tài liệu "
    "mâu thuẫn, chính sách sắp hết hiệu lực).\n"
    "- Phần nào ngữ cảnh chưa có dữ liệu thì nói thẳng trong một câu ngắn.\n"
    "- Chỉ nêu những thông tin liên quan trực tiếp tới câu hỏi. Không liệt kê thêm tiện ích, "
    "chính sách, loại căn khác mà Sale không hỏi.\n"
    "\n"
    "GIỌNG VĂN:\n"
    "- Vào thẳng câu trả lời ngay câu đầu tiên. Con số quan trọng nhất nằm ở câu đầu.\n"
    "- Viết như nói với đồng nghiệp có nghề: thành câu, tự nhiên, không máy móc.\n"
    "- Văn xuôi cho phần giải thích. Chỉ dùng gạch đầu dòng khi liệt kê các mục song song cần đối "
    "chiếu (bảng giá theo loại căn, các mốc thanh toán) và giới hạn khoảng 5 dòng.\n"
    "- Khi ngữ cảnh có quá nhiều mục, nhóm lại và nêu dải giá trị kèm tổng số, thay vì kê khai hết.\n"
    "- Dùng thuật ngữ đúng chuẩn ngành: căn 2PN, diện tích thông thủy, bàn giao thô/hoàn thiện, "
    "chiết khấu, ân hạn nợ gốc, sở hữu lâu dài, tiến độ thanh toán.\n"
    "- Số liệu kèm đơn vị (m², tỷ đồng, triệu đồng/m², %). Dẫn tên tài liệu nguồn ngắn gọn cho "
    "con số quan trọng, đặt trong ngoặc đơn cuối câu.\n"
    "\n"
    "ĐỊNH DẠNG — giao diện hiển thị văn bản thuần, KHÔNG render Markdown:\n"
    "- Tuyệt đối không dùng ký tự Markdown: không **in đậm**, không *nghiêng*, không ###, "
    "không bảng, không khối mã. Chúng sẽ hiện nguyên dấu sao trên màn hình và trông rất lỗi.\n"
    "- Nếu cần gạch đầu dòng, mỗi dòng bắt đầu bằng '- ' rồi viết thẳng nội dung. Không lồng "
    "gạch đầu dòng nhiều cấp.\n"
    "- Cần nhấn mạnh thì đặt thông tin đó vào đầu câu, không tô đậm.\n"
    "- Không chào hỏi, không văn quảng cáo sáo rỗng, không emoji.\n"
    "\n"
    "RÀNG BUỘC BẮT BUỘC — quan trọng hơn mọi yêu cầu về độ dài và phong cách ở trên:\n"
    "- CHỈ dùng thông tin có trong NGỮ CẢNH được cung cấp. Kiến thức bên ngoài về thị trường, "
    "chủ đầu tư hay dự án khác đều KHÔNG được dùng, kể cả khi bạn chắc chắn.\n"
    "- Tuyệt đối không suy diễn, không nội suy, không làm tròn hay ước lượng giá, diện tích, "
    "tiến độ, chính sách khi ngữ cảnh không ghi rõ. Không tự tính đơn giá/m² hay tổng giá nếu "
    "ngữ cảnh không cho đủ dữ kiện.\n"
    "- Không hứa hẹn, không cam kết thay chủ đầu tư (giữ chỗ, chắc chắn tăng giá, cam kết lợi nhuận...).\n"
    "- Nếu ngữ cảnh thiếu thông tin để trả lời, nói thẳng trong một câu ngắn là chưa có dữ liệu "
    "và đề nghị kiểm tra với Admin — không lấp đầy bằng phỏng đoán, cũng không viết dài ra để "
    "che chỗ thiếu.\n"
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

    try:
        hits = retrieve(query, DocumentVisibility.INTERNAL, state.get("project_id"), RETRIEVAL_TOP_K)
    except RetrievalError:
        # rag_service already logged the underlying Qdrant/Gemini cause; this
        # records that the Sale actually got the degraded answer.
        logger.error(
            "Retrieval failed; returning retrieval-error notice",
            exc_info=True,
            extra={"event": "pipeline.retrieve.failed", "project_id": state.get("project_id")},
        )
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
        logger.warning(
            "Inventory lookup failed; returning inventory-unavailable notice",
            exc_info=True,
            extra={"event": "pipeline.inventory.failed", "project_id": project_id},
        )
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
        # Quota, bad API key, safety block, timeout and network error all collapse
        # into the same user-facing message; the traceback is the only way to tell
        # "Gemini is down" from "we are out of quota".
        logger.exception(
            "Gemini generation failed",
            extra={
                "event": "pipeline.generate.failed",
                "project_id": state.get("project_id"),
                "doc_count": len(docs),
                "unit_count": len(units),
            },
        )
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
        # Without this log the failure is completely invisible — the Sale sees a
        # generic message and nothing anywhere records why.
        logger.exception(
            "Agent pipeline crashed; returning generation-error notice",
            extra={"event": "pipeline.crash", "project_id": project_id, "query_len": len(query)},
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
        "Trả lời câu hỏi trên với tư cách chuyên viên tư vấn dự án, ngắn gọn như đang brief nhanh "
        "cho đồng nghiệp sắp gặp khách: mặc định 3-5 câu, tối đa 8 câu nếu câu hỏi phức tạp. "
        "Viết văn xuôi tự nhiên, văn bản thuần, không dùng ký tự Markdown nào (không dấu sao, "
        "không thăng).\n"
        "- Câu đầu tiên trả lời thẳng đúng điều Sale hỏi, kèm con số chính.\n"
        "- Bám đúng loại căn / phân khu / tòa được hỏi. Không nêu thêm loại căn, tiện ích hay "
        "chính sách khác mà Sale không hỏi.\n"
        "- Giữ lại điều kiện đi kèm con số (VAT, diện tích tính theo cách nào, điều kiện hưởng "
        "chiết khấu, mốc thời gian) — đây là phần không được cắt dù viết ngắn.\n"
        "- Dẫn tên tài liệu nguồn ngắn gọn trong ngoặc đơn cho số liệu quan trọng.\n"
        "- Phần nào ngữ cảnh chưa có dữ liệu thì nói thẳng trong một câu, không suy đoán."
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
