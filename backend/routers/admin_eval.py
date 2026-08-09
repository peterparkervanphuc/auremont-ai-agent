from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.deps import require_role
from backend.core.enums import UserRole
from backend.core.mysql_client import get_db
from backend.repositories.feedback import (
    get_average_verifier_scores,
    get_question_for_answer,
    list_top_failed,
)

router = APIRouter(prefix="/admin/eval", tags=["Admin Eval"], dependencies=[Depends(require_role(UserRole.ADMIN))])


@router.get("/scores")
async def get_eval_scores(db: Session = Depends(get_db)) -> dict:
    """Faithfulness/Answer Relevancy dashboard + the top failed AI answers.

    The averages come from the scores the Verifier Agent recorded on each answer as it was
    generated, not from an offline DeepEval batch: those are the scores that actually
    gated what a Sale was shown. `eval/` stays the place for offline DeepEval runs over a
    fixed test set.
    """
    faithfulness_avg, answer_relevancy_avg = get_average_verifier_scores(db)

    top_failed = []
    for message_id, count in list_top_failed(db, limit=10):
        question = get_question_for_answer(db, message_id)
        if question is None:
            continue
        top_failed.append({"message_id": message_id, "question": question, "feedback_count": count})

    return {
        "faithfulness_avg": faithfulness_avg,
        "answer_relevancy_avg": answer_relevancy_avg,
        "top_failed_questions": top_failed,
    }
