from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

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
from backend.repositories.message import (
    create_message,
    delete_messages_for_session,
    list_messages_for_session,
)
from backend.schemas.chat_session import ChatSessionCreate, ChatSessionResponse
from backend.schemas.message import MessageResponse
from backend.services import agent_pipeline

router = APIRouter(
    prefix="/sale/sessions",
    tags=["Sale Chat"],
    dependencies=[Depends(require_role(UserRole.SALE, UserRole.ADMIN))],
)


class SaleAskRequest(BaseModel):
    content: str


def _owned_session(db: Session, session_id: int, user: User):
    """Lấy phiên chat, 404 nếu không tồn tại hoặc không thuộc về người đang gọi.

    Cả SALE và ADMIN đều chat được, nhưng mỗi người chỉ thấy phiên của chính
    mình: phiên chứa lịch sử tư vấn theo từng khách, không được để người này
    đọc/xoá phiên của người kia. Trả 404 thay vì 403 để không lộ id nào tồn tại.
    """
    session = get_session(db, session_id)
    if session is None or session.sale_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


@router.post("", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_sale_session(
    payload: ChatSessionCreate, db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.SALE, UserRole.ADMIN))
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
    return list_messages_for_session(db, session_id)


@router.post("/{session_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def ask_in_session(
    session_id: int,
    payload: SaleAskRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.SALE, UserRole.ADMIN)),
) -> MessageResponse:
    """Agent Pipeline for the Sale flow — flags HITL when a price/commitment risk is detected.

    TODO: replace with a real call once agent_pipeline.run_pipeline is implemented.
    """
    session = _owned_session(db, session_id, user)
    set_title_if_empty(db, session, payload.content)

    create_message(db, session_id, sender=MessageSender.SALE, content=payload.content)

    result = agent_pipeline.run_pipeline(payload.content)
    return create_message(
        db,
        session_id,
        sender=MessageSender.AGENT,
        content=result.draft_answer,
        citations=result.citations,
        verifier_score=result.verifier_score,
        requires_hitl=result.requires_hitl,
    )


@router.delete("/{session_id}/messages", status_code=status.HTTP_204_NO_CONTENT)
async def clear_session_messages(
    session_id: int, db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.SALE, UserRole.ADMIN))
) -> None:
    """Xoá lịch sử chat nhưng giữ lại phiên — nút 'Xóa chat' trong ChatWindow."""
    _owned_session(db, session_id, user)
    delete_messages_for_session(db, session_id)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_sale_session(
    session_id: int, db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.SALE, UserRole.ADMIN))
) -> None:
    """Xoá hẳn phiên tư vấn cùng toàn bộ tin nhắn — nút xoá trong SessionList."""
    _owned_session(db, session_id, user)
    delete_messages_for_session(db, session_id)
    delete_session(db, session_id)
