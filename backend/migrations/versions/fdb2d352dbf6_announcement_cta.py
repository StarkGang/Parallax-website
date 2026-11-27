"""Add optional CTA button label and URL to announcements.

Revision ID: fdb2d352dbf6
Revises: fdb2d352dbf5
Create Date: 2026-11-28 10:16:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "fdb2d352dbf6"
down_revision = "fdb2d352dbf5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("announcements", sa.Column("cta_label", sa.String(length=80), nullable=True))
    op.add_column("announcements", sa.Column("cta_url", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("announcements", "cta_url")
    op.drop_column("announcements", "cta_label")

