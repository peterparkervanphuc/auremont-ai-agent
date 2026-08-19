from datetime import datetime

from pydantic import BaseModel


class ChatSessionCreate(BaseModel):
    title: str | None = None
    customer_name: str | None = None
    project_id: str | None = None


class ChatSessionResponse(BaseModel):
    id: int
    # Nullable since this shape is shared at the ORM level with customer-chat sessions,
    # which carry no sale_id — always set for the Sale-facing endpoints that return this.
    sale_id: int | None
    title: str | None = None
    customer_name: str | None = None
    project_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
