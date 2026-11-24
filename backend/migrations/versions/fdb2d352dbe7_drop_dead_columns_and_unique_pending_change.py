"""drop dead columns, retire the eligibility-verifier role, one pending change

Revision ID: fdb2d352dbe7
Revises: fdb2d352dbe6

Three housekeeping items from the phase-8 audit:

* ``convention_editions.published_at`` / ``archived_at`` /
  ``allowed_email_domains`` and ``payment_orders.expires_at`` shipped with the
  first schema and were never written by any flow. ``convention_passes.order_id``
  was replaced by ``college_registrations.order_id`` when passes moved to the
  registration desk.
* ``edition_memberships.role = 'eligibility_verifier'`` belonged to the
  verification workflow that migration ``fdb2d352dbe4`` deleted. Those grants
  become ``event_coordinator`` so the staff member keeps read access.
* ``registration_category_changes`` could hold two ``pending`` rows for one
  registration (two concurrent requests), so a partial unique index now makes
  the select-then-insert race impossible.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "fdb2d352dbe7"
down_revision = "fdb2d352dbe6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("convention_editions") as batch:
        batch.drop_column("published_at")
        batch.drop_column("archived_at")
        batch.drop_column("allowed_email_domains")

    with op.batch_alter_table("payment_orders") as batch:
        batch.drop_column("expires_at")

    with op.batch_alter_table("convention_passes") as batch:
        batch.drop_column("order_id")

    op.execute(
        "UPDATE edition_memberships SET role = 'event_coordinator' "
        "WHERE role = 'eligibility_verifier'"
    )

    # A registration can only have one change waiting for a decision.
    op.execute(
        "UPDATE registration_category_changes SET status = 'cancelled' "
        "WHERE status = 'pending' AND id NOT IN ("
        "  SELECT DISTINCT ON (registration_id) id FROM registration_category_changes "
        "  WHERE status = 'pending' ORDER BY registration_id, created_at DESC"
        ")"
    )
    op.create_index(
        "uq_category_change_pending",
        "registration_category_changes",
        ["registration_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_category_change_pending", table_name="registration_category_changes")
    op.execute(
        "UPDATE edition_memberships SET role = 'eligibility_verifier' "
        "WHERE role = 'event_coordinator' AND id IN (SELECT id FROM edition_memberships WHERE false)"
    )
    with op.batch_alter_table("convention_passes") as batch:
        batch.add_column(sa.Column("order_id", sa.Uuid(), nullable=True))
    with op.batch_alter_table("payment_orders") as batch:
        batch.add_column(sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("convention_editions") as batch:
        batch.add_column(sa.Column("allowed_email_domains", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
