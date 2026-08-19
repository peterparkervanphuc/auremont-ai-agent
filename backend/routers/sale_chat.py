import time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.ai import prompts
from backend.core.audit import log_event, truncate
from backend.core.config import settings
from backend.core.deps import require_role
from backend.core.enums import MessageSender, UserRole
from backend.core.mysql_client import get_db
from backend.models.user import User
from backend.repositories.chat_session import (
    create_session,
    delete_session,
    get_session,
    list_sessions_for_sale,
    set_title_if_empty,
)
from backend.repositories.feedback import delete_feedback_for_session
from backend.repositories.hitl_log import confirmed_message_ids, delete_hitl_logs_for_session
from backend.repositories.message import (
    create_message,
    delete_messages_for_session,
    list_messages_for_session,
    list_recent_messages,
)
from backend.schemas.chat_session import ChatSessionCreate, ChatSessionResponse
from backend.schemas.message import MessageResponse
from backend.services import agent_pipeline, memory_service

router = APIRouter(
    prefix="/sale/sessions",
    tags=["Sale Chat"],
    dependencies=[Depends(require_role(UserRole.SALE, UserRole.ADMIN))],
)


class SaleAskRequest(BaseModel):
    content: str


# Three question/answer pairs. Enough for a Sale to build on what was just said without
# the prompt drifting back into a topic the conversation has already moved off.
HISTORY_TURN_LIMIT = 6


def _conversation_history(db: Session, session_id: int) -> list[prompts.ConversationTurn]:
    """The session's short-term working memory, oldest first.

    Edge-case notices are dropped rather than replayed. "Không đủ thông tin, liên hệ Admin"
    and the inventory-down message are UI states, not things the assistant said about the
    project; feeding them back as context invites the model to treat "there is no data" as
    an established fact and repeat it after retrieval has since succeeded.
    """
    turns = []
    for message in list_recent_messages(db, session_id, HISTORY_TURN_LIMIT):
        is_sale = message.sender == MessageSender.SALE
        if not is_sale and message.content in agent_pipeline.NOTICE_MESSAGES:
            continue
        turns.append(prompts.ConversationTurn(is_sale=is_sale, content=message.content))
    return turns


def _owned_session(db: Session, session_id: int, user: User):
    """Fetch a chat session; 404 if it does not exist or does not belong to the caller.

    Both SALE and ADMIN can chat, but each only sees their own sessions: a session
    holds per-customer consultation history, so one user must never read or delete
    another's. Returns 404 rather than 403 so the response does not reveal which
    session ids exist.

    `customer_id is not None` rejects a customer session this Sale has claimed via the
    live-inbox flow (routers/sale_live.py) — that row also carries this Sale's `sale_id`,
    but must only be reachable through the live-inbox endpoints. Routing it through here
    would call the AI pipeline (`ask_in_session` below) on a session a Sale is chatting
    through live, injecting an AI-authored message into the middle of that conversation.
    """
    session = get_session(db, session_id)
    if session is None or session.sale_id != user.id or session.customer_id is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


@router.post("", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_sale_session(
    payload: ChatSessionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.SALE, UserRole.ADMIN)),
) -> ChatSessionResponse:
    return create_session(db, sale_id=user.id, schema=payload)


@router.get("", response_model=list[ChatSessionResponse])
async def list_sale_sessions(
    db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.SALE, UserRole.ADMIN))
) -> list[ChatSessionResponse]:
    return list_sessions_for_sale(db, sale_id=user.id)


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def list_session_messages(
    session_id: int, db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.SALE, UserRole.ADMIN))
) -> list[MessageResponse]:
    _owned_session(db, session_id, user)
    messages = list_messages_for_session(db, session_id)

    # Confirmation state comes from the audit trail, not from the client. Looked up in one
    # batched query rather than per message.
    confirmed = confirmed_message_ids(db, [message.id for message in messages if message.requires_hitl])

    responses = []
    for message in messages:
        response = MessageResponse.model_validate(message)
        response.hitl_confirmed = message.id in confirmed
        responses.append(response)
    return responses


@router.post("/{session_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def ask_in_session(
    session_id: int,
    payload: SaleAskRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.SALE, UserRole.ADMIN)),
) -> MessageResponse:
    """Agent Pipeline for the Sale flow — flags HITL when a price/commitment risk is detected."""
    session = _owned_session(db, session_id, user)
    set_title_if_empty(db, session, payload.content)

    # Read the short-term memory BEFORE persisting the new question, otherwise the question
    # being answered comes back as the last "earlier turn" and the model is handed its own
    # input twice.
    history = _conversation_history(db, session_id)

    create_message(db, session_id, sender=MessageSender.SALE, content=payload.content)

    # Long-term memory is this Sale's own recurring topics, never another Sale's and
    # never the end customer's. Read before the write below so the profile reflects
    # earlier sessions rather than the question currently being answered.
    memory_key = memory_service.sale_key(user.id)
    memory_profile = memory_service.format_profile(memory_service.load_profile(memory_key))

    started = time.perf_counter()
    result = agent_pipeline.run_pipeline(
        payload.content,
        project_id=session.project_id,
        db=db,
        conversation_history=history,
        memory_profile=memory_profile,
    )
    duration_ms = round((time.perf_counter() - started) * 1000, 2)

    # The core business record for Admin Tab 2 (AI Evaluation): the Verifier score
    # and the question are enough to reproduce a wrong answer. NEVER log the answer text.
    log_event(
        "sale.query",
        session_id=session_id,
        user_id=user.id,
        project_id=session.project_id,
        verifier_score=result.verifier_score,
        faithfulness=result.faithfulness,
        answer_relevancy=result.answer_relevancy,
        completeness=result.completeness,
        # The audit log's diagnosis field: filtering Tab 2 by failure_mode is what turns a
        # list of low scores into "these 12 answers failed for the same fixable reason".
        failure_mode=result.failure_mode,
        requires_hitl=result.requires_hitl,
        used_cache=result.used_cache,
        citation_count=len(result.citations),
        duration_ms=duration_ms,
        query_len=len(payload.content),
        query=truncate(payload.content) if settings.log_query_text else None,
    )
    # Only the human's own question is remembered, never the generated answer. `db` lets
    # the project be read out of the question when the session carries none.
    memory_service.remember(memory_key, payload.content, session.project_id, db=db)

    return create_message(
        db,
        session_id,
        sender=MessageSender.AGENT,
        content=result.draft_answer,
        citations=result.citations,
        images=result.images,
        verifier_score=result.verifier_score,
        requires_hitl=result.requires_hitl,
        faithfulness=result.faithfulness,
        answer_relevancy=result.answer_relevancy,
        completeness=result.completeness,
        failure_mode=result.failure_mode,
        emotion=result.emotion,
    )


@router.delete("/{session_id}/messages", status_code=status.HTTP_204_NO_CONTENT)
async def clear_session_messages(
    session_id: int, db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.SALE, UserRole.ADMIN))
) -> None:
    """Clear the chat history but keep the session (the "Xóa chat" button in ChatWindow).

    Order matters: both feedback and HITL confirmations reference messages with non-null
    foreign keys, so they have to go first or the delete fails outright.
    """
    _owned_session(db, session_id, user)
    delete_hitl_logs_for_session(db, session_id)
    delete_feedback_for_session(db, session_id)
    delete_messages_for_session(db, session_id)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_sale_session(
    session_id: int, db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.SALE, UserRole.ADMIN))
) -> None:
    """Delete the consultation session and all its messages — the delete button in SessionList."""
    _owned_session(db, session_id, user)
    delete_hitl_logs_for_session(db, session_id)
    delete_feedback_for_session(db, session_id)
    delete_messages_for_session(db, session_id)
    delete_session(db, session_id)
