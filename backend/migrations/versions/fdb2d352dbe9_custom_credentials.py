"""custom credentials for studio-issued ID cards

Revision ID: fdb2d352dbe9
Revises: fdb2d352dbe8
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fdb2d352dbe9"
down_revision: str | None = "fdb2d352dbe8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "custom_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("edition_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=120), nullable=False),
        sa.Column("college", sa.String(length=200), nullable=True),
        sa.Column("tier", sa.String(length=120), nullable=True),
        sa.Column("design", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("issued_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["edition_id"], ["convention_editions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["issued_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("edition_id", "code", name="uq_custom_credential_edition_code"),
    )
    op.create_index(
        op.f("ix_custom_credentials_edition_id"),
        "custom_credentials",
        ["edition_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_custom_credentials_edition_id"), table_name="custom_credentials")
    op.drop_table("custom_credentials")
