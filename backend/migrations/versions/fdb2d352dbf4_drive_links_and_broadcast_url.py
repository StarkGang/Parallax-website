"""Add allow_drive_links and broadcast_url to registration_settings and external_url to registration_documents.

Revision ID: fdb2d352dbf4
Revises: fdb2d352dbf3
Create Date: 2026-11-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fdb2d352dbf4"
down_revision: str | None = "fdb2d352dbf3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "registration_settings" in tables:
        cols = {c["name"] for c in inspector.get_columns("registration_settings")}
        if "allow_drive_links" not in cols:
            op.add_column(
                "registration_settings",
                sa.Column(
                    "allow_drive_links",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                ),
            )
        if "broadcast_url" not in cols:
            op.add_column(
                "registration_settings",
                sa.Column("broadcast_url", sa.String(length=500), nullable=True),
            )

    if "registration_documents" in tables:
        cols = {c["name"] for c in inspector.get_columns("registration_documents")}
        if "external_url" not in cols:
            op.add_column(
                "registration_documents",
                sa.Column("external_url", sa.String(length=500), nullable=True),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "registration_documents" in tables:
        cols = {c["name"] for c in inspector.get_columns("registration_documents")}
        if "external_url" in cols:
            op.drop_column("registration_documents", "external_url")
    if "registration_settings" in tables:
        cols = {c["name"] for c in inspector.get_columns("registration_settings")}
        if "broadcast_url" in cols:
            op.drop_column("registration_settings", "broadcast_url")
        if "allow_drive_links" in cols:
            op.drop_column("registration_settings", "allow_drive_links")

