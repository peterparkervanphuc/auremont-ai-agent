from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.core.config import settings

# Use SQLite for development if DATABASE_URL not configured
database_url = settings.database_url or "sqlite:///./data/app.db"

# No `if database_url else None` fallback: the line above always yields a URL (SQLite when
# nothing is configured), so the None branch was unreachable while making every caller of
# SessionLocal()/engine look optional — including `get_db`, which would have been calling
# None.
engine = create_engine(
    database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
