"""Drop the unused coordinator assignments and dead policy switches (AUDIT02 A9/A13).

`event_coordinator_assignments` was written by nothing and read only by an
unused dependency (`require_event_access`) and a display-only name list, so the
permission_scope column never granted or denied anything.

The four policy columns were accepted by the policy editor, stored, echoed back
and then never consulted by any price, capacity or eligibility rule.

Revision ID: fdb2d352dbe5
Revises: fdb2d352dbe4
"""

from typing import Sequence, Union

from alembic import op

revision: str = "fdb2d352dbe5"
down_revision: Union[str, None] = "fdb2d352dbe4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEAD_POLICY_COLUMNS = (
    ("group_discount_threshold", "INTEGER"),
    ("group_discount_percent", "INTEGER"),
    ("allow_free_entry", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("allow_team_addon_split", "BOOLEAN NOT NULL DEFAULT FALSE"),
)


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS event_coordinator_assignments")
    for name, _ in DEAD_POLICY_COLUMNS:
        op.execute(f"ALTER TABLE edition_policies DROP COLUMN IF EXISTS {name}")


def downgrade() -> None:
    """Recreate the shape (rows are not restored - nothing wrote them)."""
    for name, ddl in DEAD_POLICY_COLUMNS:
        op.execute(f"ALTER TABLE edition_policies ADD COLUMN IF NOT EXISTS {name} {ddl}")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS event_coordinator_assignments (
            id UUID PRIMARY KEY,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            event_id UUID NOT NULL REFERENCES events (id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            permission_scope JSON NOT NULL DEFAULT '[]',
            assigned_by UUID REFERENCES users (id) ON DELETE SET NULL,
            CONSTRAINT uq_coordinator_assignment UNIQUE (event_id, user_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_event_coordinator_assignments_event_id "
        "ON event_coordinator_assignments (event_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_event_coordinator_assignments_user_id "
        "ON event_coordinator_assignments (user_id)"
    )
