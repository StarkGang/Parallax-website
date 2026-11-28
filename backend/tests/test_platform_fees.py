"""Tests for configurable platform fee (%) and exempt-under threshold across pass & event orders."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.commerce import PaymentOrder
from app.services.payments import calculate_platform_fee
from tests.test_compliance_deadlines import (
    ADMIN,
    _edition,
    _fresh_event,
    _login,
    _paid_registration,
)


def test_calculate_platform_fee_rules():
    class P:
        def __init__(self, bps, exempt):
            self.platform_fee_bps = bps
            self.platform_fee_exempt_under_paise = exempt

    # Disabled (0%)
    assert calculate_platform_fee(50000, P(0, 0)) == (0, 50000)

    # 2% on all transactions (exempt_under = 0)
    assert calculate_platform_fee(50000, P(200, 0)) == (1000, 51000)
    assert calculate_platform_fee(10000, P(200, 0)) == (200, 10200)

    # 2% with exempt under ₹300 (30000 paise)
    assert calculate_platform_fee(25000, P(200, 30000)) == (0, 25000)
    assert calculate_platform_fee(30000, P(200, 30000)) == (600, 30600)


@pytest.mark.asyncio
async def test_platform_fee_applied_to_pass_and_event_orders(client: AsyncClient, db_session):
    edition = await _edition(client)
    edition_id = edition["id"]

    # Admin configures 2.5% platform fee (250 bps), exempt under ₹300 (30000 paise)
    await _login(client, ADMIN, role="admin")
    policies = (await client.get(f"/api/v1/editions/{edition_id}/admin/policies")).json()["data"]
    cur = next(p for p in policies if p["isCurrent"])
    upd = await client.post(
        f"/api/v1/editions/{edition_id}/admin/policies",
        json={
            "lunchIncludedDays": cur["lunchIncludedDays"],
            "includedEventCount": cur["includedEventCount"],
            "includedValueCapPaise": cur["includedValueCapPaise"],
            "capInclusive": cur["capInclusive"],
            "allowancePackOrder": cur.get("allowancePackOrder", 0),
            "addonRequiresPass": cur["addonRequiresPass"],
            "teamMembersRequirePass": cur["teamMembersRequirePass"],
            "holdMinutes": cur["holdMinutes"],
            "gstNote": cur.get("gstNote"),
            "platformFeeBps": 250,
            "platformFeeExemptUnderPaise": 30000,
            "reason": "Enable 2.5% platform fee above ₹300",
        },
    )
    assert upd.status_code == 200, upd.text
    policies_after = (await client.get(f"/api/v1/editions/{edition_id}/admin/policies")).json()["data"]
    cur_after = next(p for p in policies_after if p["isCurrent"])
    assert cur_after["platformFeeBps"] == 250
    assert cur_after["platformFeeExemptUnderPaise"] == 30000

    # Participant buys pass (fee > ₹300 -> 2.5% applied)
    email = "platform.fee@test.local"
    await _login(client, email)
    reg = await _paid_registration(client, edition_id, email)
    base_fee = reg["feePaise"]
    expected_pass_fee = round(base_fee * 250 / 10000) if base_fee >= 30000 else 0
    assert reg["order"]["platformFeePaise"] == expected_pass_fee
    assert reg["order"]["amountPaise"] == base_fee + expected_pass_fee

    # Event under ₹300 -> ₹0 platform fee
    cheap_ev = await _fresh_event(db_session, uuid.UUID(edition_id), title="Cheap Event", price_paise=20000)
    r_cheap = await client.post(
        f"/api/v1/editions/{edition_id}/registrations", json={"eventIds": [str(cheap_ev.id)]}
    )
    assert r_cheap.status_code in (200, 201), r_cheap.text
    o_cheap_id = uuid.UUID(r_cheap.json()["data"]["order"]["orderId"])
    o_cheap = await db_session.get(PaymentOrder, o_cheap_id)
    assert o_cheap.platform_fee_paise == 0
    assert o_cheap.amount_paise == 20000

    # Event >= ₹300 -> 2.5% platform fee
    exp_ev = await _fresh_event(db_session, uuid.UUID(edition_id), title="Expensive Event", price_paise=40000)
    r_exp = await client.post(
        f"/api/v1/editions/{edition_id}/registrations", json={"eventIds": [str(exp_ev.id)]}
    )
    assert r_exp.status_code in (200, 201), r_exp.text
    o_exp_id = uuid.UUID(r_exp.json()["data"]["order"]["orderId"])
    o_exp = await db_session.get(PaymentOrder, o_exp_id)
    assert o_exp.platform_fee_paise == 1000
    assert o_exp.amount_paise == 41000

