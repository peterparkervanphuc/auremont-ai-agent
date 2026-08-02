from sqlalchemy.orm import Session

from backend.models.chat_session import ChatSession
from backend.schemas.chat_session import ChatSessionCreate


def create_session(db: Session, sale_id: int, schema: ChatSessionCreate) -> ChatSession:
    session = ChatSession(sale_id=sale_id, title=schema.title)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def list_sessions_for_sale(db: Session, sale_id: int) -> list[ChatSession]:
    return db.query(ChatSession).filter(ChatSession.sale_id == sale_id).order_by(ChatSession.created_at.desc()).all()


def get_session(db: Session, session_id: int) -> ChatSession | None:
    return db.query(ChatSession).filter(ChatSession.id == session_id).first()
