"""Records who-did-what for the append-only audit trail (app.models.identity.AuditLog).

Call sites commit their own transaction for the primary action first; log_action()
issues its own separate commit for the audit row, so a logging hiccup never masks
whether the primary action itself succeeded.
"""

import datetime
import enum
import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.identity import AuditLog, User

SENSITIVE_VALUE_MASK = "(cambio no expuesto en auditoría)"


def _serialize_audit_value(value: Any) -> Any:
    """Normaliza un valor de modelo a algo JSON-serializable y legible en la
    auditoría: Enum -> .value, UUID/datetime -> str, listas recursivamente."""
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (uuid.UUID, datetime.datetime, datetime.date)):
        return str(value)
    if isinstance(value, list):
        return [_serialize_audit_value(v) for v in value]
    return value


def diff_changed_fields(
    entity: Any,
    data: dict[str, Any],
    *,
    sensitive_fields: frozenset[str] = frozenset(),
) -> dict[str, dict[str, Any]]:
    """Para una acción `*.updated`: compara el valor actual de `entity` (antes de
    aplicarle `data`) contra cada valor entrante y devuelve solo los campos que
    realmente cambiaron, como {campo: {"antes": x, "despues": y}} — para que la
    auditoría registre qué cambió de verdad, no solo el nombre del campo.

    Los campos en `sensitive_fields` (contraseñas, secretos) nunca exponen su
    valor real: se registra que cambiaron, no a qué.
    """
    changes: dict[str, dict[str, Any]] = {}
    for field, new_value in data.items():
        old_value = getattr(entity, field, None)
        if old_value == new_value:
            continue
        if field in sensitive_fields:
            changes[field] = {"antes": SENSITIVE_VALUE_MASK, "despues": SENSITIVE_VALUE_MASK}
        else:
            changes[field] = {
                "antes": _serialize_audit_value(old_value),
                "despues": _serialize_audit_value(new_value),
            }
    return changes


def log_action(
    db: Session,
    user: User | None,
    action: str,
    entity_type: str,
    entity_id: str | uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=details,
            ip_address=request.client.host if request is not None and request.client else None,
        )
    )
    db.commit()
