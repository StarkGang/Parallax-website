"""drop leader-pays fee-basis columns

The leader-pays (``per_team``) model is gone: every team member pays for their
own seat, priced by the event's add-on price through the same quote engine as
every other seat. Three columns were left behind that no code reads any more:

* ``edition_policies.team_fee_basis_default`` - the policy default for a basis
  that no longer exists (its model default was still the invalid
  ``'flat_per_team'``).
* ``events.addon_charge_basis`` - only ever echoed back to the admin console.
* ``events.team_fee_basis`` - written by the event form and printed, never
  priced from.

Safety: before dropping ``events.team_fee_basis`` every event still marked
``per_team`` is listed, so an operator can see which events used to be
leader-pays. Nothing needs rewriting: the price of a seat is
``events.addon_price_paise`` for everybody, and that column is untouched.

Revision ID: fdb2d352dbf8
Revises: fdb2d352dbf7
"""

import sqlalchemy as sa

from alembic import op

revision = "fdb2d352dbf8"
down_revision = "fdb2d352dbf7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    columns = {c["name"] for c in sa.inspect(bind).get_columns("events")}
    if "team_fee_basis" in columns:
        rows = bind.execute(
            sa.text(
                "SELECT slug, title, addon_price_paise FROM events "
                "WHERE team_fee_basis = 'per_team' ORDER BY slug"
            )
        ).fetchall()
        print(f"[team fee basis] events still marked per_team: {len(rows)}")
        for slug, title, price in rows:
            print(f"  - {slug}: {title!r} (add-on price {price})")

    for table, column in (
        ("events", "team_fee_basis"),
        ("events", "addon_charge_basis"),
        ("edition_policies", "team_fee_basis_default"),
    ):
        present = {c["name"] for c in sa.inspect(bind).get_columns(table)}
        if column in present:
            op.drop_column(table, column)
            print(f"[team fee basis] dropped {table}.{column}")


def downgrade() -> None:
    # The values are gone; restore the columns with the only basis the product
    # still has so an old binary can start against this schema.
    conditions = {
        "events": {"team_fee_basis": None, "addon_charge_basis": "per_participant"},
        "edition_policies": {"team_fee_basis_default": "per_participant"},
    }
    for table, columns in conditions.items():
        present = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
        for column, default in columns.items():
            if column in present:
                continue
            op.add_column(table, sa.Column(column, sa.String(length=20), nullable=True))
            if default is not None:
                op.execute(
                    sa.text(f"UPDATE {table} SET {column} = :value").bindparams(
                        value=default
                    )
                )
