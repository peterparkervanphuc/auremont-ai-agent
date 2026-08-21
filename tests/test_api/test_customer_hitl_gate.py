"""The customer surface must never display a price/commitment answer.

There is no HITL card in the customer UI and `POST /hitl/{id}/confirm` is SALE/ADMIN-only,
because nobody signs off on a commitment made to themselves. That design is only safe while
a flagged answer is *withheld* on this surface rather than shown — these tests pin that
invariant on both customer paths.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core.deps import get_current_user, get_optional_current_user
from backend.core.enums import SessionStatus, UserRole
from backend.core.mysql_client import Base, get_db
from backend.main import app
from backend.models.chat_session import ChatSession
from backend.models.message import Message
from backend.models.user import User
from backend.services import agent_pipeline
from backend.services.agent_pipeline import PipelineResult


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
def customer(db_session):
    user = User(username="cust", email="cust@example.com", hashed_password="x", role=UserRole.CUSTOMER)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def as_customer(db_session):
    def _login(user: User) -> TestClient:
        app.dependency_overrides[get_db] = lambda: db_session
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_optional_current_user] = lambda: user
        return TestClient(app)

    yield _login
    app.dependency_overrides.clear()


@pytest.fixture
def anonymous_client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_optional_current_user] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def _stub_pipeline(monkeypatch, *, requires_hitl: bool):
    monkeypatch.setattr(
        agent_pipeline,
        "run_pipeline",
        lambda query, project_id=None, db=None, clearance=None, history=None: PipelineResult(
            draft_answer="Giá căn 2PN là 3,6 tỷ đồng.",
            citations=[],
            verifier_score=0.9,
            requires_hitl=requires_hitl,
        ),
    )


def _session_for(db, customer: User) -> ChatSession:
    session = ChatSession(customer_id=customer.id, status=SessionStatus.BOT_HANDLING)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _latest_agent_message(db, session_id: int) -> Message:
    return (
        db.query(Message)
        .filter(Message.session_id == session_id, Message.sender == "agent")
        .order_by(Message.id.desc())
        .first()
    )


class TestLoggedInCustomer:
    def test_a_risky_answer_is_withheld_and_handed_to_a_sale(
        self, as_customer, customer, db_session, monkeypatch
    ):
        """The regression this file exists for: the gate used to apply only to anonymous
        visitors, so a logged-in customer received the priced answer verbatim."""
        _stub_pipeline(monkeypatch, requires_hitl=True)
        session = _session_for(db_session, customer)

        response = as_customer(customer).post(
            f"/api/v1/customer/sessions/{session.id}/messages", json={"content": "Giá căn 2PN?"}
        )

        assert response.status_code == 201, response.text
        assert "3,6 tỷ" not in response.json()["content"]
        assert response.json()["status"] == SessionStatus.WAITING_SALE

        stored = _latest_agent_message(db_session, session.id)
        assert stored.requires_hitl is False
        assert "3,6 tỷ" not in stored.content

    def test_the_session_enters_the_live_queue_so_a_sale_can_take_over(
        self, as_customer, customer, db_session, monkeypatch
    ):
        _stub_pipeline(monkeypatch, requires_hitl=True)
        session = _session_for(db_session, customer)

        as_customer(customer).post(
            f"/api/v1/customer/sessions/{session.id}/messages", json={"content": "Giá căn 2PN?"}
        )

        db_session.refresh(session)
        assert session.status == SessionStatus.WAITING_SALE
        assert session.handoff_requested_at is not None

    def test_a_safe_answer_still_reaches_the_customer_unchanged(
        self, as_customer, customer, db_session, monkeypatch
    ):
        """The gate must not swallow ordinary answers — that would be a regression too."""
        _stub_pipeline(monkeypatch, requires_hitl=False)
        session = _session_for(db_session, customer)

        response = as_customer(customer).post(
            f"/api/v1/customer/sessions/{session.id}/messages", json={"content": "Dự án ở đâu?"}
        )

        assert response.status_code == 201, response.text
        assert response.json()["content"] == "Giá căn 2PN là 3,6 tỷ đồng."
        assert response.json()["status"] == SessionStatus.BOT_HANDLING


class TestAnonymousVisitor:
    def test_a_risky_answer_is_withheld_behind_the_registration_gate(
        self, anonymous_client, db_session, monkeypatch
    ):
        _stub_pipeline(monkeypatch, requires_hitl=True)
        created = anonymous_client.post("/api/v1/customer/sessions/anonymous")
        assert created.status_code == 201, created.text
        session_id = created.json()["session_id"]
        token = created.json()["visitor_token"]

        response = anonymous_client.post(
            f"/api/v1/customer/sessions/{session_id}/messages",
            json={"content": "Giá căn 2PN?"},
            headers={"X-Visitor-Token": token},
        )

        assert response.status_code == 201, response.text
        assert response.json()["gate"] == "closing_intent"
        assert "3,6 tỷ" not in response.json()["content"]

        stored = _latest_agent_message(db_session, session_id)
        assert stored.requires_hitl is False
