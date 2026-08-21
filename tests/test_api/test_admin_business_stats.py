from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core.deps import get_current_user
from backend.core.mysql_client import Base, get_db
from backend.main import app
from backend.models.chat_session import ChatSession
from backend.models.feedback import Feedback
from backend.models.message import Message
from backend.models.user import User


def test_business_dashboard_excludes_admin_and_e2e_activity():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        admin = User(username="admin", email="admin@example.com", hashed_password="x", role="admin")
        sale = User(username="sale_real", email="sale@example.com", hashed_password="x", role="sale")
        e2e = User(username="e2e_sale_noise", email="e2e@example.com", hashed_password="x", role="sale")
        db.add_all([admin, sale, e2e])
        db.flush()

        real_session = ChatSession(sale_id=sale.id, customer_name="Khách A")
        db.add_all([real_session, ChatSession(sale_id=admin.id), ChatSession(sale_id=e2e.id)])
        db.flush()
        question = Message(session_id=real_session.id, sender="sale", content="Còn căn không?")
        answer = Message(
            session_id=real_session.id,
            sender="agent",
            content="Còn căn.",
            verifier_score=0.8,
            faithfulness=0.9,
            answer_relevancy=0.8,
            requires_hitl=True,
        )
        db.add_all([question, answer])
        db.flush()
        db.add(Feedback(message_id=answer.id, user_id=sale.id, type="helpful"))
        db.commit()

        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: admin
        response = TestClient(app).get("/api/v1/admin/stats/business")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["summary"]["sessions"] == 1
        assert payload["summary"]["active_sales"] == 1
        assert payload["summary"]["questions"] == 1
        assert payload["top_sales"] == [
            {"sale_id": sale.id, "username": "sale_real", "sessions": 1, "customers": 1, "questions": 1}
        ]
        assert payload["feedback_distribution"]["helpful"] == 1
        assert len(payload["quality_trend"]) == 14
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)
