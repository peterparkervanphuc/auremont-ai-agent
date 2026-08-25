"""Live handoff queue: a customer session a Sale has taken over from the AI.

Deliberately a separate router/prefix from `sale_chat.py` (the Sale's own AI-consult flow)
rather than folded into it — a claimed session carries BOTH `sale_id` and `customer_id` (see
ChatSession's docstring), which does not fit `sale_chat.py`'s ownership check (`sale_id`
only) or its `/sale/sessions/{id}/messages` endpoint (which calls the AI pipeline — the one
thing that must never happen on a session a Sale is chatting through live).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.audit import log_event, truncate
from backend.core.deps import require_role
from backend.core.enums import DocumentVisibility, MessageSender, SessionChannel, SessionStatus, UserRole
from backend.core.mysql_client import get_db
from backend.models.chat_session import ChatSession
from backend.models.message import Message
from backend.models.user import User
from backend.repositories.chat_session import (
    claim_for_sale,
    get_latest_customer_session,
    get_session,
    list_sessions_handled_by_sale,
    list_waiting_sessions,
    return_to_bot,
)
from backend.repositories.message import create_message, history_for_pipeline, list_messages_for_session
from backend.repositories.user import get_user_by_id
from backend.schemas.message import MessageResponse
from backend.schemas.sale_live import LiveInboxEntry, SaleLiveMessageRequest, SaleSuggestResponse
from backend.services import agent_pipeline

router = APIRouter(
    prefix="/sale/live-inbox",
    tags=["Sale Live Inbox"],
    dependencies=[Depends(require_role(UserRole.SALE, UserRole.ADMIN))],
)

# Left in the transcript so the customer sees why the conversation goes quiet on the Sale
# side and knows Auremont AI is available again — see `end` below.
_HANDOFF_ENDED_MESSAGE = (
    "Chuyên viên đã kết thúc phiên hỗ trợ trực tiếp. Bạn có thể tiếp tục hỏi Auremont AI bất cứ lúc nào nhé!"
)


def _customer_label(db: Session, session: ChatSession) -> str:
    user = get_user_by_id(db, session.customer_id) if session.customer_id else None
    return user.email if user else f"Khách #{session.customer_id}"


def _owned_live_session(db: Session, session_id: int, user: User) -> ChatSession:
    """404 unless this Sale is the one who claimed this session — same "don't reveal which
    ids exist" posture as `sale_chat._owned_session`.

    The `channel == LIVE` check is the second lock on customer privacy: a Sale is never
    shown the customer's AI conversation, and every read/write in this router goes through
    here, so passing an AI session's id gets the same 404 as an id that doesn't exist.
    """
    session = get_session(db, session_id)
    if (
        session is None
        or session.sale_id != user.id
        or session.customer_id is None
        or session.channel != SessionChannel.LIVE
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


def _to_entry(db: Session, session: ChatSession) -> LiveInboxEntry:
    messages = list_messages_for_session(db, session.id)
    preview = truncate(messages[-1].content, limit=80) if messages else ""
    return LiveInboxEntry(
        session_id=session.id,
        customer_label=_customer_label(db, session),
        last_message_preview=preview or "",
        waiting_since=session.handoff_requested_at,
    )


@router.get("", response_model=list[LiveInboxEntry])
async def list_waiting(db: Session = Depends(get_db)) -> list[LiveInboxEntry]:
    return [_to_entry(db, session) for session in list_waiting_sessions(db)]


@router.get("/mine", response_model=list[LiveInboxEntry])
async def list_mine(
    db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.SALE, UserRole.ADMIN))
) -> list[LiveInboxEntry]:
    """Sessions this Sale has already claimed and is still chatting through live — without
    this, claiming removes a session from `list_waiting` and there is no other way back to
    it after navigating away or logging back in."""
    return [_to_entry(db, session) for session in list_sessions_handled_by_sale(db, sale_id=user.id)]


@router.post("/{session_id}/claim", response_model=LiveInboxEntry)
async def claim(
    session_id: int, db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.SALE, UserRole.ADMIN))
) -> LiveInboxEntry:
    session = claim_for_sale(db, session_id, sale_id=user.id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Khách này vừa được chuyên viên khác tiếp nhận.",
        )

    log_event("chat.handoff.claimed", session_id=session_id, sale_id=user.id, customer_id=session.customer_id)
    return _to_entry(db, session)


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def get_live_messages(
    session_id: int, db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.SALE, UserRole.ADMIN))
) -> list[Message]:
    """Full history, including everything the AI already said, so the Sale never has to ask
    the customer to repeat themselves."""
    _owned_live_session(db, session_id, user)
    return list_messages_for_session(db, session_id)


@router.post("/{session_id}/reply", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def reply(
    session_id: int,
    payload: SaleLiveMessageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.SALE, UserRole.ADMIN)),
) -> MessageResponse:
    """A Sale's own words, typed and sent directly — never touches the AI pipeline."""
    session = _owned_live_session(db, session_id, user)
    if session.status != SessionStatus.SALE_HANDLING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session is not live")

    message = create_message(db, session_id, sender=MessageSender.SALE, content=payload.content)
    log_event("chat.handoff.reply", session_id=session_id, sale_id=user.id, content_len=len(payload.content))
    return message


@router.post("/{session_id}/end", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def end(
    session_id: int, db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.SALE, UserRole.ADMIN))
) -> MessageResponse:
    """The Sale is done — hand the session back to the AI. Clears `sale_id` (see
    `return_to_bot`), so this session disappears from this Sale's "mine" list and, if the
    customer needs a human again later, any Sale can pick up the fresh handoff — not
    necessarily the same one."""
    session = _owned_live_session(db, session_id, user)
    return_to_bot(db, session)
    log_event("chat.handoff.ended_by_sale", session_id=session_id, sale_id=user.id)
    return create_message(db, session_id, sender=MessageSender.AGENT, content=_HANDOFF_ENDED_MESSAGE)


@router.post("/{session_id}/suggest", response_model=SaleSuggestResponse)
async def suggest(
    session_id: int, db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.SALE, UserRole.ADMIN))
) -> SaleSuggestResponse:
    """Co-pilot: draft a reply to the customer's latest message for the Sale to review and
    edit before sending via `/reply` — never persisted, never sent on its own. Runs at
    INTERNAL clearance since a Sale is now supervising every word before it goes out.
    """
    session = _owned_live_session(db, session_id, user)
    if session.status != SessionStatus.SALE_HANDLING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session is not live")

    messages = list_messages_for_session(db, session_id)
    last_customer_message = next((m for m in reversed(messages) if m.sender == MessageSender.CUSTOMER), None)
    if last_customer_message is None:
        return SaleSuggestResponse(draft="")

    # The customer's AI conversation is a separate session the Sale cannot open (see
    # `_owned_live_session`), but the draft is written by the pipeline, not read by the
    # Sale, so it still gets that context to avoid asking things the customer already
    # answered. Only this generated draft crosses over — and the Sale edits it before it is
    # ever sent, so nothing is disclosed that they don't choose to say themselves.
    ai_session = get_latest_customer_session(db, session.customer_id) if session.customer_id else None
    prior = list_messages_for_session(db, ai_session.id) if ai_session else []

    # Everything except the message being used as the query itself — same "history is
    # what came before" contract as customer_chat.py/sale_chat.py, just sliced out of an
    # already-fetched list here instead of fetched separately before persisting a new one.
    history = history_for_pipeline([*prior, *(m for m in messages if m is not last_customer_message)])
    result = agent_pipeline.run_pipeline(
        last_customer_message.content,
        project_id=session.project_id,
        db=db,
        clearance=DocumentVisibility.INTERNAL,
        history=history,
        session_id=session_id,
    )
    return SaleSuggestResponse(draft=result.draft_answer, requires_hitl=result.requires_hitl)
