"""Shared test fixtures. Runs against TEST_DATABASE_URL (a real Postgres database, never
TEST_DATABASE_URL == DATABASE_URL — several models use Postgres-only types like JSONB/UUID
that SQLite can't represent, so this deliberately isn't sqlite-in-memory).

Each test gets its own transaction that's rolled back at teardown (SQLAlchemy 2.0's
join_transaction_mode="create_savepoint" pattern — app code calling db.commit() only
releases a SAVEPOINT, the outer transaction is always rolled back), so tests never leave
data behind and can run in any order without truncating tables between them.
"""

import uuid
from collections.abc import Generator
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import rate_limiter
from app.core.security import hash_password
from app.main import app
from app.models.base import Base
from app.models.backups import BackupJob
from app.models.identity import Permission, Role, User, UserRoleAssignment
from app.models.infrastructure import Server, Site
from app.models.systems import Service, System

if settings.TEST_DATABASE_URL == settings.DATABASE_URL:
    raise RuntimeError(
        "TEST_DATABASE_URL is the same as DATABASE_URL — refusing to run tests against the "
        "real database. Set TEST_DATABASE_URL in backend/.env to a separate database."
    )


@pytest.fixture(scope="session")
def test_engine():
    engine = create_engine(settings.TEST_DATABASE_URL, future=True)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(test_engine) -> Generator[Session, None, None]:
    connection = test_engine.connect()
    trans = connection.begin()
    session_factory = sessionmaker(bind=connection, future=True, join_transaction_mode="create_savepoint")
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    """rate_limiter (app/core/rate_limit.py) is an in-process singleton, not DB state — the
    transactional rollback in db_session doesn't touch it. TestClient requests all share the
    same client_ip ("testclient"), so without this, attempts would accumulate across every
    test in the session and eventually trip LOGIN_MAX_PER_IP for unrelated tests."""
    rate_limiter._attempts.clear()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Deliberately NOT `with TestClient(app) as c:` — entering as a context manager
    fires FastAPI's lifespan, which starts main.py's 6 background loops (backup/metrics
    retention, synthetic checks, the backup scheduler, ...) against the REAL
    app.core.database.SessionLocal/DATABASE_URL, not this fixture's db_session override —
    those loops build their own sessions directly and don't go through get_db at all. A
    plain (non-`with`) TestClient never sends the lifespan scope, so routes still work
    (they only need get_db, which is overridden below) without ever touching prod data."""
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


# --- Factories -------------------------------------------------------------------------
# Plain helper functions (not fixtures) so a test can create as many/few of these as it
# actually needs, with whatever field overrides matter for that test.


def make_user(
    db: Session,
    *,
    dni: str = "12345678",
    password: str = "password123",
    full_name: str = "Test User",
    is_superuser: bool = False,
    is_active: bool = True,
) -> User:
    user = User(
        dni=dni,
        username=f"user-{dni}",
        full_name=full_name,
        hashed_password=hash_password(password),
        is_active=is_active,
        is_superuser=is_superuser,
    )
    db.add(user)
    db.flush()
    return user


def make_site(db: Session, *, name: str = "Sede de prueba", code: str | None = None) -> Site:
    site = Site(name=name, code=code or f"TEST-{uuid.uuid4().hex[:8]}")
    db.add(site)
    db.flush()
    return site


def make_server(db: Session, *, site_id: uuid.UUID | None = None, hostname: str = "test-server") -> Server:
    server = Server(site_id=site_id, hostname=hostname, os_type="linux")
    db.add(server)
    db.flush()
    return server


def make_system(db: Session, *, name: str = "Test System") -> System:
    system = System(name=name, slug=f"test-system-{uuid.uuid4().hex[:8]}")
    db.add(system)
    db.flush()
    return system


def make_service(db: Session, *, system_id: uuid.UUID | None = None, name: str = "Test Service") -> Service:
    service = Service(
        system_id=system_id or make_system(db).id,
        name=name,
        type="backend",
        control_strategy="windows_service",
    )
    db.add(service)
    db.flush()
    return service


def make_backup_job(
    db: Session,
    *,
    service_id: uuid.UUID | None = None,
    schedule_cron: str | None = None,
    enabled: bool = True,
    created_at: datetime | None = None,
) -> BackupJob:
    job = BackupJob(
        service_id=service_id or make_service(db).id,
        type="files",
        source_path="/tmp/source",
        storage_path="/tmp/storage",
        schedule_cron=schedule_cron,
        enabled=enabled,
    )
    if created_at is not None:
        job.created_at = created_at
    db.add(job)
    db.flush()
    return job


def grant_permission(db: Session, user: User, code: str) -> None:
    """Creates a fresh role + permission granting `code`, and assigns it to `user`."""
    permission = db.query(Permission).filter_by(code=code).one_or_none()
    if permission is None:
        permission = Permission(code=code)
        db.add(permission)
        db.flush()
    role = Role(name=f"role-{uuid.uuid4().hex[:8]}")
    role.permissions.append(permission)  # via the role_permissions secondary table
    db.add(role)
    db.flush()
    db.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
    db.flush()
