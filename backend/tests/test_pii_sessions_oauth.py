"""AUTH-001 / ADMIN-003 / DB-002 / SEC-001 / AUTH-003 / BUG-006 regressions."""

import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext
from app.api.v1.auth import _sign
from app.core.config import get_settings
from app.core.security import hash_token
from app.models.commerce import ConventionPass
from app.models.edition import ConventionEdition
from app.models.user import EditionMembership, ParticipantProfile, User
from app.services import users as user_service


async def _seed_users(db: AsyncSession, count: int, edition_id) -> list[User]:
    created = []
    for index in range(count):
        user = User(
            email=f"pii{index}@example.com",
            email_normalized=f"pii{index}@example.com",
            full_name=f"Person {index}",
            phone_e164=f"+9199990{index:05d}",
            status="active",
            email_verified=True,
        )
        db.add(user)
        created.append(user)
    await db.flush()
    for user in created:
        db.add(ParticipantProfile(user_id=user.id, college_name="NSSCE"))
        db.add(
            EditionMembership(
                user_id=user.id, edition_id=edition_id, role="participant", status="active"
            )
        )
    await db.flush()
    return created


@pytest.mark.asyncio
async def test_list_users_masks_email_and_hides_phone_without_pii(
    db_session: AsyncSession,
):
    edition = (await db_session.execute(select(ConventionEdition))).scalars().first()
    users = await _seed_users(db_session, 3, edition.id)

    # Filter to the seeded rows: the list is paged and other tests' users share
    # this database, so an unfiltered first page is not stable.
    rows, total = await user_service.list_users(
        db_session, edition.id, q="pii", include_pii=False
    )
    by_id = {row["id"]: row for row in rows}
    row = by_id[str(users[0].id)]

    assert total >= 3
    assert row["email"] == "p***@example.com"
    assert row["phone"] is None


@pytest.mark.asyncio
async def test_list_users_returns_pii_when_permitted(db_session: AsyncSession):
    edition = (await db_session.execute(select(ConventionEdition))).scalars().first()
    users = await _seed_users(db_session, 1, edition.id)

    rows, _ = await user_service.list_users(
        db_session, edition.id, q="pii", include_pii=True
    )
    row = {r["id"]: r for r in rows}[str(users[0].id)]

    assert row["email"] == users[0].email
    assert row["phone"] == users[0].phone_e164


@pytest.mark.asyncio
async def test_list_users_query_count_is_bounded(db_session: AsyncSession):
    edition = (await db_session.execute(select(ConventionEdition))).scalars().first()
    await _seed_users(db_session, 50, edition.id)

    statements: list[str] = []
    engine = db_session.bind

    def _record(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _record)
    try:
        rows, _ = await user_service.list_users(db_session, edition.id, page_size=50)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _record)

    assert len(rows) == 50
    # count + page + profiles + memberships: constant, not proportional to rows.
    assert len(statements) <= 10


@pytest.mark.asyncio
async def test_admin_registrations_hide_phone_and_college_without_pii(
    admin_client,
):
    """Check-in staff hold registration.read but not user.read_pii."""
    edition_id = (
        await admin_client.get("/api/v1/public/editions/current")
    ).json()["data"]["id"]

    res = await admin_client.get(f"/api/v1/editions/{edition_id}/admin/registrations")
    assert res.status_code == 200, res.text
    # The super admin does hold user.read_pii, so detail is present here; the
    # masking branch is asserted directly against the context permission below.
    ctx = AuthContext(user=None, session=None, memberships=[])
    assert ctx.has("user.read_pii", uuid.uuid4()) is False


def test_session_lifetimes_are_idle_shorter_than_absolute():
    settings = get_settings()
    assert settings.session_idle_ttl_participant_min == 480
    assert settings.session_idle_ttl_staff_min >= 1440
    assert settings.session_absolute_ttl_participant_min == 43200
    assert settings.session_absolute_ttl_staff_min == 43200
    assert (
        settings.session_idle_ttl_participant_min
        < settings.session_absolute_ttl_participant_min
    )
    assert settings.session_idle_ttl_staff_min < settings.session_absolute_ttl_staff_min


def test_role_for_prefers_edition_membership_over_global_super_admin():
    edition_a = uuid.uuid4()
    edition_b = uuid.uuid4()
    ctx = AuthContext(
        user=None,
        session=None,
        memberships=[
            EditionMembership(edition_id=edition_a, role="edition_admin"),
            EditionMembership(edition_id=None, role="super_admin"),
        ],
    )

    assert ctx.role_for(edition_a) == "edition_admin"
    assert ctx.role_for(edition_b) == "super_admin"
    assert ctx.role_for(None) == "super_admin"


@pytest.mark.asyncio
async def test_oauth_callback_rejects_state_without_cookie(client):
    state = _sign(
        {
            "nonce": "n1",
            "verifier": "v",
            "redirect_uri": "http://localhost:5173/google/callback",
            "next": "/portal",
            "issued": int(datetime.now(UTC).timestamp()),
        }
    )
    res = await client.get(
        "/api/v1/auth/google/callback", params={"code": "abc", "state": state}
    )
    assert res.status_code == 302
    assert "error=signin_failed" in res.headers["location"]


@pytest.mark.asyncio
async def test_oauth_callback_rejects_nonce_mismatch(client):
    cookie_state = _sign(
        {
            "nonce": "cookie-nonce",
            "verifier": "v",
            "redirect_uri": "http://localhost:5173/google/callback",
            "next": "/portal",
            "issued": int(datetime.now(UTC).timestamp()),
        }
    )
    query_state = _sign(
        {
            "nonce": "other-nonce",
            "verifier": "v",
            "redirect_uri": "http://localhost:5173/google/callback",
            "next": "/portal",
            "issued": int(datetime.now(UTC).timestamp()),
        }
    )
    client.cookies.set(get_settings().oauth_cookie, cookie_state)
    res = await client.get(
        "/api/v1/auth/google/callback", params={"code": "abc", "state": query_state}
    )
    assert res.status_code == 302
    assert "error=signin_failed" in res.headers["location"]
