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
    assert "token" in data

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
