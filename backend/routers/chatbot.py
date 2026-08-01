from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.mysql_client import get_db
from backend.repositories.message import create_message
from backend.schemas.message import MessageResponse
from backend.services import agent_pipeline

router = APIRouter(prefix="/chatbot", tags=["Chatbot (Public)"])


class ChatbotAskRequest(BaseModel):
    question: str


@router.post("/ask", response_model=MessageResponse)
async def ask_chatbot(payload: ChatbotAskRequest, db: Session = Depends(get_db)) -> MessageResponse:
    """Public Chatbot — RBAC filter is PUBLIC-only, answers directly with no HITL (CLAUDE.md §5.4).

    TODO: replace with a real call once agent_pipeline.run_pipeline is implemented; this stub wires
    the request/response shape ahead of that.
    """
    result = agent_pipeline.run_pipeline(payload.question, channel=None)

    return create_message(
        db,
        session_id=None,
        sender="agent",
        content=result.draft_answer,
        citations=result.citations,
        verifier_score=result.verifier_score,
        requires_hitl=False,  # Chatbot never shows the HITL card
    )
