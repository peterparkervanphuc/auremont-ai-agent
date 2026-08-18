"""Cảnh báo mâu thuẫn: quyết định 'giữ tài liệu nào' của Admin phải được thi hành."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core.deps import get_current_user
from backend.core.enums import DocumentStatus, UserRole
from backend.core.mysql_client import Base, get_db
from backend.main import app
from backend.models.user import User
from backend.repositories.conflict_flag import create_conflict
from backend.repositories.document import create_document, get_document
from backend.routers import admin_conflicts as conflicts_router
from backend.schemas.document import DocumentCreate


@pytest.fixture
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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
    user = User(username="adm1", email="a@x.com", hashed_password="x", role=UserRole.ADMIN)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def vector_syncs(monkeypatch):
    """Stand in for Qdrant and record what the router pushed into it.

    Resolving a conflict now mirrors the decision into the vector payload, and there is
    no Qdrant in a unit test run. Recording the calls rather than dropping them keeps the
    assertion available: MySQL saying BLOCKED means nothing if retrieval was never told.
    """
    calls: list[dict] = []
    monkeypatch.setattr(
        conflicts_router,
        "update_document_vector_metadata",
        lambda document_id, **kwargs: calls.append({"document_id": document_id, **kwargs}),
    )
    return calls


@pytest.fixture
def client(db_session, admin, vector_syncs):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: admin
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def conflict(db_session):
    """Hai bản bảng giá của cùng một dự án, bị flag là mâu thuẫn."""
    old = create_document(db_session, DocumentCreate(title="Bảng giá v1"))
    new = create_document(db_session, DocumentCreate(title="Bảng giá v2"))
    flag = create_conflict(db_session, document_id_a=old.id, document_id_b=new.id, description="Giá khác nhau")
    return flag, old, new


def test_resolving_keeps_the_chosen_document_and_blocks_the_other(client, db_session, conflict):
    flag, old, new = conflict

    response = client.post(f"/api/v1/admin/conflicts/{flag.id}/resolve", json={"keep_document_id": new.id})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "resolved"

    # Bản bị bác bỏ phải bị vô hiệu hoá, nếu không Agent vẫn trích dẫn nó.
    assert get_document(db_session, new.id).status != DocumentStatus.BLOCKED
    assert get_document(db_session, old.id).status == DocumentStatus.BLOCKED


def test_rejected_document_is_removed_from_retrieval(client, db_session, conflict, vector_syncs):
    """BLOCKED một mình không đủ: rag_service lọc theo is_current, không nhìn `status`.

    Thiếu bước này, Admin bấm "ưu tiên bản mới" xong bảng giá cũ vẫn tiếp tục
    được dùng để trả lời khách.
    """
    flag, old, new = conflict

    client.post(f"/api/v1/admin/conflicts/{flag.id}/resolve", json={"keep_document_id": new.id})

    assert get_document(db_session, old.id).is_current is False
    assert get_document(db_session, new.id).is_current is True
    assert vector_syncs == [
        {
            "document_id": old.id,
            "review_status": get_document(db_session, old.id).review_status,
            "legal_status": get_document(db_session, old.id).legal_status,
            "category": get_document(db_session, old.id).category,
            "is_current": False,
        }
    ]


def test_the_two_choices_are_not_interchangeable(client, db_session, conflict):
    """Giữ tài liệu A phải chặn B — ngược hẳn với lựa chọn kia."""
    flag, old, new = conflict

    client.post(f"/api/v1/admin/conflicts/{flag.id}/resolve", json={"keep_document_id": old.id})

    assert get_document(db_session, old.id).status != DocumentStatus.BLOCKED
    assert get_document(db_session, new.id).status == DocumentStatus.BLOCKED


def test_resolved_conflict_leaves_the_open_list(client, conflict):
    flag, _old, new = conflict
    assert [c["id"] for c in client.get("/api/v1/admin/conflicts").json()] == [flag.id]

    client.post(f"/api/v1/admin/conflicts/{flag.id}/resolve", json={"keep_document_id": new.id})

    assert client.get("/api/v1/admin/conflicts").json() == []


def test_rejects_a_document_outside_the_conflict(client, db_session, conflict):
    """Nếu không kiểm, quyết định của Admin sẽ áp lên nhầm tài liệu."""
    flag, old, new = conflict
    unrelated = create_document(db_session, DocumentCreate(title="Tài liệu không liên quan"))

    response = client.post(f"/api/v1/admin/conflicts/{flag.id}/resolve", json={"keep_document_id": unrelated.id})
    assert response.status_code == 400

    # Không tài liệu nào bị chặn nhầm, flag vẫn mở.
    assert get_document(db_session, old.id).status != DocumentStatus.BLOCKED
    assert get_document(db_session, new.id).status != DocumentStatus.BLOCKED
    assert [c["id"] for c in client.get("/api/v1/admin/conflicts").json()] == [flag.id]


def test_unknown_conflict_returns_404(client, conflict):
    _flag, _old, new = conflict
    assert client.post("/api/v1/admin/conflicts/9999/resolve", json={"keep_document_id": new.id}).status_code == 404
