"""drop per_team team order columns

Removes the leader-pays (per_team) model: every member now pays for their own
seat, so ``teams.order_id`` / ``teams.paid_by_user_id`` are no longer used.

Safety (this migration refuses to drop when data would be orphaned):
  * If any team still has an ``order_id`` whose order is ``paid``, it aborts —
    a human must settle/reassign that money first.
  * If any seat on a team order does not carry its own ``registration.order_id``
    pointing at that order, it aborts (the payment link would be lost).
  * Events still marked ``team_fee_basis = 'per_team'`` are listed with their
    current team fee but NOT changed (price meaning must be decided by a human).

Revision ID: fdb2d352dbf7
Revises: fdb2d352dbf6
"""

import sqlalchemy as sa

from alembic import op

revision = "fdb2d352dbf7"
down_revision = "fdb2d352dbf6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    teams = bind.execute(
        sa.text("SELECT id, order_id FROM teams WHERE order_id IS NOT NULL")
    ).fetchall()
    print(f"[per_team removal] teams with order_id set: {len(teams)}")

    paid = 0
    unlinked = 0
    for team_id, order_id in teams:
        status = bind.execute(
            sa.text("SELECT status FROM payment_orders WHERE id = :oid"),
            {"oid": order_id},
        ).scalar()
        if status == "paid":
            paid += 1
            print(f"  PAID team order {order_id} (team {team_id}) — needs manual handling")
        bad = bind.execute(
            sa.text(
                "SELECT count(*) FROM registrations "
                "WHERE team_id = :tid AND (order_id IS NULL OR order_id <> :oid)"
            ),
            {"tid": team_id, "oid": order_id},
        ).scalar()
        if bad:
            unlinked += bad
            print(f"  team {team_id}: {bad} seat(s) not linked to order {order_id}")

    if paid:
        raise RuntimeError(
            f"{paid} paid per_team order(s) found; refusing to drop teams.order_id. "
            "Settle or reassign them first, then re-run."
        )
    if unlinked:
        raise RuntimeError(
            f"{unlinked} seat(s) on a team order are not linked to it; refusing to "
            "drop teams.order_id to avoid orphaning the payment."
        )

    events = bind.execute(
        sa.text(
            "SELECT id, title, addon_price_paise FROM events "
            "WHERE team_fee_basis = 'per_team'"
        )
    ).fetchall()
    if events:
        print("[per_team removal] events still marked per_team (NOT changed):")
        for eid, title, fee in events:
            print(f"  {eid} {title!r} team fee paise={fee}")

    op.drop_constraint("fk_teams_order_id_payment_orders", "teams", type_="foreignkey")
    op.drop_index("ix_teams_order_id", table_name="teams")
    op.drop_column("teams", "order_id")
    op.drop_column("teams", "paid_by_user_id")


def downgrade() -> None:
    op.add_column("teams", sa.Column("paid_by_user_id", sa.Uuid(), nullable=True))
    op.add_column("teams", sa.Column("order_id", sa.Uuid(), nullable=True))
    op.create_index("ix_teams_order_id", "teams", ["order_id"], unique=False)
    op.create_foreign_key(
        "fk_teams_order_id_payment_orders",
        "teams",
        "payment_orders",
        ["order_id"],
        ["id"],
        ondelete="SET NULL",
    )