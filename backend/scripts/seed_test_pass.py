"""Seed one complimentary active pass for a local test attendee.

Usage (development only):
    .venv/Scripts/python.exe scripts/seed_test_pass.py <email>
"""

import asyncio
import sys

from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.commerce import ConventionPass, Ticket
from app.models.edition import ConventionEdition
from app.models.user import User
from app.services.editions import current_policy
from app.services.passes import activate_pass_for_registration


async def main(email: str) -> None:
    async with get_session_factory()() as db:
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None:
            raise SystemExit(f"No user with email {email!r}")

        edition = (
            await db.execute(
                select(ConventionEdition)
                .where(ConventionEdition.slug == "parallax-2027")
                .limit(1)
            )
        ).scalar_one_or_none()
        if edition is None:
            raise SystemExit("parallax-2027 edition not found")

        policy = await current_policy(db, edition.id)

        # price 0 = organiser comp: no fake payment is recorded against the user.
        pass_row = await activate_pass_for_registration(
            db, user.id, edition.id, policy, price_paise=0
        )
        await db.commit()

        tickets = (
            await db.execute(
                select(Ticket).where(
                    Ticket.pass_id == pass_row.id,
                    Ticket.status.in_(["active", "valid"]),
                )
            )
        ).scalars().all()

        print(
            f"pass={pass_row.id} status={pass_row.status} price={pass_row.price_paise} "
            f"policy=v{pass_row.policy_version} tickets={len(tickets)}"
        )
        print(f"user={user.email} edition={edition.slug}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: seed_test_pass.py <email>")
    asyncio.run(main(sys.argv[1]))
