from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.core.deps import require_role
from backend.core.enums import UserRole
from backend.core.mysql_client import get_db
from backend.repositories.audit_log import count_audit_logs, list_audit_logs
from backend.repositories.feedback import (
    get_average_verifier_scores,
    get_question_for_answer,
    list_top_failed,
)
from backend.utils.time import utcnow

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


@router.get("/audit")
async def get_audit_log(
    event: str | None = Query(default=None, description="Exact event name, e.g. auth.login.failure"),
    user_id: int | None = Query(default=None),
    days: int | None = Query(default=None, ge=1, le=365, description="Only events from the last N days"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    """Business-event trail, newest first.

    The stdout log is the place to debug what broke five minutes ago; this is the
    place to answer who did what, weeks later, after the container that served
    the request is long gone.
    """
    since = utcnow() - timedelta(days=days) if days is not None else None

    rows = list_audit_logs(db, event=event, user_id=user_id, since=since, limit=limit, offset=offset)

    return {
        "total": count_audit_logs(db, event=event, since=since),
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": row.id,
                "event": row.event,
                "user_id": row.user_id,
                "username": row.username,
                "request_id": row.request_id,
                "created_at": row.created_at,
                "payload": row.payload,
            }
            for row in rows
        ],
    }
