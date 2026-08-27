import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import Settings, get_settings
from backend.core.mysql_client import get_db
from backend.models.news_article import NewsArticle
from backend.schemas.news import (
    NewsArticleResponse,
    NewsIngestRequest,
    NewsIngestResponse,
    NewsListResponse,
    NewsRetentionResponse,
    NewsTopic,
)
from backend.services.news_service import list_published_news, run_news_retention, upsert_official_news
from backend.utils.time import utcnow

router = APIRouter(tags=["News"])


def require_news_ingestion_key(
    x_news_ingestion_key: str = Header(default="", alias="X-News-Ingestion-Key"),
    settings: Settings = Depends(get_settings),
) -> None:
    """Authenticate the private n8n-to-FastAPI boundary."""

    if not x_news_ingestion_key or not secrets.compare_digest(x_news_ingestion_key, settings.news_ingestion_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid news ingestion key")


@router.get("/news", response_model=NewsListResponse)
def get_news(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=12, ge=1, le=48),
    topic: NewsTopic | None = None,
    source_id: str | None = Query(default=None, max_length=50),
    q: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
) -> NewsListResponse:
    """Published official news. Public by design, so every role sees it."""

    rows, total = list_published_news(
        db,
        offset=offset,
        limit=limit,
        topic=topic,
        source_id=source_id,
        query=q,
    )
    return NewsListResponse(items=rows, total=total, offset=offset, limit=limit)


@router.get("/news/{article_id}", response_model=NewsArticleResponse)
def get_news_article(article_id: int, db: Session = Depends(get_db)) -> NewsArticle:
    row = db.scalar(
        select(NewsArticle).where(
            NewsArticle.id == article_id,
            NewsArticle.status == "published",
            NewsArticle.expires_at > utcnow(),
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News article not found")
    return row


@router.post(
    "/integrations/news",
    response_model=NewsIngestResponse,
    dependencies=[Depends(require_news_ingestion_key)],
    include_in_schema=False,
)
def ingest_official_news(
    payload: NewsIngestRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> NewsIngestResponse:
    article, created, changed = upsert_official_news(db, payload, settings)
    return NewsIngestResponse(article=article, created=created, content_changed=changed)


@router.post(
    "/integrations/news/retention",
    response_model=NewsRetentionResponse,
    dependencies=[Depends(require_news_ingestion_key)],
    include_in_schema=False,
)
def retain_news(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> NewsRetentionResponse:
    archived, deleted = run_news_retention(db, settings)
    return NewsRetentionResponse(archived=archived, deleted=deleted)
