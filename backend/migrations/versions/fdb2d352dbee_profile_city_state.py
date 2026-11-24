"""add city and state to participant_profiles

The account profile and pass purchase form share the same attendee fields,
including city and state, so both screens stay identical and pre-fill each other.

Revision ID: fdb2d352dbee
Revises: fdb2d352dbed
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fdb2d352dbee"
down_revision: str | None = "fdb2d352dbed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "participant_profiles", sa.Column("city", sa.String(120), nullable=True)
    )
    op.add_column(
        "participant_profiles", sa.Column("state", sa.String(120), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("participant_profiles", "state")
    op.drop_column("participant_profiles", "city")

