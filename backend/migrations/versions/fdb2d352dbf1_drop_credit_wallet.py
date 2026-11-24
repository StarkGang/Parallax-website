"""Drop the unused credit wallet.

The wallet was removed from the product: every cancellation and every negative
price difference is now refunded directly. This revision is deliberately
idempotent so it is safe both for a fresh database (where the wallet never
existed) and for a development database that already ran the earlier version of
the previous revision.

Revision ID: fdb2d352dbf1
Revises: fdb2d352dbf0
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fdb2d352dbf1"
down_revision: str | None = "fdb2d352dbf0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "payment_credits" in tables:
        for index in ("ix_payment_credit_user_status", "ix_payment_credits_user_id", "ix_payment_credits_edition_id"):
            if any(ix["name"] == index for ix in inspector.get_indexes("payment_credits")):
                op.drop_index(index, table_name="payment_credits")
        op.drop_table("payment_credits")

    if "event_quotes" in tables:
        columns = {column["name"] for column in inspector.get_columns("event_quotes")}
        if "credits" in columns:
            op.drop_column("event_quotes", "credits")
        if "credits_applied_paise" in columns:
            op.drop_column("event_quotes", "credits_applied_paise")


def downgrade() -> None:
    # The wallet is not coming back. A downgrade would have to invent balances
    # that no longer reconcile, so it is intentionally a no-op.
    pass
