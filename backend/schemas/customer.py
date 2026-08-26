from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from backend.core.enums import SessionStatus
from backend.schemas.message import MessageResponse
from backend.utils.phone import normalise_vn_mobile


class CustomerRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str | None = Field(default=None, max_length=255)
    # Stored normalised (`0xxxxxxxxx`) so the live inbox shows one form regardless of how
    # the visitor typed it. Optional here even when the product requires it: requiredness
    # is enforced in the router against `lead_require_phone_on_register`, so it can be
    # relaxed with one env var if the gate turns out to cost too many registrations.
    phone: str | None = None
    # If the visitor was chatting anonymously before registering, both identify the
    # in-progress session so it gets claimed (ownership transferred) instead of starting
    # the customer over with an empty chat history.
    session_id: int | None = None
    visitor_token: str | None = None

    @field_validator("phone", mode="before")
    @classmethod
    def _normalise_phone(cls, value: object) -> object:
        return normalise_vn_mobile(value) if isinstance(value, str) else value

    @field_validator("full_name", mode="before")
    @classmethod
    def _strip_full_name(cls, value: object) -> object:
        return value.strip() or None if isinstance(value, str) else value


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
