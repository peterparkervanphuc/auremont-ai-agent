from sqlalchemy import JSON, Column, DateTime, String

from backend.core.mysql_client import Base
from backend.utils.time import utcnow


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    location = Column(String(255), nullable=True)
    description = Column(String(2000), nullable=True)
    # Full payload (pricing, amenities, highlights, contact, documents...) — richer
    # than the three structured columns above, used to render project detail views
    # without adding child tables.
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
