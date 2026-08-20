import secrets
import time

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from backend.ai.intent import needs_human_handoff, needs_registration_gate, wants_human_agent
from backend.core.audit import log_event, truncate
from backend.core.config import settings
from backend.core.deps import get_optional_current_user, require_role
from backend.core.enums import DocumentVisibility, MessageEmotion, MessageSender, SessionStatus, UserRole
from backend.core.mysql_client import get_db
from backend.core.rate_limit import anonymous_rate_limit
from backend.core.security import create_access_token, create_refresh_token
from backend.models.chat_session import ChatSession
from backend.models.user import User
from backend.repositories.chat_session import (
    claim_session,
    create_anonymous_session,
    create_customer_session,
    delete_session,
    enter_waiting_queue,
    get_session,
    list_sessions_for_customer,
    return_to_bot,
    set_title_if_empty,
)
from backend.repositories.feedback import delete_feedback_for_session
from backend.repositories.hitl_log import delete_hitl_logs_for_session
from backend.repositories.message import (
    create_message,
    delete_messages_for_session,
    history_for_pipeline,
    list_messages_for_session,
)
from backend.repositories.user import create_user, get_user_by_email
from backend.schemas.customer import (
    AnonymousSessionResponse,
    CustomerAskRequest,
    CustomerAskResponse,
    CustomerChatSessionCreate,
    CustomerChatSessionResponse,
    CustomerRegisterRequest,
)
from backend.schemas.message import MessageResponse
from backend.schemas.user import TokenResponse, UserResponse
from backend.services import agent_pipeline

router = APIRouter(prefix="/customer", tags=["Customer Chat"])

# Canned copy shown instead of a real answer while the visitor is still anonymous — see
# ARCHITECTURE.md's RBAC section and the product decision behind this router: an anonymous
# visitor gets general answers for free, but registration is required before the assistant
# will discuss anything closing-adjacent (detailed pricing, floor plans, viewings) or before
# the conversation continues past a few turns.
_TURN_LIMIT_MESSAGE = (
    "Cảm ơn bạn đã trò chuyện cùng Auremont! Để mình lưu lại đoạn chat này và tư vấn sâu hơn, "
    "bạn vui lòng đăng ký/đăng nhập tài khoản nhé."
)
_CLOSING_INTENT_MESSAGE = (
    "Mình đã chuẩn bị sẵn thông tin chi tiết cho bạn. Để bảo mật thông tin dự án, bạn vui lòng "
    "đăng ký/đăng nhập tài khoản để mình mở khóa tài liệu, hoặc để chuyên viên gọi điện hỗ trợ "
    "ngay nhé!"
)
_HUMAN_REQUEST_GATE_MESSAGE = (
    "Để kết nối bạn với chuyên viên tư vấn, bạn vui lòng đăng ký/đăng nhập tài khoản nhé — "
    "mình sẽ báo ngay cho chuyên viên sau khi bạn hoàn tất."
)
# Shown once a logged-in customer's session flips to WAITING_SALE via the AI itself
# detecting the need (needs_human_handoff keyword match in ask_in_customer_session) — the
# "phần này liên quan đến..." framing states WHY it's handing off, which only makes sense
# when the AI is the one deciding to; see _HANDOFF_DIRECT_REQUEST_MESSAGE below for the
# other trigger (the customer asking directly), which needs no such justification.
_HANDOFF_NOTICE_MESSAGE = (
    "Dạ phần này liên quan đến chính sách bán hàng chi tiết, em xin phép kết nối anh/chị với "
    "chuyên viên tư vấn ngay bây giờ ạ. Chuyên viên sẽ đọc lại toàn bộ nội dung mình vừa trao "
    "đổi nên anh/chị không cần nhắc lại từ đầu."
)
# Shown when the customer themselves asks for a human — the "Gặp chuyên viên tư vấn" button
# (request_human below). Explaining "vì phần này liên quan đến chính sách..." here would be
# inventing a reason that isn't true: they asked directly, nothing about their last message
# triggered this.
_HANDOFF_DIRECT_REQUEST_MESSAGE = (
    "Dạ vâng, em xin phép kết nối anh/chị với chuyên viên tư vấn ngay bây giờ ạ. Chuyên viên "
    "sẽ đọc lại toàn bộ nội dung mình vừa trao đổi nên anh/chị không cần nhắc lại từ đầu."
)
# Shown when the customer explicitly leaves the live handoff — either they asked to (see
# `return_to_ai` below), or the Sale ended it (`sale_live.end`, mirrored into this session).
_RETURN_TO_AI_MESSAGE = (
    "Bạn đã quay lại chat với Auremont AI. Bạn có thể tiếp tục hỏi mình bất cứ điều gì về dự án nhé!"
)


def _resolve_customer_asker(
    db: Session,
    session: ChatSession | None,
    user: User | None,
    visitor_token: str | None,
) -> ChatSession:
    """404 unless the caller genuinely owns this session — same "don't reveal which ids
    exist" posture as `sale_chat._owned_session`.

    A session is owned either by a logged-in CUSTOMER whose id matches `session.customer_id`,
    or — while still anonymous — by whoever holds the matching `visitor_token` (there is no
    account to check identity against yet).
    """
    not_found = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session is None:
        raise not_found

    if session.customer_id is not None:
        if user is None or user.role != UserRole.CUSTOMER or session.customer_id != user.id:
            raise not_found
        return session

    if session.visitor_token is None or session.visitor_token != visitor_token:
        raise not_found
    return session


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register_customer(
    payload: CustomerRegisterRequest,
    db: Session = Depends(get_db),
    _: None = Depends(anonymous_rate_limit),
) -> TokenResponse:
    """Create a CUSTOMER account and, if the visitor was chatting anonymously, claim their
    in-progress session so the conversation continues without losing history."""
    if get_user_by_email(db, payload.email) is not None:
        log_event("customer.register.failure", email=payload.email, reason="email_taken")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = create_user(
        db, username=payload.email, email=payload.email, password=payload.password, role=UserRole.CUSTOMER
    )

    if payload.session_id is not None and payload.visitor_token is not None:
        session = get_session(db, payload.session_id)
        if session is not None and session.customer_id is None and session.visitor_token == payload.visitor_token:
            claim_session(db, session, user.id)

    log_event("customer.register.success", username=user.username, user_id=user.id)
    return TokenResponse(
        access_token=create_access_token(subject=user.username, role=user.role),
        refresh_token=create_refresh_token(subject=user.username),
        user=UserResponse.model_validate(user),
    )


@router.post("/sessions/anonymous", response_model=AnonymousSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_anonymous_chat_session(
    db: Session = Depends(get_db),
    _: None = Depends(anonymous_rate_limit),
) -> AnonymousSessionResponse:
    """Start a session for a visitor with no account — the token is opaque and
    server-generated, never something the client can forge or guess."""
    visitor_token = secrets.token_urlsafe(32)
    session = create_anonymous_session(db, visitor_token=visitor_token)
    return AnonymousSessionResponse(session_id=session.id, visitor_token=visitor_token)


@router.post("/sessions", response_model=CustomerChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_customer_chat_session(
    payload: CustomerChatSessionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.CUSTOMER)),
) -> CustomerChatSessionResponse:
    return create_customer_session(db, customer_id=user.id, schema=payload)


@router.get("/sessions", response_model=list[CustomerChatSessionResponse])
async def list_customer_chat_sessions(
    db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.CUSTOMER))
) -> list[CustomerChatSessionResponse]:
    return list_sessions_for_customer(db, customer_id=user.id)


@router.get("/sessions/{session_id}", response_model=CustomerChatSessionResponse)
async def get_customer_chat_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_current_user),
    x_visitor_token: str | None = Header(default=None, alias="X-Visitor-Token"),
) -> CustomerChatSessionResponse:
    """Session metadata, chiefly `status` — the frontend polls this once a handoff is under
    way (WAITING_SALE/SALE_HANDLING) to know when to switch to live-chat rendering, since the
    ask endpoint stops returning a reply the moment a Sale is involved."""
    session = get_session(db, session_id)
    _resolve_customer_asker(db, session, user, x_visitor_token)
    return session


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
async def list_customer_session_messages(
    session_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_current_user),
    x_visitor_token: str | None = Header(default=None, alias="X-Visitor-Token"),
) -> list[MessageResponse]:
    session = get_session(db, session_id)
    _resolve_customer_asker(db, session, user, x_visitor_token)
    return list_messages_for_session(db, session_id)


@router.post(
    "/sessions/{session_id}/messages",
    response_model=CustomerAskResponse | None,
    status_code=status.HTTP_201_CREATED,
)
async def ask_in_customer_session(
    session_id: int,
    payload: CustomerAskRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_current_user),
    x_visitor_token: str | None = Header(default=None, alias="X-Visitor-Token"),
    _: None = Depends(anonymous_rate_limit),
) -> CustomerAskResponse | None:
    """Public/customer counterpart to `sale_chat.ask_in_session` — always retrieves at
    PUBLIC clearance (see agent_pipeline.run_pipeline), and gates anonymous visitors behind
    a soft paywall instead of a HITL confirm-before-send step (there is no second human
    relaying the answer here: the customer IS the one reading it directly).

    Returns `None` once a live Sale is involved (WAITING_SALE/SALE_HANDLING): the message is
    still persisted, but the AI must stay completely silent from that point on so it never
    talks over the Sale. The frontend polls `GET /customer/sessions/{id}/messages` to pick up
    the Sale's reply instead of expecting one back from this call.
    """
    session = get_session(db, session_id)
    _resolve_customer_asker(db, session, user, x_visitor_token)
    set_title_if_empty(db, session, payload.content)

    # Fetched BEFORE persisting the new customer turn below, specifically so it excludes
    # that turn — run_pipeline's `history` is "everything before this question", and the
    # question itself is passed separately.
    history = history_for_pipeline(list_messages_for_session(db, session_id))

    create_message(db, session_id, sender=MessageSender.CUSTOMER, content=payload.content)

    if session.status != SessionStatus.BOT_HANDLING:
        log_event(
            "customer.query",
            session_id=session_id,
            customer_id=session.customer_id,
            status=session.status,
            query_len=len(payload.content),
        )
        return None

    is_anonymous = session.customer_id is None
    gate: str | None = None
    used_cache = False
    duration_ms = 0.0
    # `session.status` is a raw DB string (Column(String), not a native enum type) — wrap it
    # so a direct attribute assignment below (which pydantic does not validate the way
    # `model_validate` does) actually stores a `SessionStatus` member, not a bare str.
    new_status = SessionStatus(session.status)
    # Every gate/handoff branch below is a polite boundary ("that's outside what I can say
    # here, let me connect you properly") — RESPECTFUL for all of them; only the real
    # pipeline branch can also land on HAPPY/REGRETFUL, from `result.emotion`.
    emotion: MessageEmotion | None = MessageEmotion.RESPECTFUL
    # Only the real pipeline branch below ever fills this in — a gate/handoff message is
    # fixed copy, never a discovery question with options to tap.
    quick_replies: list[str] = []

    if is_anonymous and needs_registration_gate(payload.content):
        gate = "closing_intent"
        answer_text = _CLOSING_INTENT_MESSAGE
        verifier_score, requires_hitl, faithfulness, answer_relevancy = 0.0, False, None, None
    elif is_anonymous and wants_human_agent(payload.content):
        # Same funnel as every other gate: an anonymous visitor must register before a live
        # Sale gets involved — see the "human_request only for logged-in customers" decision.
        gate = "human_request"
        answer_text = _HUMAN_REQUEST_GATE_MESSAGE
        verifier_score, requires_hitl, faithfulness, answer_relevancy = 0.0, False, None, None
    elif is_anonymous and _anonymous_turn_count(db, session_id) >= settings.customer_anonymous_turn_limit:
        gate = "turn_limit"
        answer_text = _TURN_LIMIT_MESSAGE
        verifier_score, requires_hitl, faithfulness, answer_relevancy = 0.0, False, None, None
    elif not is_anonymous and needs_human_handoff(payload.content):
        new_status = SessionStatus.WAITING_SALE
        enter_waiting_queue(db, session)
        answer_text = _HANDOFF_NOTICE_MESSAGE
        verifier_score, requires_hitl, faithfulness, answer_relevancy = 0.0, False, None, None
    else:
        started = time.perf_counter()
        result = agent_pipeline.run_pipeline(
            payload.content, project_id=session.project_id, db=db, clearance=DocumentVisibility.PUBLIC, history=history
        )
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        used_cache = result.used_cache

        if is_anonymous and result.requires_hitl:
            # Belt-and-suspenders: the PUBLIC-tier answer itself tripped risk_service's
            # price/commitment detector even though the keyword gate above missed it.
            # Withhold it the same way, rather than showing a "requires confirmation"
            # answer nobody is there to confirm.
            gate = "closing_intent"
            answer_text = _CLOSING_INTENT_MESSAGE
            verifier_score, requires_hitl, faithfulness, answer_relevancy = 0.0, False, None, None
        else:
            answer_text = result.draft_answer
            verifier_score, requires_hitl = result.verifier_score, result.requires_hitl
            faithfulness, answer_relevancy = result.faithfulness, result.answer_relevancy
            emotion = MessageEmotion(result.emotion) if result.emotion else None
            quick_replies = result.quick_replies

    log_event(
        "customer.query",
        session_id=session_id,
        customer_id=session.customer_id,
        is_anonymous=is_anonymous,
        gate=gate,
        status=new_status,
        verifier_score=verifier_score,
        faithfulness=faithfulness,
        answer_relevancy=answer_relevancy,
        requires_hitl=requires_hitl,
        used_cache=used_cache,
        duration_ms=duration_ms,
        query_len=len(payload.content),
        query=truncate(payload.content) if settings.log_query_text else None,
    )

    message = create_message(
        db,
        session_id,
        sender=MessageSender.AGENT,
        content=answer_text,
        verifier_score=verifier_score,
        requires_hitl=requires_hitl,
        faithfulness=faithfulness,
        answer_relevancy=answer_relevancy,
        emotion=emotion,
        quick_replies=quick_replies,
    )

    response = CustomerAskResponse.model_validate(message)
    response.gate = gate
    response.status = new_status
    return response


@router.post(
    "/sessions/{session_id}/request-human",
    response_model=CustomerAskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_human(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.CUSTOMER)),
) -> CustomerAskResponse:
    """The "Gặp chuyên viên tư vấn" button — logged-in customers only, no dual-auth: an
    anonymous visitor never sees this button (see `wants_human_agent` handling in
    `ask_in_customer_session` for their equivalent, which routes into the registration gate
    instead of a real handoff)."""
    session = get_session(db, session_id)
    _resolve_customer_asker(db, session, user, None)

    if session.status == SessionStatus.BOT_HANDLING:
        enter_waiting_queue(db, session)
        message = create_message(
            db,
            session_id,
            sender=MessageSender.AGENT,
            content=_HANDOFF_DIRECT_REQUEST_MESSAGE,
            emotion=MessageEmotion.RESPECTFUL,
        )
        log_event("customer.handoff.requested", session_id=session_id, customer_id=user.id)
    else:
        # Already waiting or already live — no-op. Re-show the handoff notice rather than
        # whatever the customer said most recently, so this button always gets a
        # consistent, assistant-authored response back regardless of how many times it's
        # clicked.
        prior_notice = next(
            (m for m in reversed(list_messages_for_session(db, session_id)) if m.sender != MessageSender.CUSTOMER),
            None,
        )
        message = prior_notice or create_message(
            db,
            session_id,
            sender=MessageSender.AGENT,
            content=_HANDOFF_DIRECT_REQUEST_MESSAGE,
            emotion=MessageEmotion.RESPECTFUL,
        )

    response = CustomerAskResponse.model_validate(message)
    response.status = SessionStatus(session.status)
    return response


@router.post(
    "/sessions/{session_id}/return-to-ai",
    response_model=CustomerAskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def return_to_ai(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.CUSTOMER)),
) -> CustomerAskResponse:
    """The customer's own escape hatch out of a live handoff (waiting or already live) —
    without this, once a Sale is involved there is no way back to the AI at all. Only
    CUSTOMER-role, no dual-auth, same reasoning as `request_human`: an anonymous visitor can
    never reach WAITING_SALE/SALE_HANDLING in the first place (see `ask_in_customer_session`),
    so there is nothing to return from.
    """
    session = get_session(db, session_id)
    _resolve_customer_asker(db, session, user, None)

    if session.status != SessionStatus.BOT_HANDLING:
        return_to_bot(db, session)
        log_event("customer.handoff.ended_by_customer", session_id=session_id, customer_id=user.id)

    message = create_message(db, session_id, sender=MessageSender.AGENT, content=_RETURN_TO_AI_MESSAGE)
    response = CustomerAskResponse.model_validate(message)
    response.status = SessionStatus(session.status)
    return response


def _anonymous_turn_count(db: Session, session_id: int) -> int:
    return sum(1 for m in list_messages_for_session(db, session_id) if m.sender == MessageSender.CUSTOMER)


@router.delete("/sessions/{session_id}/messages", status_code=status.HTTP_204_NO_CONTENT)
async def clear_customer_session_messages(
    session_id: int, db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.CUSTOMER))
) -> None:
    session = get_session(db, session_id)
    _resolve_customer_asker(db, session, user, None)
    delete_hitl_logs_for_session(db, session_id)
    delete_feedback_for_session(db, session_id)
    delete_messages_for_session(db, session_id)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_customer_session(
    session_id: int, db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.CUSTOMER))
) -> None:
    session = get_session(db, session_id)
    _resolve_customer_asker(db, session, user, None)
    delete_hitl_logs_for_session(db, session_id)
    delete_feedback_for_session(db, session_id)
    delete_messages_for_session(db, session_id)
    delete_session(db, session_id)
