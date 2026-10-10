# database.py
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()
DATABASE_URL = settings.database_url

# Force psycopg v3 driver
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(
    DATABASE_URL,
    pool_size=settings.pool_size,
    max_overflow=settings.max_overflow,
    pool_timeout=settings.pool_timeout,
    pool_recycle=settings.pool_recycle,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        # SQLAlchemy exception strings can include bound partner/recipient data.
        db.rollback()
        raise
    finally:
        db.close()
