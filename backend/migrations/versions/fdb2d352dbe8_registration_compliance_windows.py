"""registration compliance windows

Revision ID: fdb2d352dbe8
Revises: fdb2d352dbe7

The registration desk can ask an attendee to re-upload documents or to pay a
category-change difference. Those requests used to have no deadline, so a
participant could hold an event seat (and a team slot) indefinitely while the
desk waited. These columns record the 24-hour window that the lazy/cron sweep
enforces:

* ``compliance_kind`` - ``documents`` or ``category_payment``.
* ``compliance_flagged_at`` - when the desk raised the request.
* ``compliance_deadline_at`` - ``flagged_at`` + 24 hours.
* ``compliance_enforced_at`` - when the sweep released the seats and repaired
  the team. Kept after the attendee resolves the request so the history is
  visible, and used as the exactly-once guard for enforcement.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "fdb2d352dbe8"
down_revision = "fdb2d352dbe7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("college_registrations") as batch:
        batch.add_column(sa.Column("compliance_kind", sa.String(length=40), nullable=True))
        batch.add_column(
            sa.Column("compliance_flagged_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(
            sa.Column("compliance_deadline_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(
            sa.Column("compliance_enforced_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.create_index(
            "ix_college_registration_compliance_due",
            ["compliance_kind", "compliance_deadline_at"],
        )


def downgrade() -> None:
    with op.batch_alter_table("college_registrations") as batch:
        batch.drop_index("ix_college_registration_compliance_due")
        batch.drop_column("compliance_enforced_at")
        batch.drop_column("compliance_deadline_at")
        batch.drop_column("compliance_flagged_at")
        batch.drop_column("compliance_kind")
