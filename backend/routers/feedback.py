from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.deps import get_current_user, require_role
from backend.core.enums import UserRole
from backend.core.mysql_client import get_db
from backend.models.user import User
from backend.repositories.feedback import (
    create_feedback,
    get_question_for_answer,
    list_feedback_for_message,
    list_top_failed,
)
from backend.repositories.message import get_message
from backend.schemas.feedback import FailedQuestion, FeedbackCreate, FeedbackResponse

router = APIRouter(prefix="/feedback", tags=["Feedback"])


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FeedbackResponse:
    """Nút Feedback dưới mỗi câu trả lời — Sale báo cáo câu trả lời sai/thiếu."""
    if get_message(db, payload.message_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    return create_feedback(
        db,
        message_id=payload.message_id,
        feedback_type=payload.type,
        comment=payload.comment,
        user_id=user.id,
    )


@router.get("/message/{message_id}", response_model=list[FeedbackResponse])
async def get_feedback_for_message(
    message_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[FeedbackResponse]:
    return list_feedback_for_message(db, message_id)


@router.get("/top-failed", response_model=list[FailedQuestion])
async def get_top_failed_questions(
    limit: int = 10,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
) -> list[FailedQuestion]:
    """Top câu hỏi AI trả lời thất bại, tổng hợp từ Feedback của Sale."""
    results: list[FailedQuestion] = []
    for message_id, count in list_top_failed(db, limit=limit):
        question = get_question_for_answer(db, message_id)
        if question is None:
            continue
        results.append(FailedQuestion(message_id=message_id, question=question, feedback_count=count))
    return results
