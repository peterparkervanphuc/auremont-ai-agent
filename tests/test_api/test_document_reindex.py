"""Re-indexing a stored document — the route that migrates old vectors to a new shape.

Enabling hybrid retrieval changed what a Qdrant point looks like: it now carries a BM25
vector beside the dense one. Documents ingested before that have to be rewritten, and
this endpoint is how an Admin does it, one document at a time, from the original file
still held in MinIO.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core.deps import get_current_user
from backend.core.enums import UserRole
from backend.core.mysql_client import Base, get_db
from backend.main import app
from backend.models.user import User
from backend.repositories.document import create_document
from backend.routers import documents as documents_router
from backend.schemas.document import DocumentCreate
from backend.services.ingestion_service import DocumentIngestionError


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = testing_session()

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def admin(db_session):
    user = User(username="admin1", email="admin@example.com", hashed_password="x", role=UserRole.ADMIN)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def sale(db_session):
    user = User(username="sale1", email="sale@example.com", hashed_password="x", role=UserRole.SALE)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def client(db_session, admin):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: admin
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def document(db_session, admin):
    return create_document(
        db_session,
        DocumentCreate(title="bang-gia.pdf", file_path="documents/1/abc-bang-gia.pdf"),
        uploaded_by=admin.id,
    )


def test_admin_can_reindex_a_stored_document(client, monkeypatch, document):
    calls = []
    monkeypatch.setattr(
        documents_router,
        "reindex_document",
        lambda db, *, document_id: calls.append(document_id) or document,
    )

    response = client.post(f"/api/v1/documents/{document.id}/reindex")

    assert response.status_code == 200, response.text
    assert calls == [document.id]
    assert response.json()["document_id"] == document.id


def test_a_failed_reindex_reports_an_error(client, monkeypatch, document):
    """Re-indexing deletes the old vectors first, so a silent failure would leave the
    document unreachable — the Admin has to be told it needs running again."""

    def _boom(db, *, document_id):
        raise DocumentIngestionError("MinIO unavailable")

    monkeypatch.setattr(documents_router, "reindex_document", _boom)

    response = client.post(f"/api/v1/documents/{document.id}/reindex")

    assert response.status_code == 500


def test_a_sale_cannot_reindex(db_session, sale, document):
    """Re-indexing rewrites the knowledge base; it stays an Admin-only operation."""
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: sale

    try:
        response = TestClient(app).post(f"/api/v1/documents/{document.id}/reindex")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
