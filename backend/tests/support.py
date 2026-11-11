"""Shared test setup for state the demo seed deliberately does not create.

The seed ships a catalogue and an edition policy but no participant profile,
because a real attendee completes that themselves. These helpers build exactly
the prerequisites a paid flow needs, through the same models the API uses, so
tests still assert the real route behaviour instead of a stubbed shortcut.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_clear
from app.models.edition import ConventionEdition, EligibilityVerification
from app.models.settings import SystemSetting
from app.models.user import ParticipantProfile, User
from app.services.system_settings import UNLOCK_KEY


async def _write_unlock(db: AsyncSession, when: datetime) -> None:
    row = await db.scalar(select(SystemSetting).where(SystemSetting.key == UNLOCK_KEY))
    if row is None:
        db.add(SystemSetting(key=UNLOCK_KEY, value=when.isoformat()))
    else:
        row.value = when.isoformat()
    await db.commit()
    cache_clear()


async def open_registration(db: AsyncSession) -> None:
    """Move the stored unlock instant into the past so paid flows can run."""
    await _write_unlock(db, datetime.now(UTC) - timedelta(minutes=1))


async def lock_registration(db: AsyncSession, when: datetime) -> None:
    """Pin the stored unlock instant, e.g. to assert price suppression."""
    await _write_unlock(db, when)


async def ensure_eligible_participant(
    db: AsyncSession,
    email: str,
    *,
    education_level: str = "B.Tech",
    iste_member: bool = False,
) -> User:
    """Give a logged-in demo account the profile and verification a buyer needs."""
    user = await db.scalar(select(User).where(User.email_normalized == email.lower()))
    assert user is not None, f"{email} must sign in before its profile can be prepared"

    profile = await db.scalar(
        select(ParticipantProfile).where(ParticipantProfile.user_id == user.id)
    )
    if profile is None:
        profile = ParticipantProfile(user_id=user.id)
        db.add(profile)
    profile.college_name = "NSS College of Engineering"
    profile.education_level = education_level
    profile.iste_member = iste_member
    profile.branch = "Computer Science"
    profile.year_of_study = 3
    profile.privacy_consent_at = datetime.now(UTC)
    profile.college_id_document_key = "test/college-id.png"

    edition = await db.scalar(
        select(ConventionEdition).where(ConventionEdition.status == "published")
    )
    assert edition is not None, "the seeded edition must be published"

    verification = await db.scalar(
        select(EligibilityVerification).where(
            EligibilityVerification.user_id == user.id,
            EligibilityVerification.edition_id == edition.id,
        )
    )
    if verification is None:
        verification = EligibilityVerification(
            user_id=user.id, edition_id=edition.id, method="document"
        )
        db.add(verification)
    verification.method = "document"
    verification.status = "verified"
    verification.reviewed_at = datetime.now(UTC)
    verification.rejection_reason = None

    await db.commit()
    cache_clear()
    return user


__all__ = ["ensure_eligible_participant", "lock_registration", "open_registration"]
