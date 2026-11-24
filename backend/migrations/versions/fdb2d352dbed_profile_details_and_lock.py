"""profile logistics, date of birth and the post-registration lock

The account profile now asks the same questions as the pass purchase form
(gender, meal, hostel and date of birth), so one source feeds the ID card, the
kitchen and the hostel. The pass form gained a date of birth for desk
verification against a college ID.

Revision ID: fdb2d352dbed
Revises: fdb2d352dbec
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fdb2d352dbed"
down_revision: str | None = "fdb2d352dbec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "participant_profiles", sa.Column("gender", sa.SmallInteger(), nullable=True)
    )
    op.add_column(
        "participant_profiles",
        sa.Column("food_preference", sa.SmallInteger(), nullable=True),
    )
    op.add_column(
        "participant_profiles",
        sa.Column(
            "needs_accommodation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "participant_profiles", sa.Column("date_of_birth", sa.Date(), nullable=True)
    )
    op.add_column(
        "college_registrations", sa.Column("date_of_birth", sa.Date(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("college_registrations", "date_of_birth")
    op.drop_column("participant_profiles", "date_of_birth")
    op.drop_column("participant_profiles", "needs_accommodation")
    op.drop_column("participant_profiles", "food_preference")
    op.drop_column("participant_profiles", "gender")