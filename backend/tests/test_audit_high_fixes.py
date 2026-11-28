"""Tests for the audit HIGH fixes (approve import, ticket revoke, refund amount, etc.)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commerce import Registration
from app.models.commerce import Ticket
from app.models.registration import CollegeRegistration
from app.services.tickets import ticket_token_for


@pytest.mark.asyncio
async def test_approve_event_registration_returns_2xx(
    admin_client: AsyncClient, db_session: AsyncSession
):
    """approve_event_registration must not 500 on its local Registration import."""
    edition_id = uuid.uuid4()
    reg = Registration(
        edition_id=edition_id,
        user_id=uuid.uuid4(),
        event_id=uuid.uuid4(),
        kind="addon",
        fee_paise=20000,
        status="pending",
        registration_number=f"REG-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(reg)
    await db_session.commit()
    reg_id = reg.id

    resp = await admin_client.post(
        f"/api/v1/editions/{edition_id}/admin/registrations/{reg_id}/approve"
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "confirmed"

    db_session.expire_all()
    refreshed = (
        await db_session.execute(select(Registration).where(Registration.id == reg_id))
    ).scalars().one()
    assert refreshed.status == "confirmed"
async def _make_paid_approved_registration(db_session, edition_id, user_id):
    reg = CollegeRegistration(
        edition_id=edition_id,
        user_id=user_id,
        category_id=uuid.uuid4(),
        category_code="C1",
        category_name="General",
        full_name="Test User",
        email=f"{user_id.hex[:8]}@test.local",
        college_name="Test College",
        payment_status="paid",
        verification_status="approved",
    )
    db_session.add(reg)
    await db_session.flush()
    return reg


async def _make_ticket(db_session, edition_id, user_id, status):
    ticket = Ticket(
        edition_id=edition_id,
        user_id=user_id,
        token_hash=uuid.uuid4().hex,
        token_prefix="PX",
        status=status,
    )
    db_session.add(ticket)
    await db_session.flush()
    return ticket


@pytest.mark.asyncio
async def test_revoked_ticket_is_not_valid(client: AsyncClient, db_session: AsyncSession):
    """A revoked ticket must not verify as a valid pass even if the underlying registration is paid/approved."""
    edition_id = uuid.uuid4()
    user_id = uuid.uuid4()
    await _make_paid_approved_registration(db_session, edition_id, user_id)
    ticket = await _make_ticket(db_session, edition_id, user_id, "revoked")
    await db_session.commit()

    code = ticket_token_for(ticket.id)
    resp = await client.get(f"/api/v1/public/c/{code}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["valid"] is False


@pytest.mark.asyncio
async def test_active_ticket_is_valid(client: AsyncClient, db_session: AsyncSession):
    """An active ticket on a paid/approved registration verifies as valid."""
    edition_id = uuid.uuid4()
    user_id = uuid.uuid4()
    await _make_paid_approved_registration(db_session, edition_id, user_id)
    ticket = await _make_ticket(db_session, edition_id, user_id, "active")
    await db_session.commit()

    code = ticket_token_for(ticket.id)
    resp = await client.get(f"/api/v1/public/c/{code}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["valid"] is True


@pytest.mark.asyncio
async def test_unknown_code_is_not_valid(client: AsyncClient):
    """An unknown/tampered code stays invalid (unchanged behaviour)."""
    resp = await client.get("/api/v1/public/c/PX-DEADBEEF-0000")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["valid"] is False
