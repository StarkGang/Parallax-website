"""link studio cards to the attendee registration they were built from

The ID card studio can load a registered attendee. Saving that card used to
fail: the attendee's registration number is already taken by the registration
table, so the studio could never issue the card or show its QR. The link added
here lets a studio card belong to exactly one registration, which also makes
"load from registered attendees" reopen the saved card instead of creating a
second identity.

Revision ID: fdb2d352dbec
Revises: fdb2d352dbeb
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fdb2d352dbec"
down_revision: str | None = "fdb2d352dbeb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("custom_credentials") as batch:
        batch.add_column(sa.Column("registration_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_custom_credentials_registration_id_college_registrations",
            "college_registrations",
            ["registration_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(
            op.f("ix_custom_credentials_registration_id"), ["registration_id"], unique=False
        )
        batch.create_unique_constraint(
            "uq_custom_credential_edition_registration", ["edition_id", "registration_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("custom_credentials") as batch:
        batch.drop_constraint(
            "uq_custom_credential_edition_registration", type_="unique"
        )
        batch.drop_index(op.f("ix_custom_credentials_registration_id"))
        batch.drop_constraint(
            "fk_custom_credentials_registration_id_college_registrations",
            type_="foreignkey",
        )
        batch.drop_column("registration_id")
