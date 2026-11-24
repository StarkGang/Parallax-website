"""Drop the student eligibility verification tables (AUDIT-2 F31).

`eligibility_verifications`, `verification_email_codes` and `roster_entries`
backed the roster / college-email / document-review verification flow. That flow
lost its UI (participant side) and never gated a registration, payment, pass or
door scan, so the models, services and endpoints were removed. Dropping the
tables finishes the job instead of leaving empty shelves behind.

IF EXISTS keeps this safe on databases created from the baseline revision.

Revision ID: fdb2d352dbe4
Revises: fdb2d352dbe3
"""

from typing import Sequence, Union

from alembic import op

revision: str = "fdb2d352dbe4"
down_revision: Union[str, None] = "fdb2d352dbe3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS verification_email_codes")
    op.execute("DROP TABLE IF EXISTS eligibility_verifications")
    op.execute("DROP TABLE IF EXISTS roster_entries")


def downgrade() -> None:
    """Recreate the schema the baseline revision defined.

    Rows are not restored - the old flow cannot produce them any more - but the
    shape comes back so this migration can be reversed without a manual diff.
    """
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS roster_entries (
            id UUID PRIMARY KEY,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            edition_id UUID NOT NULL REFERENCES convention_editions (id) ON DELETE CASCADE,
            college VARCHAR(200),
            student_hash VARCHAR(128) NOT NULL,
            email_hash VARCHAR(128) NOT NULL,
            claimed_at TIMESTAMP WITH TIME ZONE,
            claimed_by UUID REFERENCES users (id) ON DELETE SET NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_roster_entries_edition_id ON roster_entries (edition_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_roster_entries_student_hash ON roster_entries (student_hash)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_roster_entries_email_hash ON roster_entries (email_hash)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS eligibility_verifications (
            id UUID PRIMARY KEY,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            edition_id UUID NOT NULL REFERENCES convention_editions (id) ON DELETE CASCADE,
            method VARCHAR(20) NOT NULL,
            status VARCHAR(20) NOT NULL,
            reviewer_id UUID REFERENCES users (id) ON DELETE SET NULL,
            document_key VARCHAR(300),
            document_name VARCHAR(200),
            notes TEXT,
            rejection_reason TEXT,
            submitted_at TIMESTAMP WITH TIME ZONE NOT NULL,
            reviewed_at TIMESTAMP WITH TIME ZONE,
            rejected_count INTEGER NOT NULL DEFAULT 0,
            CONSTRAINT uq_verification_user_edition UNIQUE (user_id, edition_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_eligibility_verifications_user_id "
        "ON eligibility_verifications (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_eligibility_verifications_edition_id "
        "ON eligibility_verifications (edition_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS verification_email_codes (
            id UUID PRIMARY KEY,
            verification_id UUID NOT NULL
                REFERENCES eligibility_verifications (id) ON DELETE CASCADE,
            code_hash VARCHAR(128) NOT NULL,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            consumed_at TIMESTAMP WITH TIME ZONE
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_verification_email_codes_verification_id "
        "ON verification_email_codes (verification_id)"
    )
