from sqlalchemy.orm import Session

from backend.models.chat_session import ChatSession
from backend.schemas.chat_session import ChatSessionCreate


def create_session(db: Session, sale_id: int, schema: ChatSessionCreate) -> ChatSession:
    session = ChatSession(
        sale_id=sale_id,
        title=schema.title,
        # customer_name and project_id used to be dropped here: the schema accepted
        # them but they were never written to the DB, so every session returned null.
        customer_name=schema.customer_name,
        project_id=schema.project_id,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def list_sessions_for_sale(db: Session, sale_id: int) -> list[ChatSession]:
    return db.query(ChatSession).filter(ChatSession.sale_id == sale_id).order_by(ChatSession.created_at.desc()).all()


def get_session(db: Session, session_id: int) -> ChatSession | None:
    return db.query(ChatSession).filter(ChatSession.id == session_id).first()


def set_title_if_empty(db: Session, session: ChatSession, title: str) -> ChatSession:
    """Tự đặt tên phiên từ câu hỏi đầu tiên của Sale — tránh danh sách toàn
    "Session: Khách #N" không phân biệt được khi có nhiều phiên."""
    if session.title:
        return session
    session.title = title[:40] + ("…" if len(title) > 40 else "")
    db.commit()
    db.refresh(session)
    return session


def delete_session(db: Session, session_id: int) -> None:
    session = get_session(db, session_id)
    if session is None:
        return
    db.delete(session)
    db.commit()
