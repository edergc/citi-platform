"""add audit view permission

Revision ID: e9f8cb0bc82e
Revises: 17164779b525
Create Date: 2026-07-30 15:06:33.520609

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = 'e9f8cb0bc82e'
down_revision: Union[str, None] = '17164779b525'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PERMISSION_CODE = "audit.view"
PERMISSION_DESCRIPTION = "Ver el registro de auditoría (quién hizo qué)"


def upgrade() -> None:
    bind = op.get_bind()

    permission_id = uuid.uuid4()
    bind.execute(
        sa.text("INSERT INTO permissions (id, code, description) VALUES (:id, :code, :description)"),
        {"id": permission_id, "code": PERMISSION_CODE, "description": PERMISSION_DESCRIPTION},
    )

    admin_role_id = bind.execute(
        sa.text("SELECT id FROM roles WHERE name = 'Administrador' AND is_system_role = true LIMIT 1")
    ).scalar()
    if admin_role_id is not None:
        bind.execute(
            sa.text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:role_id, :permission_id)"),
            {"role_id": admin_role_id, "permission_id": permission_id},
        )


def downgrade() -> None:
    bind = op.get_bind()
    permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": PERMISSION_CODE}).scalar()
    if permission_id is not None:
        bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :id"), {"id": permission_id})
        bind.execute(sa.text("DELETE FROM permissions WHERE id = :id"), {"id": permission_id})
