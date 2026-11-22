import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.commerce import PaymentOrder, Registration
from app.models.edition import Event
from app.models.user import User


async def _current_edition(client: AsyncClient) -> dict:
    resp = await client.get("/api/v1/public/editions/current")
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


@pytest.mark.asyncio
async def test_admin_force_cancel_and_refund_and_roster(
    admin_client: AsyncClient, db_session
):
    edition = await _current_edition(admin_client)
    edition_id = edition["id"]

    # 1. Look up or create a test event registration
    events_resp = await admin_client.get(f"/api/v1/editions/{edition_id}/admin/events")
    assert events_resp.status_code == 200, events_resp.text
    events = events_resp.json()["data"]
    assert len(events) > 0
    test_event = events[0]
    test_event_id = test_event["id"]

    # Get a test user
    test_user = (await db_session.execute(select(User).limit(1))).scalars().first()
    assert test_user is not None
    user_id = test_user.id

    # Create a paid PaymentOrder
    order = PaymentOrder(
        edition_id=uuid.UUID(edition_id),
        user_id=user_id,
        purpose="registration",
        amount_paise=50000,
        status="paid",
    )
    db_session.add(order)
    await db_session.flush()

    # Create a test registration for this user linked to the order
    reg = Registration(
        edition_id=uuid.UUID(edition_id),
        event_id=uuid.UUID(test_event_id),
        user_id=user_id,
        kind="addon",
        fee_paise=50000,
        order_id=order.id,
        status="confirmed",
        registration_number=f"PX-TEST-{uuid.uuid4().hex[:6].upper()}",
    )
    db_session.add(reg)
    await db_session.commit()
    reg_id = str(reg.id)

    # 2. Check event roster endpoint
    roster_resp = await admin_client.get(
        f"/api/v1/editions/{edition_id}/admin/events/{test_event_id}/roster"
    )
    assert roster_resp.status_code == 200, roster_resp.text
    roster_data = roster_resp.json()["data"]
    assert "roster" in roster_data
    assert roster_data["totalRegistered"] >= 1

    # 3. Test Manual Checkin from Roster
    mark_resp = await admin_client.post(
        f"/api/v1/editions/{edition_id}/admin/attendance/mark",
        json={"userId": str(user_id), "eventId": test_event_id},
    )
    assert mark_resp.status_code == 200, mark_resp.text
    att_rec = mark_resp.json()["data"]
    assert att_rec["result"] == "admitted"
    attendance_id = att_rec["id"]

    # Duplicate check
    dup_resp = await admin_client.post(
        f"/api/v1/editions/{edition_id}/admin/attendance/mark",
        json={"userId": str(user_id), "eventId": test_event_id},
    )
    assert dup_resp.status_code == 200, dup_resp.text
    assert dup_resp.json()["data"]["result"] == "duplicate"

    # Revoke / Undo attendance
    del_resp = await admin_client.delete(
        f"/api/v1/editions/{edition_id}/admin/attendance/{attendance_id}"
    )
    assert del_resp.status_code == 200, del_resp.text
    assert del_resp.json()["data"]["revoked"] is True

    # 4. Test Force Cancel with validation: Refund cannot exceed paid fee
    fail_cancel = await admin_client.post(
        f"/api/v1/editions/{edition_id}/admin/registrations/{reg_id}/force-cancel",
        json={
            "reason": "Removed due to violation",
            "issueRefund": True,
            "refundAmountPaise": 60000,  # Exceeds 50000 fee
        },
    )
    # Should fail validation because refund amount exceeds paid fee
    assert fail_cancel.status_code in (400, 422)

    # Cancel with valid partial refund (e.g. 25000 paise = ₹250)
    ok_cancel = await admin_client.post(
        f"/api/v1/editions/{edition_id}/admin/registrations/{reg_id}/force-cancel",
        json={
            "reason": "Removed from event by administration: Rule violation",
            "issueRefund": True,
            "refundAmountPaise": 25000,
            "refundReasonNote": "Partial refund on removal",
        },
    )
    assert ok_cancel.status_code == 200, ok_cancel.text
    res = ok_cancel.json()["data"]
    assert res["status"] == "cancelled"
    assert res["cancelledBy"] == "admin"
    assert "Rule violation" in res["cancellationReason"]
    assert res["refund"]["amountPaise"] == 25000

    # 5. Issue subsequent refund on remaining balance
    refund_more = await admin_client.post(
        f"/api/v1/editions/{edition_id}/admin/registrations/{reg_id}/refund",
        json={"amountPaise": 25000, "reasonNote": "Second tranche refund"},
    )
    assert refund_more.status_code == 200, refund_more.text
    assert refund_more.json()["data"]["amountPaise"] == 25000
    assert refund_more.json()["data"]["remainingRefundablePaise"] == 0

    # 6. Test GET /registrations with status=cancelled
    list_cancelled = await admin_client.get(
        f"/api/v1/editions/{edition_id}/admin/registrations?status=cancelled"
    )
    assert list_cancelled.status_code == 200, list_cancelled.text
    cancelled_data = list_cancelled.json()["data"]
    assert len(cancelled_data) >= 1
    target_row = next(r for r in cancelled_data if r["id"] == reg_id)
    assert target_row["status"] == "cancelled"
    assert target_row["cancelledBy"] == "admin"
    assert target_row["refundedAmountPaise"] == 50000
