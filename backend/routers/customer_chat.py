import secrets
import time
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from backend.ai.intent import needs_human_handoff, wants_human_agent
from backend.core.audit import log_event, truncate
from backend.core.config import settings
from backend.core.deps import get_optional_current_user, require_role
from backend.core.enums import DocumentVisibility, MessageEmotion, MessageSender, SessionStatus, UserRole
from backend.core.mysql_client import get_db
from backend.core.rate_limit import anonymous_rate_limit
from backend.core.security import create_access_token, create_refresh_token
from backend.models.chat_session import ChatSession
from backend.models.message import Message
from backend.models.user import User
from backend.repositories.chat_session import (
    claim_or_merge_anonymous_session,
    create_anonymous_session,
    delete_session,
    enter_waiting_queue,
    get_or_create_customer_session,
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
    AnonymousSessionClaimRequest,
    AnonymousSessionResponse,
    CustomerAskRequest,
    CustomerAskResponse,
    CustomerChatSessionCreate,
    CustomerChatSessionResponse,
    CustomerRegisterRequest,
)
from backend.schemas.message import MessageResponse
from backend.schemas.user import TokenResponse, UserResponse
from backend.services import agent_pipeline, memory_service

router = APIRouter(prefix="/customer", tags=["Customer Chat"])

# Canned copy shown instead of a real answer while the visitor is still anonymous — see
# ARCHITECTURE.md's RBAC section and the product decision behind this router: an anonymous
# visitor gets general answers and closing-adjacent information through self-service. A
# registration prompt is reserved for the anonymous turn limit; a logged-in customer can
# still explicitly request a live Sale.
_TURN_LIMIT_MESSAGE = (
    "Cảm ơn bạn đã trò chuyện cùng Auremont! Để mình lưu lại đoạn chat này và tư vấn sâu hơn, "
    "bạn vui lòng đăng ký/đăng nhập tài khoản nhé."
)
# Shown when frustration with the AI causes a logged-in session to enter WAITING_SALE.
_HANDOFF_NOTICE_MESSAGE = (
    "Dạ em xin phép kết nối anh/chị với "
    "chuyên viên tư vấn ngay bây giờ ạ. Chuyên viên sẽ đọc lại toàn bộ nội dung mình vừa trao "
    "đổi nên anh/chị không cần nhắc lại từ đầu."
)
# Shown when a logged-in customer uses the "Gặp chuyên viên tư vấn" button
# (request_human below).
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
            canonical = claim_or_merge_anonymous_session(db, session, user.id)
            _remember_customer_history(db, canonical, user.id)

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
    # Idempotent by design: the customer surface is one continuous conversation, not a
    # list of independent threads. Repeated first-message calls or multiple browser tabs
    # always converge on the same row.
    return get_or_create_customer_session(db, customer_id=user.id, schema=payload)


@router.post(
    "/sessions/claim-anonymous",
    response_model=CustomerChatSessionResponse,
)
async def claim_anonymous_chat_session(
    payload: AnonymousSessionClaimRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.CUSTOMER)),
) -> CustomerChatSessionResponse:
    """Continue an anonymous transcript after logging into an existing account.

    Registration already transfers the temporary session. Login needs this explicit
    authenticated step because the generic `/auth/login` endpoint cannot safely accept an
    anonymous ownership token. If the account already has a session, both transcripts are
    merged into that canonical row.
    """
    anonymous = get_session(db, payload.session_id)
    if (
        anonymous is None
        or anonymous.customer_id is not None
        or anonymous.visitor_token != payload.visitor_token
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    canonical = claim_or_merge_anonymous_session(db, anonymous, user.id)
    _remember_customer_history(db, canonical, user.id)
    return canonical


@router.get("/sessions", response_model=list[CustomerChatSessionResponse])
async def list_customer_chat_sessions(
    db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.CUSTOMER))
) -> list[ChatSession]:
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
    session = _resolve_customer_asker(db, session, user, x_visitor_token)
    return session


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
async def list_customer_session_messages(
    session_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_current_user),
    x_visitor_token: str | None = Header(default=None, alias="X-Visitor-Token"),
) -> list[Message]:
    session = get_session(db, session_id)
    session = _resolve_customer_asker(db, session, user, x_visitor_token)
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
    PUBLIC clearance (see agent_pipeline.run_pipeline). There is no HITL confirm-before-send
    step here because there is no second human to perform it: the customer IS the one reading
    the answer, and nobody signs off on a commitment made to themselves. A price/commitment
    answer is therefore withheld rather than confirmed — anonymous visitors into the
    registration funnel, logged-in customers to a real Sale — which is what keeps every
    customer-visible message `requires_hitl=False`.

    Returns `None` once a live Sale is involved (WAITING_SALE/SALE_HANDLING): the message is
    still persisted, but the AI must stay completely silent from that point on so it never
    talks over the Sale. The frontend polls `GET /customer/sessions/{id}/messages` to pick up
    the Sale's reply instead of expecting one back from this call.
    """
    session = get_session(db, session_id)
    session = _resolve_customer_asker(db, session, user, x_visitor_token)
    set_title_if_empty(db, session, payload.content)

    # Fetched BEFORE persisting the new customer turn below, specifically so it excludes
    # that turn — run_pipeline's `history` is "everything before this question", and the
    # question itself is passed separately.
    history = history_for_pipeline(list_messages_for_session(db, session_id))

    # Long-term memory is scoped to this customer account and loaded BEFORE remembering
    # the current turn, so the prompt contains durable preferences from earlier turns
    # rather than duplicating the question that is already supplied separately. Anonymous
    # visitors have no stable identity, so they deliberately use short-term history only.
    memory_key: str | None = None
    memory_profile = ""
    if session.customer_id is not None:
        memory_key = memory_service.customer_key(session.customer_id)
        memory_profile = memory_service.format_profile(memory_service.load_profile(memory_key))

    create_message(db, session_id, sender=MessageSender.CUSTOMER, content=payload.content)
    if memory_key is not None:
        memory_service.remember(memory_key, payload.content, session.project_id, db=db)

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
    gate: Literal["turn_limit", "closing_intent", "human_request"] | None = None
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
    # Only the real pipeline branch below ever fills these in — a gate/handoff message is
    # fixed copy, never a discovery question with options to tap, and a customer being
    # walked to the registration form or a live Sale should not be invited to start a new
    # question instead.
    quick_replies: list[str] = []
    listings: list[dict] = []
    suggested_questions: list[str] = []

    if is_anonymous and _anonymous_turn_count(db, session_id) >= settings.customer_anonymous_turn_limit:
        gate = "turn_limit"
        answer_text = _TURN_LIMIT_MESSAGE
        verifier_score, requires_hitl, faithfulness, answer_relevancy = 0.0, False, None, None
    elif not is_anonymous and needs_human_handoff(payload.content):
        new_status = SessionStatus.WAITING_SALE
        enter_waiting_queue(db, session)
        answer_text = (
            _HANDOFF_DIRECT_REQUEST_MESSAGE if wants_human_agent(payload.content) else _HANDOFF_NOTICE_MESSAGE
        )
        verifier_score, requires_hitl, faithfulness, answer_relevancy = 0.0, False, None, None
    else:
        started = time.perf_counter()
        result = agent_pipeline.run_pipeline(
            payload.content,
            project_id=session.project_id,
            db=db,
            clearance=DocumentVisibility.PUBLIC,
            history=history,
            memory_profile=memory_profile,
            session_id=session_id,
        )
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        used_cache = result.used_cache

        if result.requires_hitl:
            # Customer chat is a self-service surface. A grounded price answer may trip the
            # same conservative risk detector used by the Sale co-pilot, but it must not be
            # replaced by a generic handoff. Keep HITL on the Sale flow; on this route show
            # the verified PUBLIC-tier answer and do not expose an unconfirmable HITL card.
            answer_text = result.draft_answer
            verifier_score = result.verifier_score
            faithfulness = result.faithfulness
            answer_relevancy = result.answer_relevancy
            requires_hitl = False
            emotion = MessageEmotion(result.emotion) if result.emotion else emotion
            quick_replies = result.quick_replies
            listings = result.listings
            suggested_questions = result.suggested_questions
        else:
            answer_text = result.draft_answer
            verifier_score, requires_hitl = result.verifier_score, False
            faithfulness, answer_relevancy = result.faithfulness, result.answer_relevancy
            emotion = MessageEmotion(result.emotion) if result.emotion else None
            quick_replies = result.quick_replies
            listings = result.listings
            suggested_questions = result.suggested_questions

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
        listings=listings,
        suggested_questions=suggested_questions,
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
    session = _resolve_customer_asker(db, session, user, None)

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
    session = _resolve_customer_asker(db, session, user, None)

    if session.status != SessionStatus.BOT_HANDLING:
        return_to_bot(db, session)
        log_event("customer.handoff.ended_by_customer", session_id=session_id, customer_id=user.id)

    message = create_message(db, session_id, sender=MessageSender.AGENT, content=_RETURN_TO_AI_MESSAGE)
    response = CustomerAskResponse.model_validate(message)
    response.status = SessionStatus(session.status)
    return response


def _anonymous_turn_count(db: Session, session_id: int) -> int:
    return sum(1 for m in list_messages_for_session(db, session_id) if m.sender == MessageSender.CUSTOMER)


def _remember_customer_history(db: Session, session: ChatSession, customer_id: int) -> None:
    """Seed long-term memory from turns written before an anonymous session was claimed."""
    key = memory_service.customer_key(customer_id)
    for message in list_messages_for_session(db, session.id):
        if message.sender == MessageSender.CUSTOMER:
            memory_service.remember(key, message.content, session.project_id, db=db)


@router.delete("/sessions/{session_id}/messages", status_code=status.HTTP_204_NO_CONTENT)
async def clear_customer_session_messages(
    session_id: int, db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.CUSTOMER))
) -> None:
    session = get_session(db, session_id)
    session = _resolve_customer_asker(db, session, user, None)
    delete_hitl_logs_for_session(db, session_id)
    delete_feedback_for_session(db, session_id)
    delete_messages_for_session(db, session_id)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_customer_session(
    session_id: int, db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.CUSTOMER))
) -> None:
    session = get_session(db, session_id)
    session = _resolve_customer_asker(db, session, user, None)
    delete_hitl_logs_for_session(db, session_id)
    delete_feedback_for_session(db, session_id)
    delete_messages_for_session(db, session_id)
    delete_session(db, session_id)
