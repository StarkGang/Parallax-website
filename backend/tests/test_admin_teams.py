"""Admin team management: list rosters, lock/unlock and disband a team."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

try:
    from tests.test_teams_and_editions import (
        _edition,
        _fresh_event,
        _login,
        _paid_registration,
    )
except ImportError:
    from test_teams_and_editions import (
        _edition,
        _fresh_event,
        _login,
        _paid_registration,
    )


@pytest.mark.asyncio
async def test_admin_can_list_lock_and_disband_teams(client: AsyncClient, db_session):
    """Organisers can inspect every roster and manage its lifecycle."""
    leader_email = "admin.team.lead@test.local"
    await _login(client, leader_email)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, leader_email)
    event = await _fresh_event(
        db_session,
        uuid.UUID(edition_id),
        title="Admin Team Cup",
        format="team",
        price_paise=0,
    )
    q = await client.post(
        f"/api/v1/editions/{edition_id}/quote",
        json={"eventIds": [str(event.id)]},
    )
    assert q.status_code == 200, q.text
    chk = await client.post(
        f"/api/v1/editions/{edition_id}/checkout",
        json={"quoteId": q.json()["data"]["quoteId"]},
    )
    assert chk.status_code == 200, chk.text
    created = await client.post(
        f"/api/v1/editions/{edition_id}/teams",
        json={"eventId": str(event.id), "name": "Admin Squad"},
    )
    assert created.status_code in (200, 201), created.text
    team_id = created.json()["data"]["id"]
    invite = created.json()["data"]["inviteCode"]
    assert invite

    await _login(client, "owner@parallax.local", role="admin")
    listed = await client.get(f"/api/v1/editions/{edition_id}/admin/teams")
    assert listed.status_code == 200, listed.text
    rows = listed.json()["data"]
    row = next(item for item in rows if item["id"] == team_id)
    assert row["leaderEmail"] == leader_email
    assert row["inviteCode"] == invite
    assert len(row["members"]) == 1
    assert row["members"][0]["seatStatus"] == "confirmed"
    assert row["paymentStatus"] in ("free", "paid")

    locked = await client.post(
        f"/api/v1/editions/{edition_id}/admin/teams/{team_id}/lock"
    )
    assert locked.status_code == 200, locked.text
    assert locked.json()["data"]["status"] == "locked"
    unlocked = await client.post(
        f"/api/v1/editions/{edition_id}/admin/teams/{team_id}/lock"
    )
    assert unlocked.status_code == 200, unlocked.text
    assert unlocked.json()["data"]["status"] == "active"

    disbanded = await client.delete(
        f"/api/v1/editions/{edition_id}/admin/teams/{team_id}"
    )
    assert disbanded.status_code == 200, disbanded.text
    assert disbanded.json()["data"]["status"] == "disbanded"
    assert disbanded.json()["data"]["cancelledSeats"] == 1

    filtered = await client.get(
        f"/api/v1/editions/{edition_id}/admin/teams", params={"status": "disbanded"}
    )
    assert filtered.status_code == 200, filtered.text
    assert any(item["id"] == team_id for item in filtered.json()["data"])
