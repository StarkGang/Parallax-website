"""AUTH-002 / ADMIN-002: MFA cannot lock staff out, playground stays dev-only."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app import main as main_module


def test_startup_refuses_enforced_mfa_without_ui():
    with patch.object(
        main_module, "get_settings", return_value=SimpleNamespace(mfa_enforced=True, mfa_ui_ready=False)
    ):
        with pytest.raises(RuntimeError) as exc:
            main_module.assert_mfa_startable()
    assert "MFA_UI_READY" in str(exc.value)


def test_startup_allows_enforced_mfa_when_ui_is_ready():
    with patch.object(
        main_module, "get_settings", return_value=SimpleNamespace(mfa_enforced=True, mfa_ui_ready=True)
    ):
        main_module.assert_mfa_startable()


def test_startup_allows_mfa_off():
    with patch.object(
        main_module, "get_settings", return_value=SimpleNamespace(mfa_enforced=False, mfa_ui_ready=False)
    ):
        main_module.assert_mfa_startable()


@pytest.mark.asyncio
async def test_db_playground_is_hidden_in_production(admin_client: AsyncClient):
    edition_id = (
        await admin_client.get("/api/v1/public/editions/current")
    ).json()["data"]["id"]

    with patch(
        "app.core.config.get_settings",
        return_value=SimpleNamespace(
            is_debug=False, is_development=False, is_test=False, mfa_enforced=False
        ),
    ):
        res = await admin_client.post(
            f"/api/v1/admin/editions/{edition_id}/db-playground/seed",
            json={
                "userEmailOrId": "nobody@example.com",
                "target": "pass",
                "reason": "audit test",
            },
        )

    assert res.status_code == 404


@pytest.mark.asyncio
async def test_db_playground_is_reachable_in_development(admin_client: AsyncClient):
    edition_id = (
        await admin_client.get("/api/v1/public/editions/current")
    ).json()["data"]["id"]

    res = await admin_client.post(
        f"/api/v1/admin/editions/{edition_id}/db-playground/seed",
        json={
            "userEmailOrId": "participant@parallax.local",
            "target": "pass",
            "reason": "audit test",
        },
    )

    # The gate is open: the request reaches real work and reports a domain
    # error (unknown user/policy) rather than the generic hidden-route 404.
    assert res.json().get("detail") != "Not found.", res.text
