from datetime import datetime

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    location: str | None = None
    description: str | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    location: str | None = None
    description: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
