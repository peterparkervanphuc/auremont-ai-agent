from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core.config import settings
from backend.core.mysql_client import Base, get_db
from backend.main import app
from backend.models.news_article import NewsArticle


@pytest.fixture
def news_db() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[NewsArticle.__table__])
    factory = sessionmaker(bind=engine)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture
def news_client(client, news_db, monkeypatch):
    def override_db():
        db = news_db()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(settings, "news_ingestion_key", "test-news-key")
    app.dependency_overrides[get_db] = override_db
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def _article(**overrides):
    payload = {
        "source_id": "vinhomes",
        "canonical_url": "https://vinhomes.vn/vi/tin-tuc/bai-viet-1?utm_source=test",
        "title": "Vinhomes cập nhật tiến độ dự án mới nhất",
        "summary": "Thông tin chính thức về tiến độ và các hạng mục đã hoàn thành.",
        "topic": "project_progress",
        "project_names": ["Vinhomes Ocean Park"],
        "published_at": "2026-08-27T02:00:00",
    }
    payload.update(overrides)
    return payload


def test_news_ingestion_requires_private_key(news_client):
    response = news_client.post("/api/v1/integrations/news", json=_article())
    assert response.status_code == 401


def test_n8n_ingestion_is_idempotent_and_public_to_every_role(news_client):
    headers = {"X-News-Ingestion-Key": "test-news-key"}
    first = news_client.post("/api/v1/integrations/news", json=_article(), headers=headers)
    assert first.status_code == 200
    assert first.json()["created"] is True

    repeated = news_client.post(
        "/api/v1/integrations/news",
        json=_article(canonical_url="https://www.vinhomes.vn/vi/tin-tuc/bai-viet-1?utm_campaign=again"),
        headers=headers,
    )
    assert repeated.status_code == 200
    assert repeated.json()["created"] is False

    exact_retry = news_client.post("/api/v1/integrations/news", json=_article(), headers=headers)
    assert exact_retry.status_code == 200
    assert exact_retry.json()["created"] is False
    assert exact_retry.json()["content_changed"] is False

    public_feed = news_client.get("/api/v1/news")
    assert public_feed.status_code == 200
    assert public_feed.json()["total"] == 1
    assert public_feed.json()["items"][0]["source_name"] == "Vinhomes"


def test_ingestion_rejects_domain_spoofing(news_client):
    response = news_client.post(
        "/api/v1/integrations/news",
        json=_article(canonical_url="https://vinhomes.vn.attacker.example/fake-news"),
        headers={"X-News-Ingestion-Key": "test-news-key"},
    )
    assert response.status_code == 422
