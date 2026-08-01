from fastapi import APIRouter, Depends

from backend.core.deps import require_role
from backend.core.enums import UserRole

router = APIRouter(prefix="/admin/eval", tags=["Admin Eval"], dependencies=[Depends(require_role(UserRole.ADMIN))])


@router.get("/scores")
async def get_eval_scores(channel: str = "sale") -> dict:
    """DeepEval Faithfulness/Answer Relevancy dashboard, split by channel (CLAUDE.md §6.5 Tab 2).

    TODO: read persisted DeepEval run results (see eval/results/) instead of returning a stub.
    Public channel is held to a higher threshold than Sale since it has no HITL (CLAUDE.md §9).
    """
    return {
        "channel": channel,
        "faithfulness_avg": None,
        "answer_relevancy_avg": None,
        "top_failed_questions": [],
    }
