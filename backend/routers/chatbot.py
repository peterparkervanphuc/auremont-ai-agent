from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.mysql_client import get_db
from backend.repositories.message import create_message
from backend.schemas.message import MessageResponse
from backend.services import agent_pipeline
from backend.services.verifier_service import VerifierResult, passes_threshold

router = APIRouter(prefix="/chatbot", tags=["Chatbot (Public)"])


class ChatbotAskRequest(BaseModel):
    customer_id: str
    question: str


class ChatbotAskResponse(BaseModel):
    answer: MessageResponse
    suggest_livechat: bool


@router.post("/ask", response_model=ChatbotAskResponse)
async def ask_chatbot(payload: ChatbotAskRequest, db: Session = Depends(get_db)) -> ChatbotAskResponse:
    """Public Chatbot — RBAC filter is PUBLIC-only, answers directly with no HITL (CLAUDE.md §6.3.b).

    TODO: replace with a real call once agent_pipeline.run_pipeline is implemented; this stub wires
    the request/response shape and the verifier-threshold gate ahead of that.
    """
    result = agent_pipeline.run_pipeline(payload.question, channel=None)
    verifier_result = VerifierResult(faithfulness=result.verifier_score, relevancy=result.verifier_score)
    suggest_livechat = not passes_threshold(verifier_result, channel=None)

    message = create_message(
        db,
        session_id=None,
        sender="agent",
        content=result.draft_answer,
        citations=result.citations,
        verifier_score=result.verifier_score,
        requires_hitl=False,  # Chatbot never shows the HITL card (CLAUDE.md §6.3.b note)
    )

    return ChatbotAskResponse(answer=message, suggest_livechat=suggest_livechat)
