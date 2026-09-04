"""remove services manage from site technician role

Revision ID: 37de4263d3a7
Revises: f0697632de15
Create Date: 2026-09-04 15:45:01.516679

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '37de4263d3a7'
down_revision: Union[str, None] = 'f0697632de15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLE_NAME = "Técnico de Sede"
PERMISSION_CODE = "services.manage"


def upgrade() -> None:
    bind = op.get_bind()
    role_id = bind.execute(sa.text("SELECT id FROM roles WHERE name = :name"), {"name": ROLE_NAME}).scalar()
    permission_id = bind.execute(
        sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": PERMISSION_CODE}
    ).scalar()
    if role_id is not None and permission_id is not None:
        bind.execute(
            sa.text("DELETE FROM role_permissions WHERE role_id = :role_id AND permission_id = :permission_id"),
            {"role_id": role_id, "permission_id": permission_id},
        )


def downgrade() -> None:
    bind = op.get_bind()
    role_id = bind.execute(sa.text("SELECT id FROM roles WHERE name = :name"), {"name": ROLE_NAME}).scalar()
    permission_id = bind.execute(
        sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": PERMISSION_CODE}
    ).scalar()
    if role_id is not None and permission_id is not None:
        bind.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_id) VALUES (:role_id, :permission_id) "
                "ON CONFLICT DO NOTHING"
            ),
            {"role_id": role_id, "permission_id": permission_id},
        )
