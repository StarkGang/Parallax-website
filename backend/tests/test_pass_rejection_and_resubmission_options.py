"""Tests for pass rejection refund toggles and 24h doc resubmission expiry revocation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.commerce import ConventionPass, PaymentOrder, Refund, Registration, Ticket
from app.models.registration import CollegeRegistration
from tests.test_compliance_deadlines import (
    ADMIN,
    _add_paid_seat,
    _edition,
    _expire,
    _fresh_event,
    _login,
    _paid_registration,
    _trigger_sweep,
)


@pytest.mark.asyncio
async def test_reject_without_pass_or_event_refund_still_revokes_pass_and_releases_seat(
    client: AsyncClient, db_session
):
    email = "reject.norefund@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    registration = await _paid_registration(client, edition_id, email)
    event = await _fresh_event(db_session, uuid.UUID(edition_id), title="No Refund Seat")
    seat_id = await _add_paid_seat(client, edition_id, event.id)

    await _login(client, ADMIN, role="admin")
    decided = await client.post(
        f"/api/v1/editions/{edition_id}/admin/registration/{registration['id']}/decision",
        json={
            "decision": "rejected",
            "reasonCode": "invalid_college_id",
            "initiateRefund": False,
            "refundEvents": False,
        },
    )
    assert decided.status_code == 200, decided.text
    data = decided.json()["data"]
    assert data["verificationStatus"] == "rejected"
    assert data["refundStatus"] == "not_initiated"

    db_session.expire_all()
    reg_row = await db_session.get(CollegeRegistration, uuid.UUID(registration["id"]))
    assert reg_row.verification_status == "rejected"
    assert reg_row.refund_status == "not_initiated"

    pass_row = (
        await db_session.execute(
            select(ConventionPass).where(
                ConventionPass.user_id == reg_row.user_id,
                ConventionPass.edition_id == reg_row.edition_id,
            )
        )
    ).scalars().first()
    assert pass_row is not None and pass_row.status == "cancelled"

    ticket_row = (
        await db_session.execute(
            select(Ticket).where(Ticket.pass_id == pass_row.id)
        )
    ).scalars().first()
    assert ticket_row is not None and ticket_row.status == "revoked"

    seat = await db_session.get(Registration, seat_id)
    assert seat.status == "cancelled"

    pass_refunds = list(
        (
            await db_session.execute(
                select(Refund).where(Refund.order_id == reg_row.order_id)
            )
        ).scalars()
    )
    event_refunds = list(
        (
            await db_session.execute(
                select(Refund).where(Refund.order_id == seat.order_id)
            )
        ).scalars()
    )
    assert not pass_refunds
    assert not event_refunds


@pytest.mark.asyncio
async def test_doc_resubmission_expiry_revokes_pass_and_respects_no_refund_option(
    client: AsyncClient, db_session
):
    email = "resubmit.norefund@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    registration = await _paid_registration(client, edition_id, email)
    event = await _fresh_event(db_session, uuid.UUID(edition_id), title="Resubmit No Refund Seat")
    seat_id = await _add_paid_seat(client, edition_id, event.id)

    await _login(client, ADMIN, role="admin")
    requested = await client.post(
        f"/api/v1/editions/{edition_id}/admin/registration/{registration['id']}/request-documents",
        json={
            "documents": ["college_id"],
            "message": "Blurry ID card.",
            "refundPassOnExpiry": False,
            "refundEventsOnExpiry": False,
        },
    )
    assert requested.status_code == 200, requested.text

    await _expire(db_session, uuid.UUID(registration["id"]))
    await _trigger_sweep(client, edition_id, "resubmit.norefund.trigger@test.local")

    db_session.expire_all()
    reg_row = await db_session.get(CollegeRegistration, uuid.UUID(registration["id"]))
    assert reg_row.verification_status == "rejected"
    assert reg_row.rejection_code == "resubmission_expired"
    assert reg_row.refund_status == "not_initiated"

    pass_row = (
        await db_session.execute(
            select(ConventionPass).where(
                ConventionPass.user_id == reg_row.user_id,
                ConventionPass.edition_id == reg_row.edition_id,
            )
        )
    ).scalars().first()
    assert pass_row is not None and pass_row.status == "cancelled"

    ticket_row = (
        await db_session.execute(
            select(Ticket).where(Ticket.pass_id == pass_row.id)
        )
    ).scalars().first()
    assert ticket_row is not None and ticket_row.status == "revoked"

    seat = await db_session.get(Registration, seat_id)
    assert seat.status == "cancelled"
    order = await db_session.get(PaymentOrder, seat.order_id)
    assert order.status == "paid"

