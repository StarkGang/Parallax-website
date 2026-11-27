"""Tests for packing order (0/1), -1 unlimited count, seat release on unpaid order, force-cancel no-refund, and lunch attendance."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.commerce import AttendanceRecord, EmailOutbox, PaymentOrder, Refund, Registration
from app.models.edition import Event, EventCategory
from app.services.pricing import allowance_pack
from tests.test_compliance_deadlines import (
    ADMIN,
    _edition,
    _fresh_event,
    _login,
    _paid_registration,
)


def _mock_event(title: str, base_paise: int) -> Event:
    now = datetime.now(UTC)
    return Event(
        id=uuid.uuid4(),
        edition_id=uuid.uuid4(),
        category_id=uuid.uuid4(),
        slug=title.lower().replace(" ", "-"),
        title=title,
        summary="Mock",
        format="individual",
        base_value_paise=base_paise,
        addon_price_paise=base_paise,
        included_eligible=True,
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=1, hours=2),
        status="published",
    )


def test_allowance_pack_order_and_unlimited_count():
    ev_a = _mock_event("Event A", 30000)
    ev_b = _mock_event("Event B", 20000)
    ev_c = _mock_event("Event C", 10000)

    # 0 = cheapest first: under 450 cap, picks 100 + 200 = 300 (2 events)
    cheap = allowance_pack([ev_a, ev_b, ev_c], count=3, cap_paise=45000, cap_inclusive=True, pack_order=0)
    assert cheap == [ev_c.id, ev_b.id]

    # 1 = expensive first: under 450 cap, picks 300 + 100 = 400 (2 events)
    exp = allowance_pack([ev_a, ev_b, ev_c], count=3, cap_paise=45000, cap_inclusive=True, pack_order=1)
    assert exp == [ev_a.id, ev_c.id]

    # -1 = unlimited count under cap: picks all 3 when cap=600
    unlimited = allowance_pack([ev_a, ev_b, ev_c], count=-1, cap_paise=60000, cap_inclusive=True, pack_order=0)
    assert len(unlimited) == 3


@pytest.mark.asyncio
async def test_release_unpaid_order_frees_reserved_seat(client: AsyncClient, db_session):
    email = "release.seat@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, email)
    event = await _fresh_event(db_session, uuid.UUID(edition_id), title="Movie Seat Event", price_paise=50000)

    added = await client.post(
        f"/api/v1/editions/{edition_id}/registrations",
        json={"eventIds": [str(event.id)]},
    )
    assert added.status_code in (200, 201), added.text
    order_id = added.json()["data"]["order"]["orderId"]
    reg_id = uuid.UUID(added.json()["data"]["registrations"][0]["id"])

    rel = await client.post(f"/api/v1/editions/{edition_id}/orders/{order_id}/release")
    assert rel.status_code == 200, rel.text
    assert rel.json()["data"]["released"] == 1

    db_session.expire_all()
    seat = await db_session.get(Registration, reg_id)
    assert seat.status == "cancelled"
    order = await db_session.get(PaymentOrder, uuid.UUID(order_id))
    assert order.status == "expired"


@pytest.mark.asyncio
async def test_force_cancel_no_refund_and_lunch_attendance_reset(client: AsyncClient, db_session):
    email = "lunch.force@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    reg = await _paid_registration(client, edition_id, email)
    event = await _fresh_event(db_session, uuid.UUID(edition_id), title="Force Cancel Event", price_paise=30000)

    added = await client.post(
        f"/api/v1/editions/{edition_id}/registrations",
        json={"eventIds": [str(event.id)]},
    )
    order_id = added.json()["data"]["order"]["orderId"]
    reg_id = added.json()["data"]["registrations"][0]["id"]
    paid = await client.post(f"/api/v1/editions/{edition_id}/payments/{order_id}/mock")
    assert paid.status_code == 200, paid.text

    await _login(client, ADMIN, role="admin")
    fc = await client.post(
        f"/api/v1/editions/{edition_id}/admin/registrations/{reg_id}/force-cancel",
        json={"reason": "Rule violation", "issueRefund": False, "force": True},
    )
    assert fc.status_code == 200, fc.text
    assert fc.json()["data"]["refund"] is None

    db_session.expire_all()
    refunds = list(
        (await db_session.execute(select(Refund).where(Refund.order_id == uuid.UUID(order_id)))).scalars()
    )
    assert not refunds, "no-refund force cancel must not park a pending refund"

    # Gate pass scan + Lunch scan on same day do not collide, and lunch duplicates + resets
    token = reg["registrationNumber"]
    gate = await client.post(
        f"/api/v1/editions/{edition_id}/admin/checkin",
        json={"token": token, "scope": "pass", "day": "2026-11-28"},
    )
    assert gate.status_code == 200, gate.text
    assert gate.json()["data"]["result"] == "admitted"

    lunch1 = await client.post(
        f"/api/v1/editions/{edition_id}/admin/checkin",
        json={"token": token, "scope": "lunch", "day": "2026-11-28"},
    )
    assert lunch1.status_code == 200, lunch1.text
    assert lunch1.json()["data"]["result"] == "admitted"
    assert lunch1.json()["data"]["scope"] == "lunch"

    lunch_dup = await client.post(
        f"/api/v1/editions/{edition_id}/admin/checkin",
        json={"token": token, "scope": "lunch", "day": "2026-11-28"},
    )
    assert lunch_dup.status_code == 200, lunch_dup.text
    assert lunch_dup.json()["data"]["result"] == "duplicate"

    # Reset lunch attendance and scan again
    lunch_rec = (
        await db_session.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.edition_id == uuid.UUID(edition_id),
                AttendanceRecord.scope == "lunch",
                AttendanceRecord.day == "2026-11-28",
            )
        )
    ).scalars().first()
    assert lunch_rec is not None
    reset_resp = await client.delete(f"/api/v1/editions/{edition_id}/admin/attendance/{lunch_rec.id}")
    assert reset_resp.status_code == 200, reset_resp.text

    lunch2 = await client.post(
        f"/api/v1/editions/{edition_id}/admin/checkin",
        json={"token": token, "scope": "lunch", "day": "2026-11-28"},
    )
    assert lunch2.status_code == 200, lunch2.text
    assert lunch2.json()["data"]["result"] == "admitted"


@pytest.mark.asyncio
async def test_user_cancel_refund_workflow_and_team_elder_handover(client: AsyncClient, db_session):
    leader_email = "team.leader.cancel@test.local"
    member_email = "team.member.cancel@test.local"

    await _login(client, leader_email)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, leader_email)

    await _login(client, member_email)
    await _paid_registration(client, edition_id, member_email)

    event = await _fresh_event(
        db_session, uuid.UUID(edition_id), title="Team Refund Event", format="team", price_paise=25000
    )

    # Leader registers and creates team
    await _login(client, leader_email)
    add1 = await client.post(
        f"/api/v1/editions/{edition_id}/registrations", json={"eventIds": [str(event.id)]}
    )
    assert add1.status_code in (200, 201), add1.text
    o1 = add1.json()["data"]["order"]["orderId"]
    r1 = add1.json()["data"]["registrations"][0]["id"]
    await client.post(f"/api/v1/editions/{edition_id}/payments/{o1}/mock")

    team_resp = await client.post(
        f"/api/v1/editions/{edition_id}/teams",
        json={"eventId": str(event.id), "name": "Handover Squad"},
    )
    assert team_resp.status_code in (200, 201), team_resp.text
    invite_code = team_resp.json()["data"]["inviteCode"]

    # Member joins team
    await _login(client, member_email)
    add2 = await client.post(
        f"/api/v1/editions/{edition_id}/registrations", json={"eventIds": [str(event.id)]}
    )
    o2 = add2.json()["data"]["order"]["orderId"]
    await client.post(f"/api/v1/editions/{edition_id}/payments/{o2}/mock")
    join_resp = await client.post(
        f"/api/v1/editions/{edition_id}/teams/join", json={"inviteCode": invite_code}
    )
    assert join_resp.status_code == 200, join_resp.text

    # Leader cancels event -> member becomes leader, worklist shows pending refund
    await _login(client, leader_email)
    cancel_resp = await client.delete(f"/api/v1/editions/{edition_id}/registrations/{r1}")
    assert cancel_resp.status_code == 200, cancel_resp.text

    wl = await client.get(f"/api/v1/editions/{edition_id}/worklist")
    assert wl.status_code == 200, wl.text
    cancelled = wl.json()["data"]["cancelledEvents"]
    assert cancelled and cancelled[0]["refund"]["status"] == "pending"

    # Admin confirms pending refund -> status becomes processed in both admin & user worklist
    await _login(client, ADMIN, role="admin")
    rfs = (await client.get(f"/api/v1/editions/{edition_id}/admin/refunds")).json()["data"]
    pending_rf = next(r for r in rfs if r["orderId"] == o1 and r["status"] == "pending")
    proc = await client.post(f"/api/v1/editions/{edition_id}/admin/refunds/{pending_rf['id']}/process")
    assert proc.status_code == 200, proc.text
    assert proc.json()["data"]["status"] == "processed"

    await _login(client, leader_email)
    wl2 = await client.get(f"/api/v1/editions/{edition_id}/worklist")
    assert wl2.json()["data"]["cancelledEvents"][0]["refund"]["status"] == "processed"

