from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# Default pool (size=5, max_overflow=10 => 15 concurrent connections) is too small once
# you add ~55 Agents each periodically borrowing a connection for heartbeat/history
# writes (app/api/v1/agents.py) on top of normal HTTP traffic: a burst of concurrent page
# loads (many técnicos opening the dashboard around the same time, or a parallel test
# run) can exhaust it, and uvicorn — a single process — stops accepting new connections
# entirely until requests waiting on QueuePool time out. Sized with real headroom above
# the current fleet rather than tuned tightly to it.
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_size=20, max_overflow=30, future=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
