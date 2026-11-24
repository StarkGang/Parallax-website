"""Tests for participant workflow and admin portal operations."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.user import User
from app.services.editions import current_policy
from app.services.passes import activate_pass_for_registration


@pytest.mark.asyncio
async def test_participant_pass_flow_and_tickets(
    participant_client: AsyncClient, db_session
):
    client = participant_client

    # Get current edition
    ed_resp = await client.get("/api/v1/public/editions/current")
    assert ed_resp.status_code == 200
    edition_id = ed_resp.json()["data"]["id"]

    # 1. Get pass (none initially)
    p_resp = await client.get(f"/api/v1/editions/{edition_id}/pass")
    assert p_resp.status_code == 200

    # 2. Activate the pass exactly the way the college-registration flow does:
    #    the college registration IS the convention-pass purchase, and its
    #    verification mirrors a pass + entry ticket into the pass tables.
    user = (
        (
            await db_session.execute(
                select(User).where(
                    User.email_normalized == "participant@parallax.local"
                )
            )
        )
        .scalars()
        .first()
    )
    assert user is not None
    policy = await current_policy(db_session, uuid.UUID(edition_id))
    user_pass = await activate_pass_for_registration(
        db_session, user.id, uuid.UUID(edition_id), policy, 50000
    )
    await db_session.commit()
    assert user_pass is not None and user_pass.status == "active"

    # 3. Check pass is now active (via the API)
    active_pass_resp = await client.get(f"/api/v1/editions/{edition_id}/pass")
    assert active_pass_resp.status_code == 200
    pass_data = active_pass_resp.json()["data"]
    assert pass_data["status"] == "active"

    # 4. Check ticket issued
    tkt_resp = await client.get(f"/api/v1/editions/{edition_id}/tickets")
    assert tkt_resp.status_code == 200
    tickets = tkt_resp.json()["data"]
    assert len(tickets) >= 1
    assert tickets[0]["kind"] == "pass"

    # 5. ID-card pass redirects to the interactive frontend view.
    card_resp = await client.get(
        f"/api/v1/editions/{edition_id}/registration/pass-card",
        follow_redirects=False,
    )
    assert card_resp.status_code == 303
    assert card_resp.headers["location"] == "/portal/registration"


@pytest.mark.asyncio
async def test_admin_overview_and_events(admin_client: AsyncClient):
    client = admin_client

    # Get edition id
    ed_resp = await client.get("/api/v1/public/editions/current")
    assert ed_resp.status_code == 200
    edition_id = ed_resp.json()["data"]["id"]

    # 1. Admin overview (should NOT be blocked by MFA)
    stats_resp = await client.get(f"/api/v1/editions/{edition_id}/admin/overview")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()["data"]
    assert "passesSold" in stats
    assert "eventsTotal" in stats

    # 2. Admin list events
    events_resp = await client.get(f"/api/v1/editions/{edition_id}/admin/events")
    assert events_resp.status_code == 200
    evs = events_resp.json()["data"]
    assert len(evs) >= 10
