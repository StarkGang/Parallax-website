"""One staff role per account per edition.

``POST /admin/memberships`` used to add a row per role, so the same person could
hold ``finance_admin`` *and* ``event_coordinator`` at once. Permissions were
unioned across those rows: the account could do both jobs, the console listed
the same teammate twice, and nobody could tell what anyone was actually allowed
to do. New grants now replace the previous staff role; this migration removes the
rows that already stacked, keeping only the highest-privilege role per account.
Rows left in a ``revoked`` state by the first version of this change are removed
too, so the table holds exactly one staff role per account per edition.

``super_admin`` rows are never revoked: revoking one is how an edition loses its
last administrator.

Revision ID: fdb2d352dbef
Revises: fdb2d352dbee
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fdb2d352dbef"
down_revision: str | None = "fdb2d352dbee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Highest privilege first. Deliberately duplicated here: a migration has to keep
# working when the application's own role list changes later.
PRECEDENCE = ("edition_admin", "finance_admin", "event_coordinator", "checkin_staff")


def _rank(role: str) -> int:
    return PRECEDENCE.index(role) if role in PRECEDENCE else len(PRECEDENCE)


def upgrade() -> None:
    bind = op.get_bind()
    memberships = sa.Table(
        "edition_memberships",
        sa.MetaData(),
        autoload_with=bind,
    )

    rows = bind.execute(
        sa.select(
            memberships.c.id,
            memberships.c.user_id,
            memberships.c.edition_id,
            memberships.c.role,
        ).where(
            memberships.c.status == "active",
            memberships.c.role != "super_admin",
        )
    ).fetchall()

    groups: dict[tuple[object, object], list[sa.Row]] = {}
    for row in rows:
        groups.setdefault((row.user_id, row.edition_id), []).append(row)

    retire = []
    for group in groups.values():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=lambda row: (_rank(row.role), str(row.id)))
        retire.extend(row.id for row in ordered[1:])

    if retire:
        bind.execute(memberships.delete().where(memberships.c.id.in_(retire)))

    # Stale rows from the intermediate version that flipped duplicates to
    # "revoked" instead of deleting them.
    bind.execute(
        memberships.delete().where(
            memberships.c.status == "revoked",
            memberships.c.role != "super_admin",
        )
    )


def downgrade() -> None:
    # Deliberately irreversible: the previous state was duplicate roles for one
    # person, and restoring it would hand those permissions back.
    pass
