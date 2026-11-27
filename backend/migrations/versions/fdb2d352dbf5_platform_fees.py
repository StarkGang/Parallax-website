"""Add platform_fee_bps and platform_fee_exempt_under_paise to edition_policies and platform_fee_paise to payment_orders.

Revision ID: fdb2d352dbf5
Revises: fdb2d352dbf4
Create Date: 2026-11-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fdb2d352dbf5"
down_revision: str | None = "fdb2d352dbf4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "edition_policies" in tables:
        cols = {c["name"] for c in inspector.get_columns("edition_policies")}
        if "platform_fee_bps" not in cols:
            op.add_column(
                "edition_policies",
                sa.Column("platform_fee_bps", sa.Integer(), nullable=False, server_default=sa.text("0")),
            )
        if "platform_fee_exempt_under_paise" not in cols:
            op.add_column(
                "edition_policies",
                sa.Column(
                    "platform_fee_exempt_under_paise",
                    sa.Integer(),
                    nullable=False,
                    server_default=sa.text("0"),
                ),
            )

    if "payment_orders" in tables:
        cols = {c["name"] for c in inspector.get_columns("payment_orders")}
        if "platform_fee_paise" not in cols:
            op.add_column(
                "payment_orders",
                sa.Column(
                    "platform_fee_paise", sa.Integer(), nullable=False, server_default=sa.text("0")
                ),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "payment_orders" in tables:
        cols = {c["name"] for c in inspector.get_columns("payment_orders")}
        if "platform_fee_paise" in cols:
            op.drop_column("payment_orders", "platform_fee_paise")
    if "edition_policies" in tables:
        cols = {c["name"] for c in inspector.get_columns("edition_policies")}
        if "platform_fee_exempt_under_paise" in cols:
            op.drop_column("edition_policies", "platform_fee_exempt_under_paise")
        if "platform_fee_bps" in cols:
            op.drop_column("edition_policies", "platform_fee_bps")

