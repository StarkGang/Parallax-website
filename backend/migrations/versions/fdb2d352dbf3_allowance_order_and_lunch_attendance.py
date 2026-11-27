"""Add allowance_pack_order to edition_policies and scope to attendance_records.

Revision ID: fdb2d352dbf3
Revises: fdb2d352dbf2
Create Date: 2026-11-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fdb2d352dbf3"
down_revision: str | None = "fdb2d352dbf2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "edition_policies" in tables:
        cols = {c["name"] for c in inspector.get_columns("edition_policies")}
        if "allowance_pack_order" not in cols:
            op.add_column(
                "edition_policies",
                sa.Column(
                    "allowance_pack_order",
                    sa.SmallInteger(),
                    nullable=False,
                    server_default=sa.text("0"),
                ),
            )

    if "attendance_records" in tables:
        cols = {c["name"] for c in inspector.get_columns("attendance_records")}
        if "scope" not in cols:
            op.add_column(
                "attendance_records",
                sa.Column(
                    "scope",
                    sa.String(length=24),
                    nullable=False,
                    server_default=sa.text("'pass'"),
                ),
            )
            op.execute(
                sa.text(
                    "UPDATE attendance_records SET scope = CASE WHEN event_id IS NOT NULL THEN 'event' ELSE 'pass' END"
                )
            )
        existing_indexes = {ix["name"] for ix in inspector.get_indexes("attendance_records")}
        if "uq_attendance_pass_day" in existing_indexes:
            op.drop_index("uq_attendance_pass_day", table_name="attendance_records")
        op.create_index(
            "uq_attendance_pass_day",
            "attendance_records",
            ["user_id", "edition_id", "day", "scope"],
            unique=True,
            postgresql_where=sa.text("event_id IS NULL"),
            sqlite_where=sa.text("event_id IS NULL"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "attendance_records" in tables:
        existing_indexes = {ix["name"] for ix in inspector.get_indexes("attendance_records")}
        if "uq_attendance_pass_day" in existing_indexes:
            op.drop_index("uq_attendance_pass_day", table_name="attendance_records")
        op.create_index(
            "uq_attendance_pass_day",
            "attendance_records",
            ["user_id", "edition_id", "day"],
            unique=True,
            postgresql_where=sa.text("event_id IS NULL"),
            sqlite_where=sa.text("event_id IS NULL"),
        )
        cols = {c["name"] for c in inspector.get_columns("attendance_records")}
        if "scope" in cols:
            op.drop_column("attendance_records", "scope")
    if "edition_policies" in tables:
        cols = {c["name"] for c in inspector.get_columns("edition_policies")}
        if "allowance_pack_order" in cols:
            op.drop_column("edition_policies", "allowance_pack_order")
