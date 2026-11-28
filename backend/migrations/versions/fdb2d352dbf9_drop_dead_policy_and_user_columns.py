"""drop dead policy, pass-price, user and event columns

Every column dropped here had no reader and no writer in ``app/``:

* ``edition_policies.pass_price_paise`` - the old "pass price". What an attendee
  actually pays is ``registration_categories.fee_paise``; the policy column was
  only echoed to the public FAQ and the admin policy table.
* ``edition_policies.included_selection_mode`` - the exact/up-to switch of the
  removed included-selection editor. The allowance always packs "up to N
  included events" (``pricing.allowance_pack``).
* ``users.deletion_requested_at`` - only the archived
  ``users.request_deletion`` touched it; it was never wired to a route.
* ``convention_editions.contact_phone`` / ``banner_key`` / ``created_by``.
* ``team_members.left_at`` - departures delete the row.
* ``payment_transactions.method_summary`` - never populated.

Archive: the removed Python for ``request_deletion`` lives in
``deadcode/3.3/`` together with its restore script.

Revision ID: fdb2d352dbf9
Revises: fdb2d352dbf8
"""

import sqlalchemy as sa

from alembic import op

revision = "fdb2d352dbf9"
down_revision = "fdb2d352dbf8"
branch_labels = None
depends_on = None

DROPS: tuple[tuple[str, str], ...] = (
    ("edition_policies", "pass_price_paise"),
    ("edition_policies", "included_selection_mode"),
    ("users", "deletion_requested_at"),
    ("convention_editions", "contact_phone"),
    ("convention_editions", "banner_key"),
    ("convention_editions", "created_by"),
    ("team_members", "left_at"),
    ("payment_transactions", "method_summary"),
)

ADD_BACK: dict[tuple[str, str], sa.Column] = {
    ("edition_policies", "pass_price_paise"): sa.Column(
        "pass_price_paise", sa.Integer(), nullable=False, server_default="0"
    ),
    ("edition_policies", "included_selection_mode"): sa.Column(
        "included_selection_mode", sa.String(length=10), nullable=False, server_default="up_to"
    ),
    ("users", "deletion_requested_at"): sa.Column(
        "deletion_requested_at", sa.DateTime(timezone=True), nullable=True
    ),
    ("convention_editions", "contact_phone"): sa.Column(
        "contact_phone", sa.String(length=32), nullable=True
    ),
    ("convention_editions", "banner_key"): sa.Column(
        "banner_key", sa.String(length=255), nullable=True
    ),
    ("convention_editions", "created_by"): sa.Column(
        "created_by", sa.Uuid(), nullable=True
    ),
    ("team_members", "left_at"): sa.Column(
        "left_at", sa.DateTime(timezone=True), nullable=True
    ),
    ("payment_transactions", "method_summary"): sa.Column(
        "method_summary", sa.String(length=120), nullable=True
    ),
}


def upgrade() -> None:
    bind = op.get_bind()
    for table, column in DROPS:
        present = {c["name"] for c in sa.inspect(bind).get_columns(table)}
        if column in present:
            op.drop_column(table, column)
            print(f"[dead columns] dropped {table}.{column}")


def downgrade() -> None:
    bind = op.get_bind()
    for table, column in DROPS:
        present = {c["name"] for c in sa.inspect(bind).get_columns(table)}
        if column not in present:
            op.add_column(table, ADD_BACK[(table, column)])
            print(f"[dead columns] restored {table}.{column}")
