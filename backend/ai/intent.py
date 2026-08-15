"""Classify what a question needs before any model is called.

Keyword matching rather than an LLM classifier, deliberately. Routing decides whether the
real-time inventory API is consulted, and a misroute silently answers a stock question
from a stale PDF. A deterministic rule is auditable and adds no latency; a classifier call
would add both a failure mode and a round trip to every question.
"""

from backend.utils.text import strip_diacritics

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


def needs_inventory(query: str) -> bool:
    """Diacritic-insensitive matching: a Sale typing fast on a phone rarely uses accents.

    "con can 2pn nao trong khong" must be recognised as an inventory question exactly
    like its fully accented form — otherwise the Agent quietly answers with stale unit
    counts from a PDF.
    """
    normalized = strip_diacritics(query)
    return any(strip_diacritics(keyword) in normalized for keyword in _REALTIME_INTENT_KEYWORDS)


def needs_document_retrieval(query: str) -> bool:
    """Keep policy/legal RAG independent from the live-inventory decision."""
    normalized = strip_diacritics(query)
    return any(strip_diacritics(keyword) in normalized for keyword in _DOCUMENT_INTENT_KEYWORDS) or not needs_inventory(
        query
    )
