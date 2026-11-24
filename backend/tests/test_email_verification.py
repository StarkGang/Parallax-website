"""EMAIL-002: institutional-email verification is gated on a real provider."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import encrypt_pii
from app.models.user import ParticipantProfile, User
from app.services import editions as edition_service
from app.services import verification as verif_service


@pytest.mark.asyncio
async def test_public_config_reports_email_unavailable(client: AsyncClient):
    res = await client.get("/api/v1/public/config")
    assert res.status_code == 200
    assert res.json()["emailAvailable"] is False


@pytest.mark.asyncio
async def test_college_email_verification_is_refused_without_provider(
    participant_client: AsyncClient, db_session: AsyncSession
):
    edition = (
        await participant_client.get("/api/v1/public/editions/current")
    ).json()["data"]

    user = (
        await db_session.execute(
            select(User).where(User.email == "participant@parallax.local")
        )
    ).scalar_one()
    profile = (
        await db_session.execute(
            select(ParticipantProfile).where(ParticipantProfile.user_id == user.id)
        )
    ).scalar_one_or_none()
    if profile is None:
        profile = ParticipantProfile(user_id=user.id, college_name="NSSCE", course="B.Tech")
        db_session.add(profile)
    profile.college_name = profile.college_name or "NSSCE"
    profile.course = profile.course or "B.Tech"
    profile.year_of_study = profile.year_of_study or 2
    profile.student_identifier_enc = encrypt_pii("ISTE-TEST-1")
    await db_session.flush()

    edition_row = await edition_service.edition_by_slug(db_session, edition["slug"])

    with pytest.raises(AppError) as exc:
        await verif_service.submit(
            db_session,
            None,
            user,
            edition_row,
            method="college_email",
            institution_email="student@nssce.ac.in",
        )

    assert exc.value.code == "EMAIL_UNAVAILABLE"
    assert "not available" in str(exc.value.message).lower()
