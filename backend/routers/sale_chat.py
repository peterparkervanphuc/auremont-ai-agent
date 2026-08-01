from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.deps import require_role
from backend.core.enums import MessageSender, UserRole
from backend.core.mysql_client import get_db
from backend.models.user import User
from backend.repositories.chat_session import create_session, get_session, list_sessions_for_sale
from backend.repositories.message import create_message, list_messages_for_session
from backend.schemas.chat_session import ChatSessionCreate, ChatSessionResponse
from backend.schemas.message import MessageResponse
from backend.services import agent_pipeline

router = APIRouter(
    prefix="/sale/sessions",
    tags=["Sale Chat"],
    dependencies=[Depends(require_role(UserRole.SALE))],
)


class SaleAskRequest(BaseModel):
    content: str


@router.post("", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_sale_session(
    payload: ChatSessionCreate, db: Session = Depends(get_db), sale: User = Depends(require_role(UserRole.SALE))
) -> ChatSessionResponse:
    return create_session(db, sale_id=sale.id, schema=payload)


@router.get("", response_model=list[ChatSessionResponse])
async def list_sale_sessions(
    db: Session = Depends(get_db), sale: User = Depends(require_role(UserRole.SALE))
) -> list[ChatSessionResponse]:
    return list_sessions_for_sale(db, sale_id=sale.id)


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def list_session_messages(session_id: int, db: Session = Depends(get_db)) -> list[MessageResponse]:
    session = get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return list_messages_for_session(db, session_id)


@router.post("/{session_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def ask_in_session(session_id: int, payload: SaleAskRequest, db: Session = Depends(get_db)) -> MessageResponse:
    """Agent Pipeline for the Sale flow (CLAUDE.md §6.4.d) — flags HITL when a price/commitment risk is detected.

    TODO: replace with a real call once agent_pipeline.run_pipeline is implemented.
    """
    session = get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    create_message(db, session_id, sender=MessageSender.SALE, content=payload.content)

    result = agent_pipeline.run_pipeline(payload.content, channel=UserRole.SALE)
    return create_message(
        db,
        session_id,
        sender=MessageSender.AGENT,
        content=result.draft_answer,
        citations=result.citations,
        verifier_score=result.verifier_score,
        requires_hitl=result.requires_hitl,
    )
