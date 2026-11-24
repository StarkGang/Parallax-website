"""gender, meal and accommodation on registrations and studio cards

The pass purchase form asks for gender, veg/non-veg and whether the attendee
needs accommodation. These are operational data, not decoration: the door, the
kitchen and the hostel count from them, and the desk sees them when a QR is
scanned. Studio-issued cards need the same three fields plus a branch line so a
reprinted card keeps its department.

Revision ID: fdb2d352dbea
Revises: fdb2d352dbe9
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fdb2d352dbea"
down_revision: str | None = "fdb2d352dbe9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "college_registrations", sa.Column("gender", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "college_registrations",
        sa.Column("food_preference", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "college_registrations",
        sa.Column(
            "needs_accommodation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.add_column(
        "custom_credentials", sa.Column("branch", sa.String(length=160), nullable=True)
    )
    op.add_column(
        "custom_credentials", sa.Column("gender", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "custom_credentials",
        sa.Column("food_preference", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "custom_credentials",
        sa.Column(
            "needs_accommodation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("custom_credentials", "needs_accommodation")
    op.drop_column("custom_credentials", "food_preference")
    op.drop_column("custom_credentials", "gender")
    op.drop_column("custom_credentials", "branch")

    op.drop_column("college_registrations", "needs_accommodation")
    op.drop_column("college_registrations", "food_preference")
    op.drop_column("college_registrations", "gender")
