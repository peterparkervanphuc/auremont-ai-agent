from sqlalchemy.orm import Session

from backend.core.enums import MessageEmotion, MessageSender
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
    completeness: float | None = None,
    failure_mode: str | None = None,
    emotion: MessageEmotion | None = None,
    quick_replies: list[str] | None = None,
    suggested_questions: list[str] | None = None,
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
        completeness=completeness,
        failure_mode=failure_mode,
        emotion=emotion,
        quick_replies=quick_replies or None,
        suggested_questions=suggested_questions or None,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def list_messages_for_session(db: Session, session_id: int) -> list[Message]:
    return db.query(Message).filter(Message.session_id == session_id).order_by(Message.created_at).all()


def list_recent_messages(db: Session, session_id: int, limit: int) -> list[Message]:
    """The last `limit` turns of a session, oldest first — the agent's working memory.

    Ordered by id rather than created_at: a question and its answer are written within the
    same second, and MySQL DATETIME has no sub-second resolution, so ordering on it can
    interleave the pair the wrong way round and hand the model an answer that appears to
    precede its own question.

    The newest rows are taken with a DESC limit and then reversed, so the query stays cheap
    on a long-running session instead of loading its entire history.
    """
    rows = db.query(Message).filter(Message.session_id == session_id).order_by(Message.id.desc()).limit(limit).all()
    return list(reversed(rows))


def history_for_pipeline(messages: list[Message]) -> list[dict]:
    """Shape `list_messages_for_session`'s rows into what `agent_pipeline.run_pipeline`'s
    `history` param expects — plain dicts, not ORM objects, so the pipeline module has no
    reason to import `Message`/SQLAlchemy at all. Shared by customer_chat.py and
    sale_chat.py rather than each rolling its own so the shape can't drift between them.
    """
    return [{"sender": m.sender, "content": m.content} for m in messages]


def get_message(db: Session, message_id: int) -> Message | None:
    return db.query(Message).filter(Message.id == message_id).first()


def delete_messages_for_session(db: Session, session_id: int) -> None:
    db.query(Message).filter(Message.session_id == session_id).delete(synchronize_session=False)
    db.commit()
