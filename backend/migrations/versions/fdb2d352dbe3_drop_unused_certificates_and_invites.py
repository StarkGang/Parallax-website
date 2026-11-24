"""Drop the unused certificates and team_invites tables (FEAT-001).

Neither table has a model, endpoint or reader any more. IF EXISTS keeps this
safe on databases created from the baseline revision, where the tables never
existed.

Revision ID: fdb2d352dbe3
Revises: fdb2d352dbe2
"""

from typing import Sequence, Union

from alembic import op

revision: str = "fdb2d352dbe3"
down_revision: Union[str, None] = "fdb2d352dbe2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS certificates")
    op.execute("DROP TABLE IF EXISTS team_invites")


def downgrade() -> None:
    # The models are gone, so a faithful recreation is not possible here.
    pass
