"""Admin duyệt metadata tài liệu dự án."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core.deps import get_current_user
from backend.core.enums import (
    DocumentCategory,
    DocumentReviewStatus,
    LegalStatus,
    UserRole,
)
from backend.core.mysql_client import Base, get_db
from backend.main import app
from backend.models.user import User
from backend.repositories.document import create_document
from backend.routers import documents as documents_router
from backend.schemas.document import DocumentCreate


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)

    testing_session = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
    db = testing_session()

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def admin(db_session):
    user = User(
        username="admin1",
        email="admin@example.com",
        hashed_password="x",
        role=UserRole.ADMIN,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def sale(db_session):
    user = User(
        username="sale1",
        email="sale@example.com",
        hashed_password="x",
        role=UserRole.SALE,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def client(db_session, admin):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: admin
    # API tests exercise the DB contract; Qdrant is tested independently.
    original_metadata_sync = documents_router.update_document_vector_metadata
    original_visibility_sync = documents_router.update_document_vector_visibility
    original_clear_cache = documents_router.clear_cache
    documents_router.update_document_vector_metadata = lambda *_args, **_kwargs: None
    documents_router.update_document_vector_visibility = lambda *_args, **_kwargs: None
    documents_router.clear_cache = lambda: None

    yield TestClient(app)

    documents_router.update_document_vector_metadata = original_metadata_sync
    documents_router.update_document_vector_visibility = original_visibility_sync
    documents_router.clear_cache = original_clear_cache
    app.dependency_overrides.clear()


def test_pending_review_returns_only_unapproved_documents(
    client,
    db_session,
    admin,
):
    pending = create_document(
        db_session,
        DocumentCreate(title="CSBH The Beverly T8.pdf"),
        uploaded_by=admin.id,
    )

    approved = create_document(
        db_session,
        DocumentCreate(title="Bang gia The Beverly T8.pdf"),
        uploaded_by=admin.id,
    )
    approved.review_status = DocumentReviewStatus.APPROVED
    db_session.commit()

    response = client.get("/api/v1/documents/pending-review")

    assert response.status_code == 200, response.text

    document_ids = [item["id"] for item in response.json()]
    assert pending.id in document_ids
    assert approved.id not in document_ids


def test_admin_can_approve_project_document_classification(
    client,
    db_session,
    admin,
):
    document = create_document(
        db_session,
        DocumentCreate(title="CSBH The Beverly T8.pdf"),
        uploaded_by=admin.id,
    )

    response = client.patch(
        f"/api/v1/documents/{document.id}/classification",
        json={
            "category": "sales_policy",
            "subcategory": "standard_policy",
            "subdivision_names": ["The Beverly"],
            "building_codes": ["BE1", "BE2"],
            "unit_types": ["1PN+", "2PN", "3PN"],
            "applicable_area": "Ocean Park 3",
            "document_summary": ("Chính sách bán hàng tháng 08/2026 cho phân khu The Beverly."),
            "version_label": "Tháng 08/2026",
            "effective_date": "2026-08-01",
            "expiry_date": "2026-08-31",
            "applicable_period": "08/2026",
            "legal_status": "unknown",
        },
    )

    assert response.status_code == 200, response.text

    body = response.json()
    assert body["category"] == DocumentCategory.SALES_POLICY
    assert body["review_status"] == DocumentReviewStatus.APPROVED
    assert body["subdivision_names"] == ["The Beverly"]
    assert body["building_codes"] == ["BE1", "BE2"]
    assert body["unit_types"] == ["1PN+", "2PN", "3PN"]
    assert body["effective_date"] == "2026-08-01"
    assert body["reviewed_by"] == admin.id
    assert body["reviewed_at"] is not None


def test_admin_can_approve_legal_document_classification(
    client,
    db_session,
    admin,
):
    document = create_document(
        db_session,
        DocumentCreate(title="Nghi dinh 96 2024 ND CP.pdf"),
        uploaded_by=admin.id,
    )

    response = client.patch(
        f"/api/v1/documents/{document.id}/classification",
        json={
            "category": "legal_document",
            "legal_document_type": "Nghị định",
            "legal_document_number": "96/2024/NĐ-CP",
            "legal_issuer": "Chính phủ",
            "legal_domain": "Kinh doanh bất động sản",
            "legal_status": "effective",
        },
    )

    assert response.status_code == 200, response.text

    body = response.json()
    assert body["category"] == DocumentCategory.LEGAL_DOCUMENT
    assert body["legal_document_number"] == "96/2024/NĐ-CP"
    assert body["legal_status"] == LegalStatus.EFFECTIVE
    assert body["review_status"] == DocumentReviewStatus.APPROVED


def test_sale_cannot_approve_document_classification(
    client,
    db_session,
    admin,
    sale,
):
    document = create_document(
        db_session,
        DocumentCreate(title="Tai lieu noi bo.pdf"),
        uploaded_by=admin.id,
    )

    # Đổi user hiện tại trong dependency override thành Sale.
    app.dependency_overrides[get_current_user] = lambda: sale

    response = client.patch(
        f"/api/v1/documents/{document.id}/classification",
        json={
            "category": "internal_guide",
            "legal_status": "unknown",
        },
    )

    assert response.status_code == 403


def test_classifying_an_unknown_document_returns_404(client):
    response = client.patch(
        "/api/v1/documents/999999/classification",
        json={
            "category": "other",
            "legal_status": "unknown",
        },
    )

    assert response.status_code == 404


# --- Changing visibility must reach Qdrant, not just MySQL — rag_service's retrieval
# filter reads the payload it baked in at ingestion time, so a stale payload means the
# dropdown in DocumentsTab.tsx silently has no effect on what customers can retrieve. ---


def test_changing_visibility_syncs_the_vector_store(client, db_session, admin):
    document = create_document(
        db_session,
        DocumentCreate(title="Zurich_VHOP_ThongTinDuAn_Full.pdf"),
        uploaded_by=admin.id,
    )
    calls = []
    documents_router.update_document_vector_visibility = lambda doc_id, visibility: calls.append((doc_id, visibility))

    response = client.patch(
        f"/api/v1/documents/{document.id}/visibility",
        json={"visibility": "public"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["visibility"] == "public"
    assert calls == [(document.id, "public")]


def test_changing_visibility_clears_the_semantic_cache(client, db_session, admin):
    """Otherwise a question cached while this document was still internal keeps serving
    that stale answer forever after it goes public — the cache has no idea anything about
    this specific document changed, so the only correct move is clearing all of it."""
    document = create_document(
        db_session,
        DocumentCreate(title="Zurich_VHOP_ThongTinDuAn_Full.pdf"),
        uploaded_by=admin.id,
    )
    calls = []
    documents_router.clear_cache = lambda: calls.append("cleared")

    response = client.patch(
        f"/api/v1/documents/{document.id}/visibility",
        json={"visibility": "public"},
    )

    assert response.status_code == 200, response.text
    assert calls == ["cleared"]


def test_visibility_sync_failure_returns_503(client, db_session, admin):
    from backend.services.vector_store_service import VectorStoreError

    document = create_document(
        db_session,
        DocumentCreate(title="Zurich_VHOP_ThongTinDuAn_Full.pdf"),
        uploaded_by=admin.id,
    )

    def _boom(*_args, **_kwargs):
        raise VectorStoreError("Qdrant unreachable")

    documents_router.update_document_vector_visibility = _boom

    response = client.patch(
        f"/api/v1/documents/{document.id}/visibility",
        json={"visibility": "public"},
    )

    assert response.status_code == 503
    # The DB write is not rolled back — retrieval still uses the pre-change value
    # (visibility stays "internal" in Qdrant too), so nothing is served inconsistently;
    # only the Admin needs to know the toggle didn't fully take effect.
    db_session.refresh(document)
    assert document.visibility == "public"


def test_changing_visibility_for_an_unknown_document_returns_404(client):
    response = client.patch(
        "/api/v1/documents/999999/visibility",
        json={"visibility": "public"},
    )

    assert response.status_code == 404
