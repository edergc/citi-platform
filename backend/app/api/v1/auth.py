import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import client_ip, enforce_not_blocked, rate_limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    decrypt_secret,
    generate_secure_token,
    hash_password,
    hash_secure_token,
    verify_password,
)
from app.models.identity import PasswordResetToken, User
from app.models.monitoring import NotificationChannel, NotificationChannelType
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.schemas.user import UserRead
from app.services.email_templates import render_password_reset
from app.services.audit import log_action
from app.services.notification_senders import send_email
from app.services.user_presentation import build_user_read

router = APIRouter(prefix="/auth", tags=["auth"])

RESET_TOKEN_TTL = timedelta(hours=1)
GENERIC_FORGOT_PASSWORD_MESSAGE = "Si el DNI está registrado, se enviará un correo con instrucciones para restablecer la contraseña."

# Rate limiting windows (brute-force protection). See app/core/rate_limit.py.
LOGIN_MAX_PER_IP = 20
LOGIN_MAX_PER_DNI = 5
LOGIN_WINDOW_SECONDS = 15 * 60
FORGOT_PASSWORD_MAX_PER_IP = 5
FORGOT_PASSWORD_WINDOW_SECONDS = 60 * 60
RESET_PASSWORD_MAX_PER_IP = 10
RESET_PASSWORD_WINDOW_SECONDS = 60 * 60
CHANGE_PASSWORD_MAX_PER_USER = 5
CHANGE_PASSWORD_WINDOW_SECONDS = 15 * 60
TOO_MANY_ATTEMPTS_MESSAGE = "Demasiados intentos. Intenta nuevamente más tarde."


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    ip_key = f"login:ip:{client_ip(request)}"
    dni_key = f"login:dni:{payload.dni}"
    enforce_not_blocked(ip_key, LOGIN_MAX_PER_IP, LOGIN_WINDOW_SECONDS, TOO_MANY_ATTEMPTS_MESSAGE)
    enforce_not_blocked(dni_key, LOGIN_MAX_PER_DNI, LOGIN_WINDOW_SECONDS, TOO_MANY_ATTEMPTS_MESSAGE)

    user = db.scalar(select(User).where(User.dni == payload.dni))
    if user is None or not user.is_active or not verify_password(payload.password, user.hashed_password):
        rate_limiter.record_attempt(ip_key)
        rate_limiter.record_attempt(dni_key)
        if user is None:
            reason = "usuario no encontrado"
        elif not user.is_active:
            reason = "cuenta inactiva"
        else:
            reason = "contraseña incorrecta"
        log_action(
            db, user, "auth.login_failed", "user", user.id if user else None,
            details={"dni": payload.dni, "razon": reason}, request=request,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="DNI o contraseña incorrectos")

    rate_limiter.reset(dni_key)
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    log_action(db, user, "auth.login", "user", user.id, request=request)

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        claims = decode_token(payload.refresh_token)
        if claims.get("type") != "refresh":
            raise ValueError("not a refresh token")
    except (JWTError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido") from exc

    try:
        user_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido") from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario inválido")

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserRead:
    return build_user_read(db, current_user)


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    user_key = f"change_password:user:{current_user.id}"
    enforce_not_blocked(user_key, CHANGE_PASSWORD_MAX_PER_USER, CHANGE_PASSWORD_WINDOW_SECONDS, TOO_MANY_ATTEMPTS_MESSAGE)

    if not verify_password(payload.current_password, current_user.hashed_password):
        rate_limiter.record_attempt(user_key)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La contraseña actual es incorrecta")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La contraseña debe tener al menos 8 caracteres")

    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()
    log_action(db, current_user, "auth.password_changed", "user", current_user.id, request=request)
    return MessageResponse(message="Contraseña actualizada correctamente.")


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)) -> MessageResponse:
    ip_key = f"forgot_password:ip:{client_ip(request)}"
    enforce_not_blocked(ip_key, FORGOT_PASSWORD_MAX_PER_IP, FORGOT_PASSWORD_WINDOW_SECONDS, TOO_MANY_ATTEMPTS_MESSAGE)
    rate_limiter.record_attempt(ip_key)

    user = db.scalar(select(User).where(User.dni == payload.dni))

    if user is not None and user.is_active and user.email:
        channel = db.scalar(
            select(NotificationChannel).where(
                NotificationChannel.type == NotificationChannelType.email,
                NotificationChannel.enabled.is_(True),
            )
        )
        if channel is not None:
            token = generate_secure_token()
            db.add(
                PasswordResetToken(
                    user_id=user.id,
                    token_hash=hash_secure_token(token),
                    expires_at=datetime.now(timezone.utc) + RESET_TOKEN_TTL,
                )
            )
            db.commit()

            config = json.loads(decrypt_secret(channel.config_encrypted)) if channel.config_encrypted else {}
            reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
            message = (
                f"Hola {user.full_name},\n\n"
                "Recibimos una solicitud para restablecer tu contraseña en CITI Platform "
                "(Coordinación de Informática - Corte Superior de Justicia de Lima).\n\n"
                f"Ingresa al siguiente enlace para elegir una nueva contraseña (válido por 1 hora):\n{reset_link}\n\n"
                "Si no solicitaste este cambio, ignora este correo."
            )
            html_body = render_password_reset(user.full_name, reset_link)
            await asyncio.to_thread(
                send_email, config, user.email, message, "CITI Platform - Restablecer contraseña", html_body
            )
            log_action(db, user, "auth.password_reset_requested", "user", user.id, request=request)

    return MessageResponse(message=GENERIC_FORGOT_PASSWORD_MESSAGE)


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)) -> MessageResponse:
    ip_key = f"reset_password:ip:{client_ip(request)}"
    enforce_not_blocked(ip_key, RESET_PASSWORD_MAX_PER_IP, RESET_PASSWORD_WINDOW_SECONDS, TOO_MANY_ATTEMPTS_MESSAGE)

    token_hash = hash_secure_token(payload.token)
    reset_token = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash))

    now = datetime.now(timezone.utc)
    if (
        reset_token is None
        or reset_token.used_at is not None
        or reset_token.expires_at < now
    ):
        rate_limiter.record_attempt(ip_key)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El enlace es inválido o ha expirado")

    if len(payload.new_password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La contraseña debe tener al menos 8 caracteres")

    user = db.get(User, reset_token.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El enlace es inválido o ha expirado")

    user.hashed_password = hash_password(payload.new_password)
    reset_token.used_at = now
    db.commit()
    log_action(db, user, "auth.password_reset_completed", "user", user.id, request=request)

    return MessageResponse(message="Contraseña actualizada correctamente. Ya puedes iniciar sesión.")
