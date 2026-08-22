"""Classify what a question needs before any model is called.

Keyword matching rather than an LLM classifier, deliberately. Routing decides whether the
real-time inventory API is consulted, and a misroute silently answers a stock question
from a stale PDF. A deterministic rule is auditable and adds no latency; a classifier call
would add both a failure mode and a round trip to every question.
"""

import re

from backend.utils.text import strip_diacritics

_REALTIME_INTENT_KEYWORDS = (
    "tìm căn",
    "lọc căn",
    "tìm nhà",
    "lọc nhà",
    "tìm đất",
    "lọc đất",
    "tìm văn phòng",
    "tìm mặt bằng",
    "tìm kho",
    "những căn",
    "các căn",
    "cho tôi căn",
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
    # Queries over fields exposed by the live MockAPI. These must never fall back to a
    # stale document just because the Sale did not include the words "tồn kho".
    "mã căn",
    "diện tích",
    "giá căn",
    "trạng thái",
    "loại căn",
    "unit_code",
    "project_id",
    "subdivision",
    "unit_type",
    "area_m2",
    "price_vnd",
    "status",
    "m2",
    "m²",
)

_INVENTORY_FOLLOWUP_FIELD_KEYWORDS = (
    "mã căn",
    "diện tích",
    "giá",
    "trạng thái",
    "loại căn",
    "unit_code",
    "project_id",
    "subdivision",
    "unit_type",
    "area_m2",
    "price_vnd",
    "status",
    "m2",
    "m²",
)

# Natural filtering requests often omit an explicit verb: "những căn dưới 5 tỷ", "căn
# hộ trên 80m2". Keyword-only routing missed these even though the criteria parser read
# the numeric bound correctly, leaving a valid filter stranded on the document-RAG path.
_FILTERED_UNIT_QUERY_PATTERN = re.compile(
    r"\b(?:nhung|cac)\s+can\b|\b(?:can|nha)(?:\s+ho)?\b.{0,32}\b(?:duoi|tren|toi da|toi thieu|tu)\s*\d",
    re.IGNORECASE,
)

# A budget/price filter needs both sources: live inventory says what is still available,
# while public project documents provide the published price ranges used to explain and
# compare the recommendations. Previously these questions took the inventory-only branch,
# so a customer asking "tư vấn căn dưới 3 tỷ" never searched the uploaded price material.
_PRICE_DOCUMENT_QUERY_PATTERN = re.compile(
    r"\b(?:gia|ngan\s+sach|tam\s+gia)\b"
    r"|\b(?:duoi|tren|toi\s+da|toi\s+thieu|tu)\b.{0,32}\b(?:ty|ti|trieu|vnd|dong)\b",
    re.IGNORECASE,
)

# Unit-search wording and project-document wording can occur in the same question. The
# live API owns price/status/unit codes, but qualitative attributes such as a view or the
# surrounding landscape normally live in project documents. Treating "can nao ..." as
# inventory-only silently removes the only source that can answer that second half.
# These are domain concepts, not project names or answers, so newly ingested projects
# benefit without a code change.
_PROPERTY_DOCUMENT_ATTRIBUTE_PATTERN = re.compile(
    r"\b(?:view|tam\s+nhin|huong\s+nhin|huong\s+can|canh\s+quan|tien\s+ich|noi\s+that|"
    r"ban\s+giao|so\s+huu|phap\s+ly)\b",
    re.IGNORECASE,
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
    return any(strip_diacritics(keyword) in normalized for keyword in _REALTIME_INTENT_KEYWORDS) or bool(
        _FILTERED_UNIT_QUERY_PATTERN.search(normalized)
    )


def mentions_inventory_followup_field(query: str) -> bool:
    """Whether a follow-up asks for another field of the inventory rows already in scope."""

    normalized = strip_diacritics(query)
    return any(strip_diacritics(keyword) in normalized for keyword in _INVENTORY_FOLLOWUP_FIELD_KEYWORDS)


def needs_document_retrieval(query: str) -> bool:
    """Keep document RAG independent from the live-inventory decision.

    Price-filter requests intentionally use both paths: inventory for current availability
    and uploaded project/price documents for the customer-facing explanation.
    """
    normalized = strip_diacritics(query)
    return (
        any(strip_diacritics(keyword) in normalized for keyword in _DOCUMENT_INTENT_KEYWORDS)
        or bool(_PRICE_DOCUMENT_QUERY_PATTERN.search(normalized))
        or bool(_PROPERTY_DOCUMENT_ATTRIBUTE_PATTERN.search(normalized))
        or not needs_inventory(query)
    )


# Questions a Sale asks about the end customer's profile, not about project facts. These
# must be answered from the session-scoped memory/history before retrieval: sending them
# to RAG both wastes an embedding call and makes a perfectly answerable recall depend on
# the document service being healthy.
_CUSTOMER_MEMORY_REFERENCE_PATTERN = re.compile(
    r"\b(?:khach(?:\s+hang)?(?:\s+(?:cua\s+toi|nay|do))?|ho\s+so\s+khach|nhu\s+cau\s+khach)\b",
    re.IGNORECASE,
)
_CUSTOMER_MEMORY_ATTRIBUTE_PATTERN = re.compile(
    r"\b(?:quan\s+tam|nhu\s+cau|ngan\s+sach|tai\s+chinh|tam\s+gia|loai\s+can"
    r"|phan\s+khu|du\s+an|uu\s+tien|so\s+thich|mong\s+muon|tim\s+mua|muon\s+mua)\b",
    re.IGNORECASE,
)
_MEMORY_RECALL_PATTERN = re.compile(
    r"\b(?:nao|gi|bao\s+nhieu|ra\s+sao|the\s+nao|nhac\s+lai|tom\s+tat"
    r"|cho\s+toi\s+biet|xem\s+lai)\b",
    re.IGNORECASE,
)


def is_customer_memory_query(query: str) -> bool:
    """True for a Sale recalling the represented customer's profile.

    Requiring a customer reference, a remembered attribute and a recall signal avoids
    stealing recommendation questions such as "phân khu nào phù hợp với khách của tôi?"
    or statements such as "khách này quan tâm The Pavilion" from the normal pipeline.
    """
    normalized = strip_diacritics(query)
    if any(term in normalized for term in ("phu hop", "nen chon", "tu van", "de xuat", "goi y")):
        return False
    return bool(
        _CUSTOMER_MEMORY_REFERENCE_PATTERN.search(normalized)
        and _CUSTOMER_MEMORY_ATTRIBUTE_PATTERN.search(normalized)
        and _MEMORY_RECALL_PATTERN.search(normalized)
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


# Phrases that adjust an existing unit search rather than starting a new topic ("giữ
# nguyên điều kiện, tăng giá lên 5 tỷ", "bỏ yêu cầu hồ bơi", "quay lại bộ lọc cũ").
#
# These matter because accumulated search criteria must NOT be applied to every question.
# A Sale who has been filtering units and then asks "chính sách thanh toán thế nào?" is
# changing subject, and silently keeping a 3PN filter on that answer would be wrong. So
# criteria are only touched when the turn is either an inventory question
# (`needs_inventory`) or a refinement of one — this list is the second half of that gate.
_SEARCH_REFINEMENT_KEYWORDS = (
    "giu nguyen",
    "van giu",
    "tang gia",
    "giam gia",
    "tang len",
    "giam xuong",
    "nang len",
    "ha xuong",
    "bo yeu cau",
    "bo dieu kien",
    "bo tieu chi",
    "khong can",
    "thoi khong can",
    "doi lai",
    "thay vao do",
    "re hon",
    "dat hon",
    "rong hon",
    "nho hon",
    "gia mem",
    "de o",
    "dau tu",
    "gia dinh",
    "gia thap den cao",
    "gia cao den thap",
    "re nhat",
    "dat nhat",
    "dien tich lon nhat",
    "don gia thap nhat",
    "quay lai bo loc",
    "bo loc cu",
    "dieu kien cu",
    "xoa bo loc",
    "xoa toan bo",
    "xoa tat ca",
    "bo toan bo",
    "xoa het dieu kien",
    "tim lai tu dau",
    "nhu luc nay",
)


def is_search_refinement(query: str) -> bool:
    """`True` when the turn adjusts an existing unit search instead of opening a new topic.

    Deliberately narrow. A false positive keeps stale filters alive on an unrelated
    question — a failure with no visible symptom, because the answer still looks
    plausible while quietly hiding units. A false negative merely costs the person one
    repeated condition.
    """
    normalized = strip_diacritics(query)
    return any(keyword in normalized for keyword in _SEARCH_REFINEMENT_KEYWORDS)


# Preflight policies cover requests where generation is the wrong tool: unsafe requests
# must be refused consistently, while unsupported product actions must not be presented as
# if they succeeded. The return value is a closed code; user-facing wording stays in the
# pipeline with the other notices.
_ILLEGAL_REQUEST_KEYWORDS = (
    "lam gia giay to",
    "khai gia thap",
    "tron thue",
    "lach luat",
    "ne dieu kien vay",
    "gia mao giay to",
)
_PRIVACY_REQUEST_KEYWORDS = (
    "so dien thoai chu nha",
    "cccd chu nha",
    "thong tin ca nhan chu nha",
    "thong tin ca nhan cu dan",
    "danh sach cu dan",
)
_DISCRIMINATION_PATTERN = re.compile(
    r"\b(hang xom|cu dan|khu nay).{0,30}(dan toc|ton giao|quoc tich|nguoi nuoc nao)\b",
    re.IGNORECASE,
)
_SCAM_SIGNAL_KEYWORDS = (
    "lua dao",
    "coc truoc khi xem",
    "khong cho xem giay to",
    "tai khoan nguoi khac",
    "nguoi nhan tien khong phai chu",
    "thu phi xem nha",
    "moi gioi tu nhan chinh chu",
)
_RENTAL_SEARCH_PATTERN = re.compile(
    r"\b(?:tim|can|muon)\s+(?:can ho|can|nha|phong)?\s*(?:de\s+)?thue\b|\bthue\s+(?:nha|can ho|can|phong)\b",
    re.IGNORECASE,
)


def preflight_policy(query: str) -> str | None:
    """A deterministic policy code for requests that should stop before retrieval."""
    normalized = strip_diacritics(query)
    if any(keyword in normalized for keyword in _ILLEGAL_REQUEST_KEYWORDS):
        return "illegal_request"
    if any(keyword in normalized for keyword in _PRIVACY_REQUEST_KEYWORDS):
        return "privacy_request"
    if _DISCRIMINATION_PATTERN.search(normalized):
        return "discrimination_request"
    if any(keyword in normalized for keyword in _SCAM_SIGNAL_KEYWORDS):
        return "scam_warning"
    # Saving/favourites/notifications are now self-service conversation topics. The
    # assistant may explain the current capability and keep the criteria in this session;
    # prompts still forbid claiming that an external notification was actually created.
    if _RENTAL_SEARCH_PATTERN.search(normalized) and "cho thue" not in normalized:
        return "rental_out_of_scope"
    return None


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
    "đổi lịch",
    "hủy lịch",
    "huỷ lịch",
    "xác nhận lịch",
    "nhắc lịch",
    "hẹn xem nhà",
    "hẹn xem căn",
    "đi xem dự án",
    "đi xem thực tế",
    "tư vấn trực tiếp",
    "gọi điện",
    "gọi video",
    "gọi lại",
    "gửi zalo",
    "gửi sms",
    "gửi email",
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
    """`True` when the customer explicitly needs a person or is frustrated with the AI.

    Detailed price, floor-plan and appointment questions are self-service topics and must
    reach the document pipeline. Treating every closing-adjacent keyword as a handoff made
    normal budget questions disappear behind a generic "contact Sale" response.
    """
    if wants_human_agent(query):
        return True
    normalized = strip_diacritics(query)
    return any(strip_diacritics(keyword) in normalized for keyword in _FRUSTRATION_KEYWORDS)
