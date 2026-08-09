"""LangGraph orchestration for the Sale chat flow.

The graph coordinates existing services only: Qdrant retrieval, the optional
real-time inventory tool, Gemini generation, answer verification and the HITL
risk flag consumed by the frontend.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from backend.core.enums import DocumentVisibility
from backend.core.gemini_client import generate_text
from backend.services.inventory_service import InventoryApiError, lookup_inventory
from backend.services.rag_service import RetrievalError, retrieve
from backend.services.verifier_service import passes_threshold, score_answer


@dataclass
class PipelineResult:
    draft_answer: str
    citations: list[dict]
    verifier_score: float
    requires_hitl: bool


class PipelineState(TypedDict, total=False):
    query: str
    project_id: str | None
    retrieved_docs: list[dict]
    inventory_data: list[dict]
    inventory_error: str | None
    retrieval_error: str | None
    draft_answer: str
    citations: list[dict]
    verifier_score: float
    verification_passed: bool
    retry_count: int
    requires_hitl: bool


INVENTORY_PATTERN = re.compile(
    r"\b(tồn kho|còn căn|còn hàng|căn trống|available|"
    r"\d+\s*pn|penthouse|studio|shophouse|duplex)\b",
    re.IGNORECASE,
)
RISK_PATTERN = re.compile(
    r"\b(giá|triệu|tỷ|vnd|đồng|ưu đãi|chiết khấu|"
    r"cam kết|đảm bảo|bàn giao|lợi nhuận)\b",
    re.IGNORECASE,
)
SAFE_FALLBACK = "Không đủ thông tin từ tài liệu hiện có, vui lòng liên hệ Admin."
logger = logging.getLogger(__name__)


def retrieve_node(state: PipelineState) -> dict:
    """Get static project knowledge from Qdrant with Sale/Admin visibility."""
    try:
        return {
            "retrieved_docs": retrieve(
                query=state["query"],
                visibility=DocumentVisibility.INTERNAL,
                project_id=state.get("project_id"),
            ),
            "retrieval_error": None,
        }
    except RetrievalError as exc:
        # Retrieval infrastructure failures must not turn a chat request into a 500.
        return {"retrieved_docs": [], "retrieval_error": str(exc)}


def should_lookup_inventory(state: PipelineState) -> str:
    """Inventory is only queried when the question and project are both known."""
    if state.get("project_id") and INVENTORY_PATTERN.search(state.get("query", "")):
        return "inventory"
    return "generate"


def inventory_node(state: PipelineState) -> dict:
    project_id = state.get("project_id")
    if not project_id:
        return {"inventory_data": [], "inventory_error": None}

    try:
        units = lookup_inventory(project_id, state["query"])
        return {"inventory_data": [asdict(unit) for unit in units], "inventory_error": None}
    except InventoryApiError:
        return {"inventory_data": [], "inventory_error": "Tạm thời không tra được tồn kho."}


def _build_citations(docs: list[dict]) -> list[dict]:
    citations: list[dict] = []
    seen_document_ids: set[int] = set()

    for doc in docs:
        document_id = doc.get("document_id")
        if not isinstance(document_id, int) or document_id in seen_document_ids:
            continue
        seen_document_ids.add(document_id)
        citations.append(
            {
                "document_id": document_id,
                "title": doc.get("title") or "Tài liệu",
                "page": doc.get("page"),
            }
        )

    return citations


def _build_prompt(state: PipelineState) -> str:
    sources: list[str] = []

    for doc in state.get("retrieved_docs", []):
        sources.append(
            f"[Tài liệu: {doc.get('title', 'Không rõ tên')}, trang {doc.get('page', '?')}]\n"
            f"{doc.get('content', '')[:2500]}"
        )

    if state.get("inventory_data"):
        inventory_lines = [
            "- Mã căn: {unit_code}; Loại: {unit_type}; Giá: {price}; Trạng thái: {status}".format(
                unit_code=unit.get("unit_code"),
                unit_type=unit.get("unit_type"),
                price=unit.get("price"),
                status=unit.get("status"),
            )
            for unit in state["inventory_data"]
        ]
        sources.append("[Tồn kho real-time]\n" + "\n".join(inventory_lines))

    if state.get("inventory_error"):
        sources.append(f"[Trạng thái tồn kho]\n{state['inventory_error']}")

    source_text = "\n\n".join(sources)

    return f"""
Bạn là SalesMate, trợ lý tư vấn bất động sản cho đội Sale.

Quy tắc bắt buộc:
- Chỉ trả lời dựa trên dữ liệu nguồn bên dưới.
- Không tự bịa giá, tồn kho, ưu đãi, chính sách hoặc cam kết.
- Nếu nguồn chưa đủ, trả lời đúng câu: \"{SAFE_FALLBACK}\"
- Nếu tồn kho không truy vấn được, nêu rõ điều đó.
- Trả lời bằng tiếng Việt, ngắn gọn, rõ ràng.

Câu hỏi của Sale:
{state['query']}

Nguồn dữ liệu:
{source_text}
""".strip()


def _source_fallback(docs: list[dict], inventory_data: list[dict], inventory_error: str | None) -> str:
    """Return cited source excerpts when the generation provider is unavailable.

    This keeps the Sale flow useful during a temporary provider quota outage,
    without fabricating an LLM-style answer.
    """
    if inventory_data:
        units = "\n".join(
            "- {unit_code}: {unit_type}, giá {price}, trạng thái {status}".format(
                unit_code=unit.get("unit_code", "Không rõ mã"),
                unit_type=unit.get("unit_type", "Không rõ loại"),
                price=unit.get("price", "chưa có"),
                status=unit.get("status", "chưa có"),
            )
            for unit in inventory_data[:5]
        )
        return "Gemini hiện chưa khả dụng. Thông tin tồn kho từ nguồn real-time:\n" + units

    if inventory_error:
        return inventory_error

    excerpts = [
        "[{title}]\n{content}".format(
            title=doc.get("title") or "Tài liệu",
            content=(doc.get("content") or "")[:800],
        )
        for doc in docs[:2]
        if doc.get("content")
    ]
    if excerpts:
        return "Gemini hiện chưa khả dụng. Trích đoạn liên quan từ tài liệu:\n\n" + "\n\n".join(excerpts)

    return SAFE_FALLBACK


def generate_node(state: PipelineState) -> dict:
    """Generate strictly from retrieved documents and/or inventory data."""
    docs = state.get("retrieved_docs", [])
    inventory_data = state.get("inventory_data", [])

    if not docs and not inventory_data:
        answer = state.get("inventory_error") or SAFE_FALLBACK
        return {"draft_answer": answer, "citations": []}

    try:
        answer = generate_text(
            _build_prompt(state),
            system_instruction=(
                "Bạn là trợ lý AI cho đội Sale bất động sản. "
                "Ưu tiên tính chính xác và an toàn nghiệp vụ."
            ),
        ).strip()
    except Exception:
        logger.exception("Gemini generation failed; returning cited source fallback.")
        answer = _source_fallback(docs, inventory_data, state.get("inventory_error"))

    return {"draft_answer": answer or SAFE_FALLBACK, "citations": _build_citations(docs)}


def verify_node(state: PipelineState) -> dict:
    contexts = [doc.get("content", "") for doc in state.get("retrieved_docs", []) if doc.get("content")]
    if state.get("inventory_data"):
        contexts.append(str(state["inventory_data"]))

    result = score_answer(state["query"], state["draft_answer"], contexts)
    return {"verifier_score": result.score, "verification_passed": passes_threshold(result)}


def should_retry_or_risk_check(state: PipelineState) -> str:
    if not state.get("verification_passed", False) and state.get("retry_count", 0) < 1:
        return "retry_generate"
    return "risk_check"


def retry_generate_node(state: PipelineState) -> dict:
    """Keep retries bounded, so a verifier outage cannot cause an infinite loop."""
    return {"retry_count": state.get("retry_count", 0) + 1}


def risk_check_node(state: PipelineState) -> dict:
    answer = state.get("draft_answer", "")
    return {"requires_hitl": bool(RISK_PATTERN.search(answer))}


def build_graph():
    graph = StateGraph(PipelineState)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("inventory", inventory_node)
    graph.add_node("generate", generate_node)
    graph.add_node("verify", verify_node)
    graph.add_node("retry_generate", retry_generate_node)
    graph.add_node("risk_check", risk_check_node)

    graph.add_edge(START, "retrieve")
    graph.add_conditional_edges(
        "retrieve",
        should_lookup_inventory,
        {"inventory": "inventory", "generate": "generate"},
    )
    graph.add_edge("inventory", "generate")
    graph.add_edge("generate", "verify")
    graph.add_conditional_edges(
        "verify",
        should_retry_or_risk_check,
        {"retry_generate": "retry_generate", "risk_check": "risk_check"},
    )
    graph.add_edge("retry_generate", "generate")
    graph.add_edge("risk_check", END)
    return graph.compile()


agent_graph = build_graph()


def run_pipeline(query: str, project_id: str | None = None) -> PipelineResult:
    """Entry point used by the Sale chat router."""
    final_state = agent_graph.invoke(
        {
            "query": query,
            "project_id": project_id,
            "retrieved_docs": [],
            "inventory_data": [],
            "citations": [],
            "retry_count": 0,
            "requires_hitl": False,
        }
    )

    return PipelineResult(
        draft_answer=final_state.get("draft_answer", SAFE_FALLBACK),
        citations=final_state.get("citations", []),
        verifier_score=float(final_state.get("verifier_score", 0.0)),
        requires_hitl=bool(final_state.get("requires_hitl", False)),
    )
