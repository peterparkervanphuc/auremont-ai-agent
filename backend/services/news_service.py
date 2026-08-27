import hashlib
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import HTTPException, status
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from backend.core.config import Settings
from backend.models.news_article import NewsArticle
from backend.schemas.news import NewsIngestRequest
from backend.utils.time import utcnow


@dataclass(frozen=True)
class OfficialNewsSource:
    name: str
    canonical_host: str
    allowed_hosts: frozenset[str]


OFFICIAL_NEWS_SOURCES: dict[str, OfficialNewsSource] = {
    "vinhomes": OfficialNewsSource("Vinhomes", "vinhomes.vn", frozenset({"vinhomes.vn", "www.vinhomes.vn"})),
    "vingroup-real-estate": OfficialNewsSource(
        "Vingroup · Bất động sản",
        "vingroup.net",
        frozenset({"vingroup.net", "www.vingroup.net"}),
    ),
    "vinhomes-market": OfficialNewsSource(
        "Vinhomes Market",
        "market.vinhomes.vn",
        frozenset({"market.vinhomes.vn"}),
    ),
}

_TRACKING_QUERY_KEYS = frozenset({"fbclid", "gclid", "mc_cid", "mc_eid"})


def canonicalize_official_url(raw_url: str, source_id: str) -> str:
    source = OFFICIAL_NEWS_SOURCES[source_id]
    parts = urlsplit(raw_url.strip())
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme.lower() not in {"http", "https"} or host not in source.allowed_hosts:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"URL does not belong to the configured official source: {source_id}",
        )
    if parts.username or parts.password:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="URL credentials are not allowed")

    clean_query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_QUERY_KEYS
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("https", source.canonical_host, path, urlencode(clean_query), ""))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _content_hash(payload: NewsIngestRequest, canonical_url: str) -> str:
    values = [
        canonical_url,
        payload.title,
        payload.summary or "",
        payload.image_url or "",
        payload.topic,
        "\x1f".join(payload.project_names),
        payload.published_at.isoformat() if payload.published_at else "",
    ]
    return _sha256("\x1e".join(values))


def upsert_official_news(db: Session, payload: NewsIngestRequest, settings: Settings) -> tuple[NewsArticle, bool, bool]:
    canonical_url = canonicalize_official_url(payload.canonical_url, payload.source_id)
    url_hash = _sha256(canonical_url)
    now = utcnow()
    content_hash = _content_hash(payload, canonical_url)
    article = db.scalar(select(NewsArticle).where(NewsArticle.url_hash == url_hash))

    if article is None:
        expiry_base = payload.published_at or now
        article = NewsArticle(
            url_hash=url_hash,
            canonical_url=canonical_url,
            source_id=payload.source_id,
            source_name=OFFICIAL_NEWS_SOURCES[payload.source_id].name,
            title=payload.title,
            summary=payload.summary,
            image_url=payload.image_url,
            topic=payload.topic,
            project_names=payload.project_names,
            status="published",
            content_hash=content_hash,
            published_at=payload.published_at,
            fetched_at=now,
            expires_at=expiry_base + timedelta(days=settings.news_default_ttl_days),
        )
        db.add(article)
        db.commit()
        db.refresh(article)
        return article, True, True

    changed = article.content_hash != content_hash
    if changed:
        article.source_id = payload.source_id
        article.source_name = OFFICIAL_NEWS_SOURCES[payload.source_id].name
        article.canonical_url = canonical_url
        article.title = payload.title
        article.summary = payload.summary
        article.image_url = payload.image_url
        article.topic = payload.topic
        article.project_names = payload.project_names
        article.published_at = payload.published_at
        article.content_hash = content_hash
        article.status = "published"
        article.archived_at = None
        expiry_base = payload.published_at or now
        article.expires_at = expiry_base + timedelta(days=settings.news_default_ttl_days)
    article.fetched_at = now
    db.commit()
    db.refresh(article)
    return article, False, changed


def list_published_news(
    db: Session,
    *,
    offset: int,
    limit: int,
    topic: str | None = None,
    source_id: str | None = None,
    query: str | None = None,
) -> tuple[list[NewsArticle], int]:
    now = utcnow()
    filters = [NewsArticle.status == "published", NewsArticle.expires_at > now]
    if topic:
        filters.append(NewsArticle.topic == topic)
    if source_id:
        filters.append(NewsArticle.source_id == source_id)
    if query:
        pattern = f"%{query.strip()}%"
        filters.append(or_(NewsArticle.title.ilike(pattern), NewsArticle.summary.ilike(pattern)))

    total = db.scalar(select(func.count(NewsArticle.id)).where(*filters)) or 0
    rows = list(
        db.scalars(
            select(NewsArticle)
            .where(*filters)
            .order_by(NewsArticle.published_at.desc(), NewsArticle.fetched_at.desc(), NewsArticle.id.desc())
            .offset(offset)
            .limit(limit)
        )
    )
    return rows, total


def run_news_retention(db: Session, settings: Settings) -> tuple[int, int]:
    now = utcnow()
    archive_result = db.execute(
        update(NewsArticle)
        .where(NewsArticle.status == "published", NewsArticle.expires_at <= now)
        .values(status="archived", archived_at=now)
    )
    delete_before = now - timedelta(days=settings.news_archive_retention_days)
    delete_result = db.execute(
        delete(NewsArticle).where(NewsArticle.status == "archived", NewsArticle.archived_at <= delete_before)
    )
    db.commit()
    return int(archive_result.rowcount or 0), int(delete_result.rowcount or 0)
