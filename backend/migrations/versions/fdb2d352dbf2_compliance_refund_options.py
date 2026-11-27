"""Add compliance refund preference columns to college_registrations.

Revision ID: fdb2d352dbf2
Revises: fdb2d352dbf1
Create Date: 2026-11-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fdb2d352dbf2"
down_revision: str | None = "fdb2d352dbf1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "college_registrations" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("college_registrations")}
    if "compliance_refund_pass" not in columns:
        op.add_column(
            "college_registrations",
            sa.Column(
                "compliance_refund_pass",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )
    if "compliance_refund_events" not in columns:
        op.add_column(
            "college_registrations",
            sa.Column(
                "compliance_refund_events",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "college_registrations" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("college_registrations")}
    if "compliance_refund_events" in columns:
        op.drop_column("college_registrations", "compliance_refund_events")
    if "compliance_refund_pass" in columns:
        op.drop_column("college_registrations", "compliance_refund_pass")

