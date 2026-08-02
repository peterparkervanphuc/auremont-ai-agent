from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.core.config import settings

# Use SQLite for development if DATABASE_URL not configured
database_url = settings.database_url or "sqlite:///./data/app.db"

engine = create_engine(
    database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
) if database_url else None

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine else None

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
