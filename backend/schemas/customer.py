from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from backend.core.enums import SessionStatus
from backend.schemas.message import MessageResponse


class CustomerRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str | None = None
    # If the visitor was chatting anonymously before registering, both identify the
    # in-progress session so it gets claimed (ownership transferred) instead of starting
    # the customer over with an empty chat history.
    session_id: int | None = None
    visitor_token: str | None = None


class AnonymousSessionResponse(BaseModel):
    session_id: int
    visitor_token: str


class AnonymousSessionClaimRequest(BaseModel):
    session_id: int
    visitor_token: str


class CustomerChatSessionCreate(BaseModel):
    title: str | None = None
    project_id: str | None = None


class CustomerChatSessionResponse(BaseModel):
    id: int
    customer_id: int | None = None
    title: str | None = None
    project_id: str | None = None
    # Who is currently answering — BOT_HANDLING/WAITING_SALE/SALE_HANDLING. The frontend
    # polls `GET /customer/sessions/{id}` for this to know when to show the "waiting for a
    # Sale" banner or switch to live-chat rendering.
    status: SessionStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class CustomerAskRequest(BaseModel):
    content: str


class CustomerAskResponse(MessageResponse):
    # Set when this turn was intercepted by the soft paywall instead of answered for
    # real — the frontend uses it to pop the register/login modal. `None` on every
    # normally-answered turn. "human_request" is the anonymous-visitor case of asking for
    # a live Sale — same gate mechanism, different copy (see routers/customer_chat.py).
    gate: Literal["turn_limit", "closing_intent", "human_request"] | None = None
    # No sensible default from `Message` alone (status lives on `ChatSession`) — the router
    # always overwrites this after `model_validate`, same as it does for `gate`.
    status: SessionStatus = SessionStatus.BOT_HANDLING
