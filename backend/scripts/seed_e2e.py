"""Non-interactive seed for the Playwright e2e suite (frontend/e2e/smoke.spec.ts).

Creates exactly the one superuser account the suite logs in as — DNI/password match
e2e/smoke.spec.ts's E2E_DNI/E2E_PASSWORD defaults. Nothing else: the smoke tests only
assert each page renders its heading without a console error, which holds on an
otherwise-empty database (see this session's earlier "mucho scroll" work — list pages
already render correctly with zero rows).

Idempotent — safe to run every CI job without first checking whether the user exists.

Usage: run against TEST_DATABASE_URL after `alembic upgrade head`, e.g.:
    DATABASE_URL=$TEST_DATABASE_URL python backend/scripts/seed_e2e.py
"""
from sqlalchemy.orm import Session

from app.core.database import engine
from app.core.security import hash_password
from app.models.identity import User

DNI = "12345678"
PASSWORD = "123456"


def main() -> None:
    with Session(engine) as db:
        existing = db.query(User).filter_by(dni=DNI).one_or_none()
        if existing is not None:
            print(f"[seed_e2e] usuario {DNI} ya existe, no se hace nada")
            return
        user = User(
            dni=DNI,
            username=f"user-{DNI}",
            full_name="E2E Test Admin",
            hashed_password=hash_password(PASSWORD),
            is_active=True,
            is_superuser=True,
        )
        db.add(user)
        db.commit()
        print(f"[seed_e2e] usuario {DNI} creado")


if __name__ == "__main__":
    main()
