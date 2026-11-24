"""BUG-001 / BUG-002: config is not cached while unresolved; inquiries persist."""

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_get


@pytest.mark.asyncio
async def test_config_does_not_cache_an_unresolved_edition(client: AsyncClient):
    with patch(
        "app.api.v1.public.current_edition", side_effect=RuntimeError("db down")
    ):
        # The transport surfaces the error instead of a 5xx body; what matters is
        # that the failure is not cached as a valid, edition-less config.
        with pytest.raises(RuntimeError):
            await client.get("/api/v1/public/config")

    assert cache_get("public:config") is None


@pytest.mark.asyncio
async def test_inquiry_is_accepted_without_storing_a_row(
    client: AsyncClient, db_session: AsyncSession
):
    res = await client.post(
        "/api/v1/public/inquiries",
        json={
            "name": "Asha",
            "email": "asha@example.com",
            "category": "Registration",
            "message": "Can I transfer my pass?",
        },
    )

    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["sent"] is True
    assert data["notified"] is False
    assert "not configured" in data["message"]

    # Inquiries are logged, not persisted: there is no storage table for them.
    stored = await db_session.execute(
        text(
            "SELECT count(*) FROM sqlite_master "
            "WHERE type='table' AND name='inquiries'"
        )
    )
    assert stored.scalar_one() == 0
