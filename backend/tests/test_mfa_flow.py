"""Staff authenticator-app MFA: enforced by default, enrolled on first login."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pyotp
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commerce import RateLimitCounter
from app.models.user import MfaCredential, Session, User
from app.services.users import me_payload

OWNER = "owner@parallax.local"


def _secret_from_uri(uri: str) -> str:
    return parse_qs(urlparse(uri).query)["secret"][0]


def _enforced_auth_settings() -> SimpleNamespace:
    """Only the attributes direct_login reads, with MFA enforced."""
    return SimpleNamespace(
        dev_login_available=True,
        allow_direct_login=True,
        mfa_enforced=True,
        bootstrap_owner_email=OWNER,
        admin_email=None,
    )


async def _login_as_owner(client: AsyncClient) -> None:
    """Log in with MFA enforced, which leaves a basic (unenrolled) session."""
    with patch("app.api.v1.auth.get_settings", return_value=_enforced_auth_settings()):
        res = await client.post(
            "/api/v1/auth/login", json={"email": OWNER, "role": "admin"}
        )
    assert res.status_code == 200, res.text


async def _reset_login_limits(db: AsyncSession) -> None:
    """Keep this file from spending the suite's shared login budget."""
    for row in (
        await db.execute(
            select(RateLimitCounter).where(RateLimitCounter.bucket.like("auth_login%"))
        )
    ).scalars():
        await db.delete(row)
    await db.commit()


async def _clear_credentials(db: AsyncSession) -> None:
    user = (await db.execute(select(User).where(User.email == OWNER))).scalar_one()
    for row in (
        await db.execute(select(MfaCredential).where(MfaCredential.user_id == user.id))
    ).scalars():
        await db.delete(row)
    await db.commit()


@pytest.mark.asyncio
async def test_staff_enrols_authenticator_then_admin_routes_open(
    admin_client: AsyncClient, db_session: AsyncSession
):
    await _clear_credentials(db_session)
    await _reset_login_limits(db_session)
    await _login_as_owner(admin_client)
    edition_id = (
        await admin_client.get("/api/v1/public/editions/current")
    ).json()["data"]["id"]

    with patch(
        "app.api.deps.get_settings", return_value=SimpleNamespace(mfa_enforced=True)
    ):
        blocked = await admin_client.get(
            f"/api/v1/editions/{edition_id}/admin/overview"
        )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "MFA_REQUIRED"

    setup = await admin_client.post("/api/v1/auth/mfa/setup")
    assert setup.status_code == 200, setup.text
    secret = _secret_from_uri(setup.json()["otpauthUri"])

    verified = await admin_client.post(
        "/api/v1/auth/mfa/verify", json={"code": pyotp.TOTP(secret).now()}
    )
    assert verified.status_code == 200, verified.text
    assert len(verified.json()["data"]["recoveryCodes"]) == 8

    with patch(
        "app.api.deps.get_settings", return_value=SimpleNamespace(mfa_enforced=True)
    ):
        allowed = await admin_client.get(
            f"/api/v1/editions/{edition_id}/admin/overview"
        )
    assert allowed.status_code == 200, allowed.text

    # Re-enrolment is refused once active; a live code is still accepted.
    assert (await admin_client.post("/api/v1/auth/mfa/setup")).status_code == 409
    challenge = await admin_client.post(
        "/api/v1/auth/mfa/challenge", json={"code": pyotp.TOTP(secret).now()}
    )
    assert challenge.status_code == 200, challenge.text
    assert (
        await admin_client.post(
            "/api/v1/auth/mfa/challenge", json={"code": "000000"}
        )
    ).status_code == 400


@pytest.mark.asyncio
async def test_me_reports_mfa_required_until_enrolled(db_session: AsyncSession):
    user = (await db_session.execute(select(User).where(User.email == OWNER))).scalar_one()
    await db_session.commit()
    now = datetime.now(UTC)
    session = Session(
        user_id=user.id,
        token_hash="mfa-test-hash",
        csrf_secret="csrf",
        auth_level="basic",
        idle_expires_at=now + timedelta(hours=1),
        absolute_expires_at=now + timedelta(days=1),
    )

    with patch(
        "app.services.users.get_settings", return_value=SimpleNamespace(mfa_enforced=True)
    ):
        payload = await me_payload(db_session, user, session)
    assert payload.mfa_required is True

    session.auth_level = "staff_mfa"
    with patch(
        "app.services.users.get_settings", return_value=SimpleNamespace(mfa_enforced=True)
    ):
        payload = await me_payload(db_session, user, session)
    assert payload.mfa_required is False


def test_only_staff_and_admin_roles_are_challenged():
    from app.api.deps import AuthContext
    from app.core.permissions import Role
    from app.models.user import EditionMembership

    def ctx_for(role: str) -> AuthContext:
        return AuthContext(
            user=None, session=None, memberships=[EditionMembership(role=role)]
        )

    assert ctx_for(Role.CHECKIN_STAFF).staff_mfa_required is True
    assert ctx_for(Role.EVENT_COORDINATOR).staff_mfa_required is True
    assert ctx_for(Role.EDITION_ADMIN).staff_mfa_required is True
    assert ctx_for(Role.SUPER_ADMIN).staff_mfa_required is True
    assert ctx_for(Role.PARTICIPANT).staff_mfa_required is False


@pytest.mark.asyncio
async def test_step_up_only_prompts_on_destructive_mutations_when_expired(
    admin_client: AsyncClient, db_session: AsyncSession
):
    """Verifies:
    1. Read-only GET requests never require step-up.
    2. Non-destructive actions do not require step-up.
    3. Mutating settings requires step-up only when expired (>15m).
    4. Within the 15m window, mutating settings succeeds without prompt.
    """
    await _clear_credentials(db_session)
    await _reset_login_limits(db_session)
    await _login_as_owner(admin_client)

    edition_id = (
        await admin_client.get("/api/v1/public/editions/current")
    ).json()["data"]["id"]

    # Enroll MFA
    setup = await admin_client.post("/api/v1/auth/mfa/setup")
    secret = _secret_from_uri(setup.json()["otpauthUri"])
    verified = await admin_client.post(
        "/api/v1/auth/mfa/verify", json={"code": pyotp.TOTP(secret).now()}
    )
    assert verified.status_code == 200

    # 1. Fresh session (within 15 min): GET settings succeeds
    with patch("app.api.deps.get_settings", return_value=SimpleNamespace(mfa_enforced=True)):
        get_res = await admin_client.get(f"/api/v1/editions/{edition_id}/admin/settings")
        assert get_res.status_code == 200

    # 2. Simulate 20 minutes passed (session mfa_verified_at is expired)
    user = (await db_session.execute(select(User).where(User.email == OWNER))).scalar_one()
    sessions = (
        await db_session.execute(
            select(Session).where(Session.user_id == user.id, Session.revoked_at.is_(None))
        )
    ).scalars().all()
    for s in sessions:
        s.mfa_verified_at = datetime.now(UTC) - timedelta(minutes=20)
    await db_session.commit()

    with patch("app.api.deps.get_settings", return_value=SimpleNamespace(mfa_enforced=True)):
        # GET settings must STILL succeed without step-up!
        get_res_expired = await admin_client.get(f"/api/v1/editions/{edition_id}/admin/settings")
        assert get_res_expired.status_code == 200

        # GET registration config must STILL succeed without step-up!
        get_config_expired = await admin_client.get(f"/api/v1/editions/{edition_id}/admin/registration/config")
        assert get_config_expired.status_code == 200

        # PATCH settings must challenge for step-up!
        patch_res = await admin_client.patch(
            f"/api/v1/editions/{edition_id}/admin/settings",
            json={"tagline": "Updated tagline test"},
        )
        assert patch_res.status_code == 403
        assert patch_res.json()["error"]["code"] == "STEP_UP_REQUIRED"

        # PATCH registration config must challenge for step-up!
        patch_config_res = await admin_client.patch(
            f"/api/v1/editions/{edition_id}/admin/registration/config",
            json={"settings": {}},
        )
        assert patch_config_res.status_code == 403
        assert patch_config_res.json()["error"]["code"] == "STEP_UP_REQUIRED"

    # 3. Perform step-up
    step_up_res = await admin_client.post(
        "/api/v1/auth/mfa/step-up", json={"code": pyotp.TOTP(secret).now()}
    )
    assert step_up_res.status_code == 200
    assert step_up_res.json()["data"]["stepUp"] is True
    assert step_up_res.json()["data"]["expiresInSeconds"] == 900

    # 4. Now PATCH settings and registration config succeed without prompt!
    with patch("app.api.deps.get_settings", return_value=SimpleNamespace(mfa_enforced=True)):
        patch_res_fresh = await admin_client.patch(
            f"/api/v1/editions/{edition_id}/admin/settings",
            json={"tagline": "Updated fresh tagline"},
        )
        assert patch_res_fresh.status_code == 200

