# # database.py
# import os
# from sqlalchemy import create_engine
# from sqlalchemy.orm import sessionmaker

# DATABASE_URL = os.getenv(
#     "DATABASE_URL",
#     "postgresql+psycopg://postgres:postgres123@127.0.0.1:5432/partner_api",
# )

# engine = create_engine(
#     DATABASE_URL,
#     pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
#     max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
#     pool_pre_ping=True,
#     pool_recycle=int(os.getenv("DB_POOL_RECYCLE_SECS", "1800")),
# )

# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# def get_db():
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()


# database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from config import get_settings
import logging

logger = logging.getLogger(__name__)
settings = get_settings()

# Enhanced engine with connection pooling
engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=settings.pool_size,
    max_overflow=settings.max_overflow,
    pool_timeout=settings.pool_timeout,
    pool_recycle=settings.pool_recycle,
    pool_pre_ping=True,  # Verify connections before use
    echo=False,  # Set to True for debugging SQL
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db() -> Session:
    """
    Database dependency with proper error handling
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database error: {e}")
        db.rollback()
        raise
    finally:
        db.close()