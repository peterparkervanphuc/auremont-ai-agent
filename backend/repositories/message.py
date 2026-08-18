from sqlalchemy.orm import Session

from backend.core.enums import MessageSender
from backend.models.message import Message


def create_message(
    db: Session,
    session_id: int | None,
    sender: MessageSender,
    content: str,
    citations: list[dict] | None = None,
    images: list[dict] | None = None,
    verifier_score: float | None = None,
    requires_hitl: bool = False,
    faithfulness: float | None = None,
    answer_relevancy: float | None = None,
) -> Message:
    message = Message(
        session_id=session_id,
        sender=sender,
        content=content,
        citations=citations,
        images=images,
        verifier_score=verifier_score,
        requires_hitl=requires_hitl,
        faithfulness=faithfulness,
        answer_relevancy=answer_relevancy,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def list_messages_for_session(db: Session, session_id: int) -> list[Message]:
    return db.query(Message).filter(Message.session_id == session_id).order_by(Message.created_at).all()


def get_message(db: Session, message_id: int) -> Message | None:
    return db.query(Message).filter(Message.id == message_id).first()


def delete_messages_for_session(db: Session, session_id: int) -> None:
    db.query(Message).filter(Message.session_id == session_id).delete(synchronize_session=False)
    db.commit()
