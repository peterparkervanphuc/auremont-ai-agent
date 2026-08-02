from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core.enums import FeedbackType, MessageSender
from backend.models.feedback import Feedback
from backend.models.message import Message


def create_feedback(
    db: Session,
    message_id: int,
    feedback_type: FeedbackType,
    comment: str | None = None,
    user_id: int | None = None,
) -> Feedback:
    feedback = Feedback(
        message_id=message_id,
        user_id=user_id,
        type=feedback_type,
        comment=comment,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


def list_feedback_for_message(db: Session, message_id: int) -> list[Feedback]:
    return db.query(Feedback).filter(Feedback.message_id == message_id).order_by(Feedback.created_at).all()


def list_top_failed(db: Session, limit: int = 10) -> list[tuple[int, int]]:
    """(message_id, feedback_count) cho các câu trả lời bị báo sai/thiếu, nhiều nhất trước.

    Chỉ đếm WRONG/INCOMPLETE — HELPFUL không phải thất bại.
    """
    rows = (
        db.query(Feedback.message_id, func.count(Feedback.id).label("total"))
        .filter(Feedback.type.in_([FeedbackType.WRONG, FeedbackType.INCOMPLETE]))
        .group_by(Feedback.message_id)
        .order_by(func.count(Feedback.id).desc())
        .limit(limit)
        .all()
    )
    return [(row.message_id, row.total) for row in rows]


def get_question_for_answer(db: Session, answer_message_id: int) -> str | None:
    """Câu hỏi đã sinh ra câu trả lời bị báo lỗi — tin nhắn của Sale ngay trước đó.

    Admin cần thấy *câu hỏi*, không phải câu trả lời, để biết cần bổ sung tài liệu nào.
    """
    answer = db.query(Message).filter(Message.id == answer_message_id).first()
    if answer is None:
        return None

    question = (
        db.query(Message)
        .filter(
            Message.session_id == answer.session_id,
            Message.created_at <= answer.created_at,
            Message.id != answer.id,
            Message.sender == MessageSender.SALE,
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .first()
    )
    # Phiên chưa có câu hỏi nào đứng trước (dữ liệu lệch) -> lấy tạm nội dung câu trả lời.
    return question.content if question is not None else answer.content
