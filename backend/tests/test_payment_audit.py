"""PAY-002: refunds must be backed by a captured transaction and a gateway id."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ValidationFailed
from app.models.commerce import ConventionPass, PaymentOrder, PaymentTransaction, Refund
from app.services import payments
from sqlalchemy import func, select


def _order(amount: int = 50000) -> PaymentOrder:
    return PaymentOrder(
        edition_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        purpose="pass",
        amount_paise=amount,
        status="paid",
        gateway_order_id=f"order_{uuid.uuid4().hex[:10]}",
        paid_at=datetime.now(UTC),
    )


def _transaction(order: PaymentOrder, amount: int | None = None) -> PaymentTransaction:
    return PaymentTransaction(
        order_id=order.id,
        gateway_payment_id=f"pay_{uuid.uuid4().hex[:10]}",
        amount_paise=amount if amount is not None else order.amount_paise,
        status="captured",
    )


@pytest.mark.asyncio
async def test_refund_without_captured_transaction_is_refused(db_session: AsyncSession):
    order = _order()
    db_session.add(order)
    await db_session.flush()

    with pytest.raises(ValidationFailed):
        await payments.refund_order(db_session, order, 10000, "requested_by_attendee")

    assert order.status == "paid"
    refunds = list(
        (
            await db_session.execute(
                select(Refund).where(Refund.order_id == order.id)
            )
        ).scalars()
    )
    assert refunds == []


@pytest.mark.asyncio
async def test_refund_gateway_failure_changes_nothing(db_session: AsyncSession):
    order = _order()
    db_session.add(order)
    await db_session.flush()
    db_session.add(_transaction(order))
    await db_session.flush()

    with patch(
        "app.services.payments._gateway_refund_sync",
        side_effect=RuntimeError("gateway down"),
    ):
        with pytest.raises(AppError) as exc:
            await payments.refund_order(db_session, order, 50000, "requested_by_attendee")
    assert exc.value.status_code == 502
    assert order.status == "paid"
    refunds = list(
        (
            await db_session.execute(
                select(Refund).where(Refund.order_id == order.id)
            )
        ).scalars()
    )
    assert refunds == []


@pytest.mark.asyncio
async def test_refund_requires_a_gateway_id(db_session: AsyncSession):
    order = _order()
    db_session.add(order)
    await db_session.flush()
    db_session.add(_transaction(order))
    await db_session.flush()

    with patch("app.services.payments._gateway_refund_sync", return_value=None):
        with pytest.raises(AppError) as exc:
            await payments.refund_order(db_session, order, 50000, "requested_by_attendee")
    assert exc.value.status_code == 502
    assert order.status == "paid"


@pytest.mark.asyncio
async def test_expire_unpaid_orders_and_reservations(db_session: AsyncSession):
    from datetime import timedelta

    from app.models.commerce import Registration

    stale_order = PaymentOrder(
        edition_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        purpose="college_registration",
        amount_paise=10000,
        status="created",
    )
    db_session.add(stale_order)
    await db_session.flush()
    stale_order.created_at = datetime.now(UTC) - timedelta(hours=3)

    fresh_order = PaymentOrder(
        edition_id=stale_order.edition_id,
        user_id=stale_order.user_id,
        purpose="pass",
        amount_paise=10000,
        status="created",
    )
    db_session.add(fresh_order)
    await db_session.flush()

    reserved = Registration(
        edition_id=stale_order.edition_id,
        event_id=uuid.uuid4(),
        user_id=stale_order.user_id,
        kind="addon",
        fee_paise=10000,
        status="reserved",
        registration_number=f"PX-{uuid.uuid4().hex[:6].upper()}",
        reservation_expires_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db_session.add(reserved)
    await db_session.flush()

    expired = await payments.expire_unpaid(db_session)
    await db_session.flush()

    assert expired >= 2
    assert stale_order.status == "expired"
    assert fresh_order.status == "created"
    assert reserved.status == "cancelled"


@pytest.mark.asyncio
async def test_mark_order_paid_is_idempotent(db_session: AsyncSession):
    order = PaymentOrder(
        edition_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        purpose="pass",
        amount_paise=50000,
        status="created",
        gateway_order_id=f"order_{uuid.uuid4().hex[:10]}",
    )
    db_session.add(order)
    await db_session.flush()
    # A historic purpose="pass" order is no longer fulfilled: no entitlement is
    # activated, the money is parked for finance. The idempotency guarantee (one
    # transaction row, one refund request, paid exactly once) still holds.
    await payments.mark_order_paid(db_session, order, transaction_id="pay_dup_1")
    await db_session.flush()
    await payments.mark_order_paid(db_session, order, transaction_id="pay_dup_1")
    await db_session.flush()

    count = await db_session.scalar(
        select(func.count())
        .select_from(PaymentTransaction)
        .where(PaymentTransaction.gateway_payment_id == "pay_dup_1")
    )
    assert count == 1
    assert order.status == "paid"
    parked = list(
        (
            await db_session.execute(select(Refund).where(Refund.order_id == order.id))
        ).scalars()
    )
    assert len(parked) == 1
    assert parked[0].status == "pending"
    assert parked[0].amount_paise == order.amount_paise


@pytest.mark.asyncio
async def test_full_refund_marks_processed_after_gateway_id(db_session: AsyncSession):
    order = _order()
    db_session.add(order)
    await db_session.flush()
    db_session.add(_transaction(order))
    await db_session.flush()

    with patch("app.services.payments._gateway_refund_sync", return_value="rfnd_abc"):
        refund = await payments.refund_order(
            db_session, order, 50000, "requested_by_attendee"
        )

    assert refund.status == "processed"
    assert refund.gateway_refund_id == "rfnd_abc"
    assert order.status == "refunded"


@pytest.mark.asyncio
async def test_partial_refund_keeps_order_paid(db_session: AsyncSession):
    order = _order()
    db_session.add(order)
    await db_session.flush()
    db_session.add(_transaction(order))
    await db_session.flush()

    with patch("app.services.payments._gateway_refund_sync", return_value="rfnd_partial"):
        refund = await payments.refund_order(
            db_session, order, 20000, "requested_by_attendee"
        )

    assert refund.status == "processed"
    assert refund.amount_paise == 20000
    assert order.status == "paid"
