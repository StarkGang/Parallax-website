"""Tests for participant workflow and admin portal operations."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_participant_pass_flow_and_tickets(participant_client: AsyncClient):
    client = participant_client

    # Get current edition
    ed_resp = await client.get("/api/v1/public/editions/current")
    assert ed_resp.status_code == 200
    edition_id = ed_resp.json()["data"]["id"]

    # 1. Get pass (none initially)
    p_resp = await client.get(f"/api/v1/editions/{edition_id}/pass")
    assert p_resp.status_code == 200

    # 2. Create pass order
    order_resp = await client.post(f"/api/v1/editions/{edition_id}/pass/order")
    assert order_resp.status_code == 200
    order_data = order_resp.json()["data"]
    order_id = order_data["orderId"]
    assert order_data["amountPaise"] == 35000

    # 3. Pay for order via mock
    pay_resp = await client.post(f"/api/v1/editions/{edition_id}/payments/{order_id}/mock")
    assert pay_resp.status_code == 200
    assert pay_resp.json()["data"]["paid"] is True

    # 4. Check pass is now active
    active_pass_resp = await client.get(f"/api/v1/editions/{edition_id}/pass")
    assert active_pass_resp.status_code == 200
    pass_data = active_pass_resp.json()["data"]
    assert pass_data["status"] == "active"

    # 5. Check ticket issued
    tkt_resp = await client.get(f"/api/v1/editions/{edition_id}/tickets")
    assert tkt_resp.status_code == 200
    tickets = tkt_resp.json()["data"]
    assert len(tickets) >= 1
    assert tickets[0]["kind"] == "pass"


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
