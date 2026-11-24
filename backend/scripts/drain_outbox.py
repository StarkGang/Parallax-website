"""Drain the transactional email outbox.

Usage (from backend/):

    python scripts/drain_outbox.py --dry-run   # list what is waiting, send nothing
    python scripts/drain_outbox.py             # send via the configured provider

The script refuses to send when no provider is configured, so it can never
silently mark rows sent. `--dry-run` never writes to the database.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import session_scope  # noqa: E402
from app.integrations import email as email_outbox  # noqa: E402
from app.models.commerce import EmailOutbox  # noqa: E402


async def list_pending(db) -> None:
    rows = list(
        (
            await db.execute(
                select(EmailOutbox)
                .where(
                    EmailOutbox.status.in_(email_outbox.ACTIVE_STATUSES),
                    EmailOutbox.attempts < email_outbox.MAX_ATTEMPTS,
                )
                .order_by(EmailOutbox.scheduled_at)
            )
        ).scalars()
    )
    print(f"{len(rows)} row(s) waiting (max {email_outbox.MAX_ATTEMPTS} attempts):")
    for row in rows:
        print(
            f"  {row.id}  {row.status:8} attempts={row.attempts}  "
            f"{row.recipient}  {row.template}"
        )


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list queued rows and exit without writing anything",
    )
    args = parser.parse_args()

    settings = get_settings()
    async with session_scope() as db:
        if args.dry_run:
            await list_pending(db)
            return 0
        if not settings.email_available:
            print(
                "Email is not configured (EMAIL_ENABLED, EMAIL_PROVIDER_API_KEY, "
                "EMAIL_FROM). Nothing was sent and no row was changed.",
                file=sys.stderr,
            )
            return 2
        sent = await email_outbox.send_batch(db)
        print(f"sent {sent} row(s)")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
