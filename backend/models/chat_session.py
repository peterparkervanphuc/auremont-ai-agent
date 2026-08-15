from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from backend.core.mysql_client import Base
from backend.utils.time import utcnow


class ChatSession(Base):
    """A Sale consultation session — holds its own Memory per customer."""

    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Free text entered by the Sale, e.g. "Session: Khách Nguyễn Văn A".
    title = Column(String(255), nullable=True)

    # The customer this session belongs to — each session keeps its own Memory per customer.
    customer_name = Column(String(255), nullable=True)

    # The project this consultation session belongs to: it narrows retrieval to that
    # project's documents and picks which project's stock the inventory API is asked for.
    # Nullable, and genuinely optional — the session-creation form no longer asks the Sale
    # to choose a project, so most rows carry NULL. Inventory still works in that case:
    # `inventory_service.resolve_api_project_id` falls back to the INVENTORY_PROJECT_MAP
    # catch-all rather than refusing the lookup.
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)

    created_at = Column(DateTime, default=utcnow, nullable=False)
