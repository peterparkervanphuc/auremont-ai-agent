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

    # The project this consultation session belongs to. The Agent needs it for
    # real-time inventory lookups (`lookup_inventory` requires a project_id) and to
    # filter retrieval to the right project's documents. Nullable because sessions
    # created before this column exist, and a Sale may ask general questions that
    # belong to no specific project.
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)

    created_at = Column(DateTime, default=utcnow, nullable=False)
