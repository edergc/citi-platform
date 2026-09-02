import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.fernet import Fernet
from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_token(subject: str, expires_delta: timedelta, extra_claims: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {"sub": subject, "iat": now, "exp": now + expires_delta}
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(subject: str) -> str:
    return create_token(
        subject,
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        extra_claims={"type": "access"},
    )


def create_refresh_token(subject: str) -> str:
    return create_token(
        subject,
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        extra_claims={"type": "refresh"},
    )


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def _fernet() -> Fernet:
    return Fernet(settings.CONFIG_ENCRYPTION_KEY.encode())


def encrypt_secret(plain_value: str) -> str:
    return _fernet().encrypt(plain_value.encode()).decode()


def decrypt_secret(encrypted_value: str) -> str:
    return _fernet().decrypt(encrypted_value.encode()).decode()


def generate_secure_token() -> str:
    return secrets.token_urlsafe(32)


def hash_secure_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_enrollment_token() -> str:
    return generate_secure_token()


def hash_enrollment_token(token: str) -> str:
    return hash_secure_token(token)


def create_agent_token(agent_id: str) -> str:
    return create_token(agent_id, timedelta(days=3650), extra_claims={"type": "agent"})
