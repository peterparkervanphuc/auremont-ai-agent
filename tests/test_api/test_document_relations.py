"""Version relations must retire superseded documents from RAG safely."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core.deps import get_current_user
from backend.core.enums import DocumentReviewStatus, LegalStatus, UserRole
from backend.core.mysql_client import Base, get_db
from backend.main import app
from backend.models.user import User
from backend.repositories.document import create_document, get_document
from backend.routers import document_relations as relations_router
from backend.schemas.document import DocumentCreate


@pytest.fixture
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = factory()
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
def client(db_session, admin):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: admin
    original_sync = relations_router.update_document_vector_metadata
    relations_router.update_document_vector_metadata = lambda *_args, **_kwargs: None
    yield TestClient(app)
    relations_router.update_document_vector_metadata = original_sync
    app.dependency_overrides.clear()


def test_approved_replacement_retires_the_old_document(client, db_session):
    old = create_document(db_session, DocumentCreate(title="CSBH tháng 07"))
    new = create_document(db_session, DocumentCreate(title="CSBH tháng 08"))
    old.review_status = DocumentReviewStatus.APPROVED
    new.review_status = DocumentReviewStatus.APPROVED
    db_session.commit()

    created = client.post(
        "/api/v1/document-relations",
        json={
            "source_document_id": new.id,
            "target_document_id": old.id,
            "relation_type": "replaces",
            "confidence": 0.95,
        },
    )
    assert created.status_code == 201, created.text

    response = client.post(
        f"/api/v1/document-relations/{created.json()['id']}/review",
        json={"approve": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["review_status"] == "approved"
    assert get_document(db_session, old.id).is_current is False
    assert get_document(db_session, new.id).is_current is True


def test_approved_repeal_marks_legal_document_repealed(client, db_session):
    old = create_document(db_session, DocumentCreate(title="Nghị định cũ"))
    new = create_document(db_session, DocumentCreate(title="Nghị định mới"))
    old.legal_status = LegalStatus.EFFECTIVE
    db_session.commit()

    created = client.post(
        "/api/v1/document-relations",
        json={
            "source_document_id": new.id,
            "target_document_id": old.id,
            "relation_type": "repeals",
        },
    )
    response = client.post(
        f"/api/v1/document-relations/{created.json()['id']}/review",
        json={"approve": True},
    )

    assert response.status_code == 200, response.text
    old = get_document(db_session, old.id)
    assert old.is_current is False
    assert old.legal_status == LegalStatus.REPEALED


def test_relation_cannot_link_a_document_to_itself(client, db_session):
    document = create_document(db_session, DocumentCreate(title="Một tài liệu"))
    response = client.post(
        "/api/v1/document-relations",
        json={
            "source_document_id": document.id,
            "target_document_id": document.id,
            "relation_type": "updates",
        },
    )
    assert response.status_code == 400
