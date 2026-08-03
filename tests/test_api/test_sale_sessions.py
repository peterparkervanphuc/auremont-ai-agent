"""Sale session flow — ownership isolation and the two delete endpoints the UI calls."""

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
from backend.services import agent_pipeline
from backend.services.agent_pipeline import PipelineResult


@pytest.fixture
def db_session():
    """In-memory SQLite so the suite runs without a live MySQL."""
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
def sales(db_session):
    """Two distinct sales, so cross-account access can be exercised."""
    a = User(username="sale_a", email="a@example.com", hashed_password="x", role=UserRole.SALE)
    b = User(username="sale_b", email="b@example.com", hashed_password="x", role=UserRole.SALE)
    db_session.add_all([a, b])
    db_session.commit()
    db_session.refresh(a)
    db_session.refresh(b)
    return a, b


@pytest.fixture
def admin(db_session):
    """Admin cũng chat được — dùng để kiểm tra role không bị chặn khỏi luồng chat."""
    user = User(username="admin_a", email="admin@example.com", hashed_password="x", role=UserRole.ADMIN)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def as_sale(db_session, sales):
    """Client factory that authenticates as a given user, bypassing JWT."""

    def _login(user: User) -> TestClient:
        app.dependency_overrides[get_db] = lambda: db_session
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app)

    yield _login
    app.dependency_overrides.clear()


@pytest.fixture
def stub_pipeline(monkeypatch):
    """agent_pipeline.run_pipeline is still a TODO stub — these tests cover the
    session/message routes, not the RAG pipeline, so give it a canned answer."""
    monkeypatch.setattr(
        agent_pipeline,
        "run_pipeline",
        lambda query, project_id=None: PipelineResult(
            draft_answer=f"Trả lời cho: {query}",
            citations=[],
            verifier_score=0.9,
            requires_hitl=False,
        ),
    )


def _create_session(client: TestClient, title: str = "Khách A") -> int:
    response = client.post("/api/v1/sale/sessions", json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_delete_session_removes_it_from_the_list(as_sale, sales):
    client = as_sale(sales[0])
    session_id = _create_session(client)

    assert client.delete(f"/api/v1/sale/sessions/{session_id}").status_code == 204

    remaining = client.get("/api/v1/sale/sessions").json()
    assert [s["id"] for s in remaining] == []


def test_clear_messages_keeps_the_session(as_sale, sales, stub_pipeline):
    client = as_sale(sales[0])
    session_id = _create_session(client)
    client.post(f"/api/v1/sale/sessions/{session_id}/messages", json={"content": "Giá căn 2PN?"})

    assert client.get(f"/api/v1/sale/sessions/{session_id}/messages").json() != []

    assert client.delete(f"/api/v1/sale/sessions/{session_id}/messages").status_code == 204

    assert client.get(f"/api/v1/sale/sessions/{session_id}/messages").json() == []
    # The session itself must survive so the Sale keeps the customer thread.
    assert [s["id"] for s in client.get("/api/v1/sale/sessions").json()] == [session_id]


def test_admin_can_use_the_chat_flow(as_sale, admin, stub_pipeline):
    """Admin cũng tư vấn được: tạo phiên, hỏi, và nhận câu trả lời."""
    client = as_sale(admin)
    session_id = _create_session(client, title="Khách của Admin")

    reply = client.post(f"/api/v1/sale/sessions/{session_id}/messages", json={"content": "Giá căn 2PN?"})
    assert reply.status_code == 201, reply.text
    assert reply.json()["sender"] == "agent"

    assert [s["id"] for s in client.get("/api/v1/sale/sessions").json()] == [session_id]


def test_admin_cannot_read_a_sales_session(as_sale, sales, admin, stub_pipeline):
    """Mở chat cho admin không được phá cách ly: phiên của sale vẫn là riêng tư."""
    owner = sales[0]
    session_id = _create_session(as_sale(owner), title="Khách riêng của Sale")

    admin_client = as_sale(admin)
    assert admin_client.get(f"/api/v1/sale/sessions/{session_id}/messages").status_code == 404
    assert admin_client.delete(f"/api/v1/sale/sessions/{session_id}").status_code == 404
    # Phiên của sale không lọt vào danh sách của admin.
    assert admin_client.get("/api/v1/sale/sessions").json() == []


def test_a_sale_cannot_touch_another_sales_session(as_sale, sales, stub_pipeline):
    owner, intruder = sales
    owner_client = as_sale(owner)
    session_id = _create_session(owner_client, title="Khách riêng")

    other_client = as_sale(intruder)

    # 404 (not 403) so session ids of other sales stay unguessable.
    assert other_client.get(f"/api/v1/sale/sessions/{session_id}/messages").status_code == 404
    assert other_client.delete(f"/api/v1/sale/sessions/{session_id}").status_code == 404
    assert (
        other_client.post(
            f"/api/v1/sale/sessions/{session_id}/messages", json={"content": "hi"}
        ).status_code
        == 404
    )

    # And the owner's session is untouched.
    assert [s["id"] for s in as_sale(owner).get("/api/v1/sale/sessions").json()] == [session_id]
