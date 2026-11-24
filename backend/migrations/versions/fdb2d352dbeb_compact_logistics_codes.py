"""store gender and meal as one small integer

Names were stored as text ("female", "non_veg"). One integer is enough: 0 = male
or veg, 1 = female or non-veg. The API keeps speaking names, so nothing outside
the database has to change.

Revision ID: fdb2d352dbeb
Revises: fdb2d352dbea
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fdb2d352dbeb"
down_revision: str | None = "fdb2d352dbea"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GENDER_USING = "CASE gender WHEN 'male' THEN 0 WHEN 'female' THEN 1 ELSE NULL END"
FOOD_USING = (
    "CASE food_preference "
    "WHEN 'veg' THEN 0 WHEN 'vegetarian' THEN 0 "
    "WHEN 'non_veg' THEN 1 WHEN 'non-veg' THEN 1 ELSE NULL END"
)


def upgrade() -> None:
    for table in ("college_registrations", "custom_credentials"):
        op.alter_column(
            table,
            "gender",
            type_=sa.SmallInteger(),
            postgresql_using=GENDER_USING,
        )
        op.alter_column(
            table,
            "food_preference",
            type_=sa.SmallInteger(),
            postgresql_using=FOOD_USING,
        )


def downgrade() -> None:
    for table in ("college_registrations", "custom_credentials"):
        op.alter_column(
            table,
            "gender",
            type_=sa.String(length=20),
            postgresql_using="CASE gender WHEN 0 THEN 'male' WHEN 1 THEN 'female' ELSE NULL END",
        )
        op.alter_column(
            table,
            "food_preference",
            type_=sa.String(length=20),
            postgresql_using="CASE food_preference WHEN 0 THEN 'veg' WHEN 1 THEN 'non_veg' ELSE NULL END",
        )
