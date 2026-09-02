"""add site technician role

Revision ID: cb1738c53170
Revises: 24c383c027bc
Create Date: 2026-07-31 12:45:43.115828

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'cb1738c53170'
down_revision: Union[str, None] = '24c383c027bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLE_NAME = "Técnico de Sede"
ROLE_DESCRIPTION = "Administra únicamente los servidores y servicios de sus sedes asignadas — sin acceso a Sistemas, notificaciones, backups ni despliegues"
PERMISSION_CODES = ["servers.manage", "services.manage"]


def upgrade() -> None:
    bind = op.get_bind()

    role_id = uuid.uuid4()
    bind.execute(
        sa.text("INSERT INTO roles (id, name, description, is_system_role) VALUES (:id, :name, :description, false)"),
        {"id": role_id, "name": ROLE_NAME, "description": ROLE_DESCRIPTION},
    )

    for code in PERMISSION_CODES:
        permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": code}).scalar()
        if permission_id is not None:
            bind.execute(
                sa.text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:role_id, :permission_id)"),
                {"role_id": role_id, "permission_id": permission_id},
            )


def downgrade() -> None:
    bind = op.get_bind()
    role_id = bind.execute(sa.text("SELECT id FROM roles WHERE name = :name"), {"name": ROLE_NAME}).scalar()
    if role_id is not None:
        bind.execute(sa.text("DELETE FROM user_role_assignments WHERE role_id = :id"), {"id": role_id})
        bind.execute(sa.text("DELETE FROM role_permissions WHERE role_id = :id"), {"id": role_id})
        bind.execute(sa.text("DELETE FROM roles WHERE id = :id"), {"id": role_id})
