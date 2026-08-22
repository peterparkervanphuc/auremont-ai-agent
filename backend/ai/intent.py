"""Classify what a question needs before any model is called.

Keyword matching rather than an LLM classifier, deliberately. Routing decides whether the
real-time inventory API is consulted, and a misroute silently answers a stock question
from a stale PDF. A deterministic rule is auditable and adds no latency; a classifier call
would add both a failure mode and a round trip to every question.
"""

import re

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

# A budget threshold ("dưới 5 tỷ", "tối đa 3 tỷ", "từ 3 tỷ đến 5 tỷ", "3-5 tỷ") is an
# inventory question too: `inventory_service._extract_price_range` already knows how to
# filter live units by exactly this phrasing, but only ever runs once `needs_inventory`
# routes the question to the tool. Missing this here means a budget-based recommendation
# ("tư vấn căn hộ dưới 5 tỷ") falls through to document retrieval instead — nothing in an
# ingested price-list PDF is phrased as "under 5 billion", so the model reports missing
# data even though the live inventory lookup could have answered it directly. Matched
# against the diacritic-stripped query, same as everything else in this module.
_PRICE_THRESHOLD_PATTERN = re.compile(r"\b(?:duoi|tren|khong qua|toi da)\s*\d+(?:[.,]\d+)?\s*(?:ty|trieu|tr)\b")
_PRICE_RANGE_PATTERN = re.compile(
    r"\b(?:tu\s*)?\d+(?:[.,]\d+)?\s*(?:ty|trieu|tr)?\s*(?:-|den|toi)\s*\d+(?:[.,]\d+)?\s*(?:ty|trieu|tr)\b"
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


def _mentions_price_threshold(normalized: str) -> bool:
    return bool(_PRICE_THRESHOLD_PATTERN.search(normalized) or _PRICE_RANGE_PATTERN.search(normalized))


def needs_inventory(query: str) -> bool:
    """Diacritic-insensitive matching: a Sale typing fast on a phone rarely uses accents.

    "con can 2pn nao trong khong" must be recognised as an inventory question exactly
    like its fully accented form — otherwise the Agent quietly answers with stale unit
    counts from a PDF.
    """
    normalized = strip_diacritics(query)
    if any(strip_diacritics(keyword) in normalized for keyword in _REALTIME_INTENT_KEYWORDS):
        return True
    return _mentions_price_threshold(normalized)


def needs_document_retrieval(query: str) -> bool:
    """Keep policy/legal RAG independent from the live-inventory decision.

    A budget-threshold question ALSO runs retrieval, unlike a plain availability question
    ("còn căn nào không") — see `names_specific_document_topic` for why: the live inventory
    API in this build phase is placeholder mock data (no subdivision, no real VND prices),
    so a budget-based recommendation is answered from the ingested price-list/catalogue
    documents, with whatever the live tool returns folded in alongside rather than relied
    on alone.
    """
    normalized = strip_diacritics(query)
    if any(strip_diacritics(keyword) in normalized for keyword in _DOCUMENT_INTENT_KEYWORDS):
        return True
    if _mentions_price_threshold(normalized):
        return True
    return not needs_inventory(query)


def names_specific_document_topic(query: str) -> bool:
    """True for the keyword-matched half of `needs_document_retrieval` above, plus a
    budget threshold — both name something (policy, discount, legal, price list, a price
    range...) that should live in an ingested document, as opposed to
    `needs_document_retrieval`'s generic catch-all (True for almost anything that isn't a
    plain availability question, including a bare "tư vấn giúp em" with nothing to look up
    yet).

    Used to decide whether zero retrieval hits means "genuinely missing data, say so
    plainly" versus "nothing specific was asked for, let the model have a normal
    conversation instead" — see agent_pipeline._retrieve.
    """
    normalized = strip_diacritics(query)
    if any(strip_diacritics(keyword) in normalized for keyword in _DOCUMENT_INTENT_KEYWORDS):
        return True
    return _mentions_price_threshold(normalized)


# Signals that an anonymous visitor is past general curiosity and into a sales-closing
# question — this is the one moment the customer chat flow (backend/routers/customer_chat.py)
# withholds the real answer and shows the register/login gate instead. Keyword matching,
# same rationale as everything else in this file: deterministic, auditable, no added
# round trip. First-draft wordlist — tune against real visitor phrasing once available.
_CLOSING_INTENT_KEYWORDS = (
    "bảng giá chi tiết",
    "xin bảng giá",
    "gửi bảng giá",
    "cho mình bảng giá",
    "mặt bằng chi tiết",
    "xem mặt bằng",
    "đặt lịch",
    "hẹn xem nhà",
    "hẹn xem căn",
    "đi xem dự án",
    "đi xem thực tế",
    "tư vấn trực tiếp",
    "gọi điện",
    "số điện thoại",
    "liên hệ em",
    "liên hệ anh",
    "liên hệ chị",
)


def needs_registration_gate(query: str) -> bool:
    """`True` when the question is a sales-closing ask that must trigger the soft paywall
    instead of a direct answer, for an anonymous customer-chat visitor.
    """
    normalized = strip_diacritics(query)
    return any(strip_diacritics(keyword) in normalized for keyword in _CLOSING_INTENT_KEYWORDS)


# An explicit ask for a human, as opposed to merely asking a closing-adjacent question.
# Kept separate from `_CLOSING_INTENT_KEYWORDS` because the two need different responses for
# an anonymous visitor: a closing-adjacent question gets the existing "register to unlock"
# copy, this gets "register to talk to someone" copy — see the `"human_request"` gate in
# backend/routers/customer_chat.py.
_WANTS_HUMAN_KEYWORDS = (
    "gặp người thật",
    "nói chuyện với người",
    "nói chuyện với nhân viên",
    "gặp chuyên viên",
    "gặp sale",
    "gặp nhân viên",
    "tư vấn viên",
    "nhân viên hỗ trợ",
    "cho gặp người",
    "kết nối nhân viên",
)


def wants_human_agent(query: str) -> bool:
    """`True` when the visitor explicitly asked to talk to a person, regardless of topic."""
    normalized = strip_diacritics(query)
    return any(strip_diacritics(keyword) in normalized for keyword in _WANTS_HUMAN_KEYWORDS)


# Signs of frustration — on top of the two lists above, this is the third trigger for
# handing a conversation to a human (backend/routers/customer_chat.py), only applied to a
# logged-in customer: frustration means "this now needs a human before the AI makes it
# worse", which is a lower bar than what an anonymous visitor should be gated on.
_FRUSTRATION_KEYWORDS = (
    "bực",
    "khó chịu",
    "không hài lòng",
    "phàn nàn",
    "khiếu nại",
    "chán",
    "thất vọng",
    "trả lời linh tinh",
    "không hiểu",
    "hỏi mãi",
    "vô dụng",
)


def needs_human_handoff(query: str) -> bool:
    """`True` when a logged-in customer's question should be handed to a live Sale instead
    of answered by the AI — a closing-adjacent question, an explicit ask for a human, or a
    sign of frustration with the AI itself.
    """
    if needs_registration_gate(query) or wants_human_agent(query):
        return True
    normalized = strip_diacritics(query)
    return any(strip_diacritics(keyword) in normalized for keyword in _FRUSTRATION_KEYWORDS)
