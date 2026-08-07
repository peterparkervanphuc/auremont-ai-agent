from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.deps import require_role
from backend.core.enums import UserRole
from backend.core.mysql_client import get_db
from backend.repositories.feedback import get_question_for_answer, list_top_failed

router = APIRouter(prefix="/admin/eval", tags=["Admin Eval"], dependencies=[Depends(require_role(UserRole.ADMIN))])


@router.get("/scores")
async def get_eval_scores(db: Session = Depends(get_db)) -> dict:
    """DeepEval Faithfulness/Answer Relevancy dashboard + the top failed AI answers.

    TODO: read persisted DeepEval run results (see eval/results/) instead of returning None.
    """
    top_failed = []
    for message_id, count in list_top_failed(db, limit=10):
        question = get_question_for_answer(db, message_id)
        if question is None:
            continue
        top_failed.append({"message_id": message_id, "question": question, "feedback_count": count})

    return {
        "faithfulness_avg": None,
        "answer_relevancy_avg": None,
        "top_failed_questions": top_failed,
    }
