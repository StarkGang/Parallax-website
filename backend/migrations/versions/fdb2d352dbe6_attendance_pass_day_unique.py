"""Dedupe pass-level door scans (AUDIT03 B8).

`uq_attendance` is `(user_id, event_id, day)`. A pass-level scan stores
`event_id = NULL`, and SQL treats NULLs as distinct, so the database could not
reject a second scan of the same pass: two scanners at the same second both
wrote an attendance row and the person was counted twice.

This adds the missing partial unique index for the event-less case. Existing
duplicates are collapsed first (the oldest row for the day wins, matching what
the scanner reports as "already checked in").

Revision ID: fdb2d352dbe6
Revises: fdb2d352dbe5
"""

from typing import Sequence, Union

from alembic import op

revision: str = "fdb2d352dbe6"
down_revision: Union[str, None] = "fdb2d352dbe5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "uq_attendance_pass_day"


def upgrade() -> None:
    # Collapse pre-existing duplicates so the index can be created.
    op.execute(
        """
        DELETE FROM attendance_records a
        USING attendance_records b
        WHERE a.event_id IS NULL
          AND b.event_id IS NULL
          AND a.user_id = b.user_id
          AND a.edition_id = b.edition_id
          AND a.day = b.day
          AND (a.checked_in_at > b.checked_in_at
               OR (a.checked_in_at = b.checked_in_at AND a.id > b.id))
        """
    )
    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME}
        ON attendance_records (user_id, edition_id, day)
        WHERE event_id IS NULL
        """
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
