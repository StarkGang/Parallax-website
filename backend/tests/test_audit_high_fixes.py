"""Tests for the audit HIGH fixes (approve import, ticket revoke, refund amount, etc.)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commerce import Registration


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