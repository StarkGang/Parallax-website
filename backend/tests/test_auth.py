"""Tests for authentication: pure Google Auth, easy login without MFA, and admin elevation."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_participant_login_easy_no_mfa(client: AsyncClient):
    """Participant logs in simply without MFA barriers."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "student@nssce.ac.in", "role": "participant", "fullName": "Test Student"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["user"]["email"] == "student@nssce.ac.in"
    # The session travels in an HttpOnly cookie; the body must not repeat it.
    assert "token" not in data
    assert any("session" in c for c in resp.headers.get_list("set-cookie"))

    # Check /me
    me_resp = await client.get("/api/v1/me")
    assert me_resp.status_code == 200
    me_data = me_resp.json()["data"]
    assert me_data["email"] == "student@nssce.ac.in"
    assert me_data["mfaRequired"] is False
    assert me_data["mfaEnabled"] is False


@pytest.mark.asyncio
async def test_admin_login_elevates_immediately_no_mfa(client: AsyncClient):
    """Admin logs in and immediately receives super_admin permissions without MFA blockage."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@parallax.local", "role": "admin"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["user"]["email"] == "owner@parallax.local"

    # Check /me reflects super_admin and no MFA blockage
    me_resp = await client.get("/api/v1/me")
    assert me_resp.status_code == 200
    me_data = me_resp.json()["data"]
    assert me_data["email"] == "owner@parallax.local"
    assert me_data["mfaRequired"] is False
    roles = [r["role"] for r in me_data["roles"]]
    assert "super_admin" in roles


@pytest.mark.asyncio
async def test_dev_login_endpoint(client: AsyncClient):
    """Test GET /api/v1/auth/dev/login endpoint."""
    resp = await client.get(
        "/api/v1/auth/dev/login?role=admin",
        follow_redirects=False,
    )
    # Redirects to portal with session cookie set
    assert resp.status_code == 302
    assert "Set-Cookie" in resp.headers
    cookie = resp.headers["Set-Cookie"]
    assert "px_session=" in cookie



@pytest.mark.asyncio
async def test_google_login_redirect_uri_canonical(client: AsyncClient, monkeypatch):
    """Google OAuth login uses the canonical authorized redirect URI."""
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "google_client_id", "test-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "test-client-secret")
    monkeypatch.setattr(settings, "google_redirect_uri", "https://parallax-iste.vercel.app/google/callback")

    resp = await client.get("/api/v1/auth/google/login", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers["Location"]
    assert "accounts.google.com" in location
    assert "redirect_uri=https%3A%2F%2Fparallax-iste.vercel.app%2Fgoogle%2Fcallback" in location
    assert "state=" in location


@pytest.mark.asyncio
async def test_top_level_google_callback_route(client: AsyncClient):
    """Top-level /google/callback and /auth/ routes exist and do not 404."""
    resp1 = await client.get("/google/callback", follow_redirects=False)
    assert resp1.status_code == 302
    assert "/login?error=signin_failed" in resp1.headers["Location"]

    resp2 = await client.get("/auth/", follow_redirects=False)
    assert resp2.status_code == 302
    assert "/login?error=signin_failed" in resp2.headers["Location"]


@pytest.mark.asyncio
async def test_profile_locks_after_registering(client: AsyncClient):
    """Profile is editable before registering, then locked once registered."""
    await client.post(
        "/api/v1/auth/login",
        json={"email": "profile-lock@example.test", "role": "participant", "fullName": "Before Reg"},
    )
    before = await client.get("/api/v1/me/profile")
    assert before.status_code == 200
    assert before.json()["data"]["profileLocked"] is False

    ok = await client.patch(
        "/api/v1/me/profile",
        json={"fullName": "Edited Name", "collegeName": "NSSCE", "branch": "CSE"},
    )
    assert ok.status_code == 200

    edition_id = (await client.get("/api/v1/public/editions/current")).json()["data"]["id"]
    cat_id = next(
        c["id"]
        for c in (await client.get(f"/api/v1/editions/{edition_id}/registration")).json()["data"]["categories"]
        if c["enabled"]
    )
    reg = await client.put(
        f"/api/v1/editions/{edition_id}/registration/profile",
        json={
            "categoryId": cat_id,
            "fullName": "Edited Name",
            "email": "profile-lock@example.test",
            "phone": "9876543210",
            "collegeName": "NSSCE",
            "course": "B.Tech",
            "branch": "CSE",
            "yearOfStudy": "3",
            "gender": "male",
            "foodPreference": "veg",
            "needsAccommodation": False,
        },
    )
    assert reg.status_code == 200, reg.text

    # Before payment, profile is still editable.
    mid = await client.get("/api/v1/me/profile")
    assert mid.status_code == 200
    assert mid.json()["data"]["profileLocked"] is False

    # Pay for the pass using mock gateway.
    import base64

    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    cats = (await client.get(f"/api/v1/editions/{edition_id}/registration")).json()["data"]["categories"]
    cat = next(c for c in cats if c["id"] == cat_id)
    for req in cat["requiredDocuments"]:
        up = await client.post(
            f"/api/v1/editions/{edition_id}/registration/documents/{req['type']}",
            files={"file": ("id.png", png, "image/png")},
        )
        assert up.status_code == 200, up.text
    submitted = await client.post(f"/api/v1/editions/{edition_id}/registration/submit")
    assert submitted.status_code == 200, submitted.text
    order_id = submitted.json()["data"]["payment"]["orderId"]
    paid = await client.post(f"/api/v1/editions/{edition_id}/registration/payments/{order_id}/mock")
    assert paid.status_code == 200, paid.text

    after = await client.get("/api/v1/me/profile")
    assert after.status_code == 200
    assert after.json()["data"]["profileLocked"] is True

    blocked = await client.patch(
        "/api/v1/me/profile",
        json={"fullName": "Sneaky Rename", "branch": "ECE"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "PROFILE_LOCKED"
