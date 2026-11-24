"""One event worklist, delta pricing and team-owned payments.

Adds the three things the unified worklist needs:

* ``event_quotes`` - a server-priced basket, consumed once by checkout, so the
  browser never computes money and a retry cannot charge twice.
* ``teams.order_id`` / ``paid_by_user_id`` - a per-team entry is paid by the
  team, not by the leader's seat, so leadership can move without orphaning it.

Also records how each seat was priced (``registrations.price_basis``) and when
a membership ended (``team_members.left_at``), which the elder-leads handover
and the finance reconciliation read.

Revision ID: fdb2d352dbf0
Revises: fdb2d352dbef
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fdb2d352dbf0"
down_revision: str | None = "fdb2d352dbef"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ----------------------------------------------------------------- teams
    op.add_column("teams", sa.Column("order_id", sa.Uuid(), nullable=True))
    op.add_column("teams", sa.Column("paid_by_user_id", sa.Uuid(), nullable=True))
    op.add_column(
        "teams",
        sa.Column(
            "formation_state", sa.String(length=20), nullable=False, server_default="forming"
        ),
    )
    op.add_column(
        "teams",
        sa.Column("min_size", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_teams_order_id", "teams", ["order_id"], unique=False)
    # SQLite cannot add a foreign key with ALTER TABLE. Tests create tables from
    # the models; this branch keeps a local SQLite migration run possible.
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_teams_order_id_payment_orders",
            "teams",
            "payment_orders",
            ["order_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_foreign_key(
            "fk_teams_paid_by_user_id_users",
            "teams",
            "users",
            ["paid_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.add_column("team_members", sa.Column("left_at", sa.DateTime(timezone=True), nullable=True))

    # --------------------------------------------------------- registrations
    op.add_column(
        "registrations", sa.Column("price_basis", sa.String(length=24), nullable=True)
    )
    op.add_column("registrations", sa.Column("quote_id", sa.Uuid(), nullable=True))
    op.create_index("ix_registrations_quote_id", "registrations", ["quote_id"], unique=False)

    # ------------------------------------------------------- event room guides
    op.add_column(
        "events",
        sa.Column("solo_guide_md", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "events",
        sa.Column("team_guide_md", sa.Text(), nullable=False, server_default=""),
    )

    # ----------------------------------------------------------- event quotes
    op.create_table(
        "event_quotes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("edition_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("lines", sa.JSON(), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("covered_paise", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("due_paise", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["edition_id"], ["convention_editions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["payment_orders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_event_quotes_edition_id", "event_quotes", ["edition_id"])
    op.create_index("ix_event_quotes_user_id", "event_quotes", ["user_id"])
    op.create_index("ix_event_quote_user_status", "event_quotes", ["user_id", "status"])
    op.create_index(
        "uq_event_quote_idempotency",
        "event_quotes",
        ["user_id", "idempotency_key"],
        unique=True,
    )

    # ---------------------------------------------------------------- backfill
    bind = op.get_bind()

    # A per-team entry paid under the old model is found through the leader's
    # seat. Move that pointer onto the team so a leader change cannot orphan it.
    bind.execute(
        sa.text(
            """
            UPDATE teams
               SET order_id = (
                    SELECT r.order_id
                      FROM registrations r
                      JOIN payment_orders o ON o.id = r.order_id
                     WHERE r.team_id = teams.id
                       AND r.user_id = teams.leader_id
                       AND o.status = 'paid'
                     LIMIT 1
               )
             WHERE order_id IS NULL
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE teams
               SET paid_by_user_id = leader_id
             WHERE order_id IS NOT NULL AND paid_by_user_id IS NULL
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE teams
               SET formation_state = CASE
                    WHEN status = 'locked' THEN 'locked'
                    WHEN status = 'disbanded' THEN 'disbanded'
                    ELSE 'forming'
               END
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE registrations
               SET price_basis = CASE
                    WHEN kind = 'included' THEN 'included'
                    WHEN kind = 'team' THEN 'team_per_participant'
                    WHEN COALESCE(fee_paise, 0) = 0 THEN 'free'
                    ELSE 'addon'
               END
             WHERE price_basis IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_index("uq_event_quote_idempotency", table_name="event_quotes")
    op.drop_index("ix_event_quote_user_status", table_name="event_quotes")
    op.drop_index("ix_event_quotes_user_id", table_name="event_quotes")
    op.drop_index("ix_event_quotes_edition_id", table_name="event_quotes")
    op.drop_table("event_quotes")

    op.drop_column("events", "team_guide_md")
    op.drop_column("events", "solo_guide_md")

    op.drop_index("ix_registrations_quote_id", table_name="registrations")
    op.drop_column("registrations", "quote_id")
    op.drop_column("registrations", "price_basis")

    op.drop_column("team_members", "left_at")

    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("fk_teams_paid_by_user_id_users", "teams", type_="foreignkey")
        op.drop_constraint("fk_teams_order_id_payment_orders", "teams", type_="foreignkey")
    op.drop_index("ix_teams_order_id", table_name="teams")
    op.drop_column("teams", "min_size")
    op.drop_column("teams", "formation_state")
    op.drop_column("teams", "paid_by_user_id")
    op.drop_column("teams", "order_id")
