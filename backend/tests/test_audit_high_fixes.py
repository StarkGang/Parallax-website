"""Tests for the audit HIGH fixes (approve import, ticket revoke, refund amount, etc.)."""

import uuid
from datetime import UTC, datetime, timedelta

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


@pytest.mark.asyncio
async def test_refund_order_second_over_cap_rejected(db_session: AsyncSession):
    """Sequential double refund: a second refund beyond the remaining cap is rejected.

    Concurrency is not runtime-tested (SQLite ignores SELECT ... FOR UPDATE).
    """
    from app.core.errors import ValidationFailed
    from app.models.commerce import PaymentOrder, PaymentTransaction
    from app.services.payments import refund_order

    edition_id = uuid.uuid4()
    user_id = uuid.uuid4()
    order = PaymentOrder(
        edition_id=edition_id,
        user_id=user_id,
        purpose="pass",
        amount_paise=50000,
        status="paid",
        gateway_order_id=f"order_{uuid.uuid4().hex[:10]}",
        paid_at=datetime.now(UTC),
    )
    db_session.add(order)
    await db_session.flush()
    db_session.add(
        PaymentTransaction(
            order_id=order.id,
            gateway_payment_id="pay_x",
            amount_paise=50000,
            status="captured",
        )
    )
    await db_session.commit()

    first = await refund_order(db_session, order, 30000, reason_code="test")
    assert first.amount_paise == 30000
    await db_session.commit()

    with pytest.raises(ValidationFailed):
        await refund_order(db_session, order, 30000, reason_code="test")


# --- Round 2: shared-order expiry helper across all three paths -------------

async def _make_edition(db_session):
    from app.models.edition import ConventionEdition

    ed = ConventionEdition(
        slug=f"ed-{uuid.uuid4().hex[:8]}",
        name="Test Edition",
        organizer="Org",
        host="Host",
        venue="Venue",
        city="City",
        starts_at=datetime.now(UTC),
        ends_at=datetime.now(UTC),
    )
    db_session.add(ed)
    await db_session.flush()
    return ed


async def _make_team_order(db_session, edition_id, order_id):
    from app.models.commerce import Team

    team = Team(
        edition_id=edition_id,
        event_id=uuid.uuid4(),
        name="Team A",
        leader_id=uuid.uuid4(),
        invite_code="CODE1234",
        invite_code_hash="hash",
        order_id=order_id,
    )
    db_session.add(team)
    await db_session.flush()
    return team


@pytest.mark.asyncio
async def test_cancel_registration_solo_expires_order(db_session: AsyncSession):
    from app.models.commerce import PaymentOrder
    from app.services.registrations import cancel_registration

    edition_id = uuid.uuid4()
    user_id = uuid.uuid4()
    order = await _make_order(db_session, edition_id, user_id, "created")
    reg = await _make_event_reg(db_session, edition_id, user_id, order.id, status="reserved")
    await db_session.commit()
    order_id, reg_id = order.id, reg.id

    await cancel_registration(db_session, None, user_id, reg_id)
    db_session.expire_all()
    assert (await db_session.get(PaymentOrder, order_id)).status == "expired"


@pytest.mark.asyncio
async def test_cancel_registration_shared_keeps_order(db_session: AsyncSession):
    from app.models.commerce import PaymentOrder
    from app.services.registrations import cancel_registration

    edition_id = uuid.uuid4()
    user_id = uuid.uuid4()
    order = await _make_order(db_session, edition_id, user_id, "created")
    reg1 = await _make_event_reg(db_session, edition_id, user_id, order.id, status="reserved")
    await _make_event_reg(db_session, edition_id, user_id, order.id, status="reserved")
    await db_session.commit()
    order_id, reg1_id = order.id, reg1.id

    await cancel_registration(db_session, None, user_id, reg1_id)
    db_session.expire_all()
    assert (await db_session.get(PaymentOrder, order_id)).status == "created"


@pytest.mark.asyncio
async def test_cancel_registration_team_order_kept(db_session: AsyncSession):
    from app.models.commerce import PaymentOrder
    from app.services.registrations import cancel_registration

    edition_id = uuid.uuid4()
    user_id = uuid.uuid4()
    order = await _make_order(db_session, edition_id, user_id, "created")
    reg = await _make_event_reg(db_session, edition_id, user_id, order.id, status="reserved")
    await _make_team_order(db_session, edition_id, order.id)
    await db_session.commit()
    order_id, reg_id = order.id, reg.id

    await cancel_registration(db_session, None, user_id, reg_id)
    db_session.expire_all()
    assert (await db_session.get(PaymentOrder, order_id)).status == "created"


@pytest.mark.asyncio
async def test_remove_seat_solo_expires_order(db_session: AsyncSession):
    from app.models.commerce import PaymentOrder
    from app.services.pricing import remove_seat

    edition = await _make_edition(db_session)
    user_id = uuid.uuid4()
    event_id = uuid.uuid4()
    order = await _make_order(db_session, edition.id, user_id, "created")
    reg = await _make_event_reg(db_session, edition.id, user_id, order.id, status="reserved")
    reg.event_id = event_id
    await db_session.commit()
    order_id = order.id

    await remove_seat(
        db_session, request=None, user_id=user_id, edition=edition, event_id=event_id
    )
    db_session.expire_all()
    assert (await db_session.get(PaymentOrder, order_id)).status == "expired"


@pytest.mark.asyncio
async def test_remove_seat_shared_keeps_order(db_session: AsyncSession):
    from app.models.commerce import PaymentOrder
    from app.services.pricing import remove_seat

    edition = await _make_edition(db_session)
    user_id = uuid.uuid4()
    event1, event2 = uuid.uuid4(), uuid.uuid4()
    order = await _make_order(db_session, edition.id, user_id, "created")
    r1 = await _make_event_reg(db_session, edition.id, user_id, order.id, status="reserved")
    r1.event_id = event1
    r2 = await _make_event_reg(db_session, edition.id, user_id, order.id, status="reserved")
    r2.event_id = event2
    await db_session.commit()
    order_id = order.id

    await remove_seat(
        db_session, request=None, user_id=user_id, edition=edition, event_id=event1
    )
    db_session.expire_all()
    assert (await db_session.get(PaymentOrder, order_id)).status == "created"


@pytest.mark.asyncio
async def test_force_cancel_team_order_kept(admin_client: AsyncClient, db_session: AsyncSession):
    from app.models.commerce import PaymentOrder

    edition_id = uuid.uuid4()
    user_id = uuid.uuid4()
    order = await _make_order(db_session, edition_id, user_id, "created")
    reg = await _make_event_reg(db_session, edition_id, user_id, order.id)
    await _make_team_order(db_session, edition_id, order.id)
    await db_session.commit()
    reg_id, order_id = reg.id, order.id

    resp = await _force_cancel(admin_client, edition_id, reg_id)
    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    assert (await db_session.get(PaymentOrder, order_id)).status == "created"


@pytest.mark.asyncio
async def test_verify_expired_order_revives_in_dev(participant_client: AsyncClient, db_session: AsyncSession):
    edition_id = uuid.uuid4()
    uid = await _participant_user_id(db_session)
    order = await _make_order_for(db_session, edition_id, uid, "expired")
    await db_session.commit()
    order_id = order.id

    resp = await _verify(participant_client, edition_id, order_id)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["paid"] is True
    db_session.expire_all()
    from app.models.commerce import PaymentOrder

    assert (await db_session.get(PaymentOrder, order_id)).status == "paid"


@pytest.mark.asyncio
async def test_verify_expired_order_bad_signature_stays_expired(
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
    order = await _make_order_for(db_session, edition_id, uid, "expired")
    await db_session.commit()
    order_id = order.id

    resp = await _verify(participant_client, edition_id, order_id)
    assert resp.status_code == 400, resp.text
    db_session.expire_all()
    from app.models.commerce import PaymentOrder

    assert (await db_session.get(PaymentOrder, order_id)).status == "expired"


# --- F5 D-2: expire_unpaid must not expire captured orders ------------------

async def _make_stale_order(db_session, edition_id, user_id, gateway_order_id=None):
    from app.models.commerce import PaymentOrder

    order = PaymentOrder(
        edition_id=edition_id,
        user_id=user_id,
        purpose="pass",
        amount_paise=50000,
        status="created",
        gateway_order_id=gateway_order_id or f"order_{uuid.uuid4().hex[:12]}",
        created_at=datetime.now(UTC) - timedelta(days=1),
    )
    db_session.add(order)
    await db_session.flush()
    return order


@pytest.mark.asyncio
async def test_expire_unpaid_captured_flagged_for_finance(db_session, monkeypatch):
    from types import SimpleNamespace

    from app.models.commerce import PaymentOrder
    from app.services.payments import expire_unpaid

    monkeypatch.setattr(
        "app.services.payments.get_settings",
        lambda: SimpleNamespace(payments_enabled=True, unpaid_order_ttl_minutes=30),
    )

    async def _fake_fetch(_gid):
        return {"status": "paid"}

    monkeypatch.setattr("app.services.payments.fetch_gateway_order", _fake_fetch)

    order = await _make_stale_order(db_session, uuid.uuid4(), uuid.uuid4())
    await db_session.commit()
    order_id = order.id

    await expire_unpaid(db_session)
    db_session.expire_all()
    stored = await db_session.get(PaymentOrder, order_id)
    assert stored.status == "needs_reconciliation"
    assert (stored.notes or {}).get("needsReconciliation") is True


@pytest.mark.asyncio
async def test_expire_unpaid_captures_unpaid_expired(db_session, monkeypatch):
    from types import SimpleNamespace

    from app.models.commerce import PaymentOrder
    from app.services.payments import expire_unpaid

    monkeypatch.setattr(
        "app.services.payments.get_settings",
        lambda: SimpleNamespace(payments_enabled=True, unpaid_order_ttl_minutes=30),
    )

    async def _fake_fetch(_gid):
        return {"status": "created"}

    monkeypatch.setattr("app.services.payments.fetch_gateway_order", _fake_fetch)

    order = await _make_stale_order(db_session, uuid.uuid4(), uuid.uuid4())
    await db_session.commit()
    order_id = order.id

    await expire_unpaid(db_session)
    db_session.expire_all()
    assert (await db_session.get(PaymentOrder, order_id)).status == "expired"


@pytest.mark.asyncio
async def test_expire_unpaid_gateway_error_keeps_order(db_session, monkeypatch):
    from types import SimpleNamespace

    from app.models.commerce import PaymentOrder
    from app.services.payments import expire_unpaid

    monkeypatch.setattr(
        "app.services.payments.get_settings",
        lambda: SimpleNamespace(payments_enabled=True, unpaid_order_ttl_minutes=30),
    )

    async def _boom(_gid):
        raise RuntimeError("gateway down")

    monkeypatch.setattr("app.services.payments.fetch_gateway_order", _boom)

    order = await _make_stale_order(db_session, uuid.uuid4(), uuid.uuid4())
    await db_session.commit()
    order_id = order.id

    await expire_unpaid(db_session)
    db_session.expire_all()
    assert (await db_session.get(PaymentOrder, order_id)).status == "created"


@pytest.mark.asyncio
async def test_expire_unpaid_payments_disabled_expires(db_session, monkeypatch):
    from types import SimpleNamespace

    from app.models.commerce import PaymentOrder
    from app.services.payments import expire_unpaid

    monkeypatch.setattr(
        "app.services.payments.get_settings",
        lambda: SimpleNamespace(payments_enabled=False, unpaid_order_ttl_minutes=30),
    )

    order = await _make_stale_order(db_session, uuid.uuid4(), uuid.uuid4())
    await db_session.commit()
    order_id = order.id

    await expire_unpaid(db_session)
    db_session.expire_all()
    assert (await db_session.get(PaymentOrder, order_id)).status == "expired"
