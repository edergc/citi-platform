"""Login: valid/invalid credentials, and the brute-force rate limiter (app/core/rate_limit.py)."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1.auth import LOGIN_MAX_PER_DNI
from tests.conftest import make_user


def test_login_succeeds_with_correct_credentials(client: TestClient, db_session: Session) -> None:
    make_user(db_session, dni="11111111", password="correct-password")
    db_session.commit()

    response = client.post("/api/v1/auth/login", json={"dni": "11111111", "password": "correct-password"})

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]


def test_login_fails_with_wrong_password(client: TestClient, db_session: Session) -> None:
    make_user(db_session, dni="22222222", password="correct-password")
    db_session.commit()

    response = client.post("/api/v1/auth/login", json={"dni": "22222222", "password": "wrong-password"})

    assert response.status_code == 401


def test_login_fails_for_unknown_dni(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"dni": "00000000", "password": "anything"})

    assert response.status_code == 401


def test_login_fails_for_inactive_user(client: TestClient, db_session: Session) -> None:
    make_user(db_session, dni="33333333", password="correct-password", is_active=False)
    db_session.commit()

    response = client.post("/api/v1/auth/login", json={"dni": "33333333", "password": "correct-password"})

    assert response.status_code == 401


def test_repeated_failed_logins_get_rate_limited(client: TestClient, db_session: Session) -> None:
    dni = "44444444"
    make_user(db_session, dni=dni, password="correct-password")
    db_session.commit()

    for _ in range(LOGIN_MAX_PER_DNI):
        client.post("/api/v1/auth/login", json={"dni": dni, "password": "wrong-password"})

    response = client.post("/api/v1/auth/login", json={"dni": dni, "password": "wrong-password"})

    assert response.status_code == 429
