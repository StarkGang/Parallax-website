"""Tests for the audit HIGH fixes (approve import, ticket revoke, refund amount, etc.)."""

import uuid
from datetime import UTC, datetime

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


async def _make_paid_college(db_session, edition_id, user_id, fee_paise):
    from app.models.commerce import PaymentOrder

    order = PaymentOrder(
        edition_id=edition_id,
        user_id=user_id,
        purpose="college_registration",
        amount_paise=fee_paise,
        status="paid",
        gateway_order_id=f"order_{uuid.uuid4().hex[:10]}",
        paid_at=datetime.now(UTC),
    )
    db_session.add(order)
    await db_session.flush()
    reg = CollegeRegistration(
        edition_id=edition_id,
        user_id=user_id,
        category_id=uuid.uuid4(),
        category_code="C1",
        category_name="General",
        full_name="Refund User",
        email=f"{user_id.hex[:8]}@test.local",
        college_name="Test College",
        payment_status="paid",
        verification_status="approved",
        fee_paise=fee_paise,
        order_id=order.id,
    )
    db_session.add(reg)
    await db_session.flush()
    return reg


@pytest.mark.asyncio
async def test_refund_amount_zero_is_rejected(db_session: AsyncSession):
    """amountPaise: 0 must be rejected, not silently refund the full fee."""
    from app.core.errors import ValidationFailed
    from app.services import college_registrations as cr

    reg = await _make_paid_college(db_session, uuid.uuid4(), uuid.uuid4(), 50000)
    await db_session.commit()
    with pytest.raises(ValidationFailed):
        await cr.refund_action(
            db_session, None, reg, None, None,
            action="initiate", amount_paise=0, note=None, gateway_refund_id=None,
        )


@pytest.mark.asyncio
async def test_refund_amount_negative_is_rejected(db_session: AsyncSession):
    from app.core.errors import ValidationFailed
    from app.services import college_registrations as cr

    reg = await _make_paid_college(db_session, uuid.uuid4(), uuid.uuid4(), 50000)
    await db_session.commit()
    with pytest.raises(ValidationFailed):
        await cr.refund_action(
            db_session, None, reg, None, None,
            action="initiate", amount_paise=-100, note=None, gateway_refund_id=None,
        )


@pytest.mark.asyncio
async def test_refund_amount_omitted_refunds_full(db_session: AsyncSession):
    from app.services import college_registrations as cr

    reg = await _make_paid_college(db_session, uuid.uuid4(), uuid.uuid4(), 50000)
    await db_session.commit()
    refund = await cr.refund_action(
        db_session, None, reg, None, None,
        action="initiate", amount_paise=None, note=None, gateway_refund_id=None,
    )
    assert refund.amount_paise == 50000


@pytest.mark.asyncio
async def test_refund_amount_partial_is_exact(db_session: AsyncSession):
    from app.services import college_registrations as cr

    reg = await _make_paid_college(db_session, uuid.uuid4(), uuid.uuid4(), 50000)
    await db_session.commit()
    refund = await cr.refund_action(
        db_session, None, reg, None, None,
        action="initiate", amount_paise=20000, note=None, gateway_refund_id=None,
    )
    assert refund.amount_paise == 20000


@pytest.mark.asyncio
async def test_refund_amount_over_refundable_is_capped(db_session: AsyncSession):
    from app.services import college_registrations as cr

    reg = await _make_paid_college(db_session, uuid.uuid4(), uuid.uuid4(), 50000)
    await db_session.commit()
    refund = await cr.refund_action(
        db_session, None, reg, None, None,
        action="initiate", amount_paise=90000, note=None, gateway_refund_id=None,
    )
    assert refund.amount_paise == 50000


def test_refund_action_schema_rejects_zero():
    from pydantic import ValidationError

    from app.schemas.registration import RefundAction

    assert RefundAction(action="initiate").amount_paise is None
    with pytest.raises(ValidationError):
        RefundAction(action="initiate", amount_paise=0)
    with pytest.raises(ValidationError):
        RefundAction(action="initiate", amount_paise=-5)


async def _make_order(db_session, edition_id, user_id, status, amount_paise=50000):
    from app.models.commerce import PaymentOrder

    order = PaymentOrder(
        edition_id=edition_id,
        user_id=user_id,
        purpose="registration",
        amount_paise=amount_paise,
        status=status,
        gateway_order_id=f"order_{uuid.uuid4().hex[:10]}",
        paid_at=datetime.now(UTC) if status == "paid" else None,
    )
    db_session.add(order)
    await db_session.flush()
    return order


async def _make_event_reg(db_session, edition_id, user_id, order_id, status="confirmed"):
    reg = Registration(
        edition_id=edition_id,
        user_id=user_id,
        event_id=uuid.uuid4(),
        kind="addon",
        fee_paise=50000,
        status=status,
        registration_number=f"REG-{uuid.uuid4().hex[:8]}",
        order_id=order_id,
    )
    db_session.add(reg)
    await db_session.flush()
    return reg


async def _force_cancel(admin_client, edition_id, reg_id, body=None):
    return await admin_client.post(
        f"/api/v1/editions/{edition_id}/admin/registrations/{reg_id}/force-cancel",
        json=body or {},
    )


@pytest.mark.asyncio
async def test_force_cancel_expires_solo_unpaid_order(admin_client: AsyncClient, db_session: AsyncSession):
    from app.models.commerce import PaymentOrder

    edition_id = uuid.uuid4()
    order = await _make_order(db_session, edition_id, uuid.uuid4(), "created")
    reg = await _make_event_reg(db_session, edition_id, uuid.uuid4(), order.id)
    await db_session.commit()
    reg_id, order_id = reg.id, order.id

    resp = await _force_cancel(admin_client, edition_id, reg_id)
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    stored = await db_session.get(PaymentOrder, order_id)
    assert stored.status == "expired"


@pytest.mark.asyncio
async def test_force_cancel_keeps_shared_unpaid_order(admin_client: AsyncClient, db_session: AsyncSession):
    from app.models.commerce import PaymentOrder

    edition_id = uuid.uuid4()
    user_id = uuid.uuid4()
    order = await _make_order(db_session, edition_id, user_id, "created")
    leader = await _make_event_reg(db_session, edition_id, user_id, order.id)
    await _make_event_reg(db_session, edition_id, uuid.uuid4(), order.id, status="confirmed")
    await db_session.commit()
    leader_id, order_id = leader.id, order.id

    resp = await _force_cancel(admin_client, edition_id, leader_id)
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    stored = await db_session.get(PaymentOrder, order_id)
    assert stored.status == "created"


@pytest.mark.asyncio
async def test_force_cancel_leaves_paid_order_untouched(admin_client: AsyncClient, db_session: AsyncSession):
    from app.models.commerce import PaymentOrder

    edition_id = uuid.uuid4()
    order = await _make_order(db_session, edition_id, uuid.uuid4(), "paid")
    reg = await _make_event_reg(db_session, edition_id, uuid.uuid4(), order.id)
    await db_session.commit()
    reg_id, order_id = reg.id, order.id

    resp = await _force_cancel(admin_client, edition_id, reg_id)
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    stored = await db_session.get(PaymentOrder, order_id)
    assert stored.status == "paid"


@pytest.mark.asyncio
async def test_force_cancel_drops_attendance(admin_client: AsyncClient, db_session: AsyncSession):
    from app.models.commerce import AttendanceRecord

    edition_id = uuid.uuid4()
    user_id = uuid.uuid4()
    reg = await _make_event_reg(db_session, edition_id, user_id, None)
    event_id = reg.event_id
    db_session.add(
        AttendanceRecord(
            edition_id=edition_id,
            user_id=user_id,
            event_id=event_id,
            scope="event",
            day="1",
            result="admitted",
        )
    )
    await db_session.commit()
    reg_id = reg.id

    resp = await _force_cancel(admin_client, edition_id, reg_id)
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    remaining = (
        await db_session.execute(
            select(AttendanceRecord).where(AttendanceRecord.user_id == user_id)
        )
    ).scalars().all()
    assert remaining == []


@pytest.mark.asyncio
async def test_force_cancel_without_attendance_is_noop(admin_client: AsyncClient, db_session: AsyncSession):
    edition_id = uuid.uuid4()
    reg = await _make_event_reg(db_session, edition_id, uuid.uuid4(), None)
    await db_session.commit()

    resp = await _force_cancel(admin_client, edition_id, reg.id)
    assert resp.status_code == 200, resp.text


async def _participant_user_id(db_session):
    from app.models.user import User

    return (
        await db_session.execute(
            select(User.id).where(User.email == "participant@parallax.local")
        )
    ).scalar_one()


async def _make_order_for(db_session, edition_id, user_id, status):
    from app.models.commerce import PaymentOrder

    order = PaymentOrder(
        edition_id=edition_id,
        user_id=user_id,
        purpose="pass",
        amount_paise=50000,
        status=status,
        gateway_order_id=f"order_{uuid.uuid4().hex[:10]}",
        paid_at=datetime.now(UTC) if status in ("paid", "refunded") else None,
    )
    db_session.add(order)
    await db_session.flush()
    return order


async def _verify(participant_client, edition_id, order_id):
    return await participant_client.post(
        f"/api/v1/editions/{edition_id}/payments/verify",
        json={
            "orderId": str(order_id),
            "razorpayPaymentId": "pay_dummy_123456",
            "razorpaySignature": "sig_dummy_1234567890",
        },
    )


@pytest.mark.asyncio
async def test_verify_paid_order_unchanged(participant_client: AsyncClient, db_session: AsyncSession):
    edition_id = uuid.uuid4()
    uid = await _participant_user_id(db_session)
    order = await _make_order_for(db_session, edition_id, uid, "paid")
    await db_session.commit()
    resp = await _verify(participant_client, edition_id, order.id)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["paid"] is True


@pytest.mark.asyncio
async def test_verify_refunded_order_rejected(participant_client: AsyncClient, db_session: AsyncSession):
    edition_id = uuid.uuid4()
    uid = await _participant_user_id(db_session)
    order = await _make_order_for(db_session, edition_id, uid, "refunded")
    await db_session.commit()
    resp = await _verify(participant_client, edition_id, order.id)
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_verify_failed_order_rejected(participant_client: AsyncClient, db_session: AsyncSession):
    edition_id = uuid.uuid4()
    uid = await _participant_user_id(db_session)
    order = await _make_order_for(db_session, edition_id, uid, "failed")
    await db_session.commit()
    resp = await _verify(participant_client, edition_id, order.id)
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_verify_created_order_unchanged(participant_client: AsyncClient, db_session: AsyncSession):
    edition_id = uuid.uuid4()
    uid = await _participant_user_id(db_session)
    order = await _make_order_for(db_session, edition_id, uid, "created")
    await db_session.commit()
    resp = await _verify(participant_client, edition_id, order.id)
    # Dev/test mock mode: created order still confirms (unchanged behaviour).
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["paid"] is True


@pytest.mark.asyncio
async def test_verify_payments_on_bad_signature_rejected(
    participant_client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    from types import SimpleNamespace

    monkeypatch.setattr(
        "app.api.v1.participant.get_settings",
        lambda: SimpleNamespace(payments_enabled=True, mock_payments_available=False),
    )
    monkeypatch.setattr(
        "app.services.payments.verify_checkout_signature", lambda *a, **k: False
    )
    edition_id = uuid.uuid4()
    uid = await _participant_user_id(db_session)
    order = await _make_order_for(db_session, edition_id, uid, "created")
    await db_session.commit()

    resp = await _verify(participant_client, edition_id, order.id)
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "PAYMENT_SIGNATURE_INVALID"


@pytest.mark.asyncio
async def test_verify_payments_off_prod_like_rejected(
    participant_client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    from types import SimpleNamespace

    monkeypatch.setattr(
        "app.api.v1.participant.get_settings",
        lambda: SimpleNamespace(payments_enabled=False, mock_payments_available=False),
    )
    edition_id = uuid.uuid4()
    uid = await _participant_user_id(db_session)
    order = await _make_order_for(db_session, edition_id, uid, "created")
    await db_session.commit()
    order_id = order.id

    resp = await _verify(participant_client, edition_id, order_id)
    assert resp.status_code == 422, resp.text
    db_session.expire_all()
    from app.models.commerce import PaymentOrder

    stored = await db_session.get(PaymentOrder, order_id)
    assert stored.status == "created"


@pytest.mark.asyncio
async def test_verify_payments_off_dev_mock_still_works(
    participant_client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    from types import SimpleNamespace

    monkeypatch.setattr(
        "app.api.v1.participant.get_settings",
        lambda: SimpleNamespace(payments_enabled=False, mock_payments_available=True),
    )
    edition_id = uuid.uuid4()
    uid = await _participant_user_id(db_session)
    order = await _make_order_for(db_session, edition_id, uid, "created")
    await db_session.commit()

    resp = await _verify(participant_client, edition_id, order.id)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["paid"] is True
