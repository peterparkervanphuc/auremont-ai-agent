from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

NewsTopic = Literal[
    "official_update",
    "project_progress",
    "infrastructure",
    "market_potential",
    "promotion",
]


class NewsIngestRequest(BaseModel):
    source_id: Literal["vinhomes", "vingroup-real-estate", "vinhomes-market"]
    canonical_url: str = Field(min_length=10, max_length=3000)
    title: str = Field(min_length=5, max_length=500)
    summary: str | None = Field(default=None, max_length=2000)
    image_url: str | None = Field(default=None, max_length=3000)
    topic: NewsTopic = "official_update"
    project_names: list[str] = Field(default_factory=list, max_length=12)
    published_at: datetime | None = None

    @field_validator("title", "summary", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return " ".join(value.split()) or None

    @field_validator("project_names", mode="after")
    @classmethod
    def unique_projects(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for raw in values:
            value = " ".join(raw.split())[:150]
            key = value.casefold()
            if value and key not in seen:
                result.append(value)
                seen.add(key)
        return result


class NewsArticleResponse(BaseModel):
    id: int
    canonical_url: str
    source_id: str
    source_name: str
    title: str
    summary: str | None
    image_url: str | None
    topic: str
    project_names: list[str]
    published_at: datetime | None
    fetched_at: datetime

    model_config = {"from_attributes": True}


class NewsListResponse(BaseModel):
    items: list[NewsArticleResponse]
    total: int
    offset: int
    limit: int


class NewsIngestResponse(BaseModel):
    article: NewsArticleResponse
    created: bool
    content_changed: bool


class NewsRetentionResponse(BaseModel):
    archived: int
    deleted: int
