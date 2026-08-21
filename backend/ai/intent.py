"""Classify what a question needs before any model is called.

Keyword matching rather than an LLM classifier, deliberately. Routing decides whether the
real-time inventory API is consulted, and a misroute silently answers a stock question
from a stale PDF. A deterministic rule is auditable and adds no latency; a classifier call
would add both a failure mode and a round trip to every question.
"""

from backend.utils.text import strip_diacritics

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


def names_specific_document_topic(query: str) -> bool:
    """True only for the keyword-matched half of `needs_document_retrieval` above — a
    query that names something (policy, discount, legal, price list...) that should live
    in an ingested document, as opposed to `needs_document_retrieval`'s generic catch-all
    (True for almost anything that isn't an inventory question, including a bare "tư vấn
    giúp em" with nothing to look up yet).

    Used to decide whether zero retrieval hits means "genuinely missing data, say so
    plainly" versus "nothing specific was asked for, let the model have a normal
    conversation instead" — see agent_pipeline._retrieve.
    """
    normalized = strip_diacritics(query)
    return any(strip_diacritics(keyword) in normalized for keyword in _DOCUMENT_INTENT_KEYWORDS)


# Questions ABOUT the conversation itself rather than about a project ("tôi vừa hỏi gì",
# "bạn vừa nói gì", "tóm tắt lại"). The answer lives in the session transcript, which the
# model already receives via prompts.build_prompt's history block — no document can ever
# ground it. Without this, such a question reaches the Verifier, which scores faithfulness
# against retrieved documents that say nothing about what was asked two turns ago, scores
# 0.0 and replaces a perfectly correct answer with "Không đủ thông tin, liên hệ Admin."
# — see agent_pipeline._route_after_generate.
_CONVERSATION_META_KEYWORDS = (
    "vua hoi",
    "vua noi",
    "vua bao",
    "vua nhac",
    "hoi gi",
    "noi gi",
    "cau hoi truoc",
    "cau truoc",
    "luc nay",
    "ban nay",
    "phia tren",
    "o tren",
    "tom tat lai",
    "tom tat cuoc",
    "tom tat hoi thoai",
    "nhac lai",
    "lap lai",
    "noi lai",
    "da hoi",
    "da noi",
    "dang noi ve",
    "dang hoi ve",
    "chung ta noi",
    "chung ta dang",
)


def is_conversation_meta_query(query: str) -> bool:
    """`True` when the question is about the conversation so far, not about a project.

    These are answerable only from the session transcript, so the Verifier's
    document-grounded faithfulness check is meaningless for them — see
    `_CONVERSATION_META_KEYWORDS` above and `agent_pipeline._route_after_generate`.

    Keyword matching on the diacritic-stripped query, same rationale as the rest of this
    module: deterministic, auditable, no extra round trip. The keyword list is already
    stored unaccented since every comparison runs on the stripped form.
    """
    normalized = strip_diacritics(query)
    return any(keyword in normalized for keyword in _CONVERSATION_META_KEYWORDS)


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
