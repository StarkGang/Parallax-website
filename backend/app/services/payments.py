"""Payments: Razorpay order generation, webhooks, mock payment in dev and refunds."""

import asyncio
import base64
import hmac
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_delete_pattern
from app.core.config import get_settings
from app.core.errors import AppError, NotFound, ValidationFailed
from app.core.logging import get_logger
from app.models.edition import Event
from app.models.commerce import (
    ConventionPass,
    PaymentOrder,
    PaymentTransaction,
    PaymentWebhookEvent,
    Refund,
    Registration,
)
from app.services.tickets import (
    issue_for_registration,
    revoke_for_pass,
    revoke_for_registration,
)

logger = get_logger("payments")

# Bound how long a checkout click can wait on the payment provider. A stalled
# gateway must fail fast instead of leaving the browser without feedback.
GATEWAY_TIMEOUT = httpx.Timeout(8.0, connect=4.0, read=6.0)


def _auth_header() -> dict[str, str]:
    settings = get_settings()
    key = settings.razorpay_key_id
    secret = settings.razorpay_key_secret
    creds = f"{key}:{secret}".encode()
    b64 = base64.b64encode(creds).decode()
    return {"Authorization": f"Basic {b64}"}


async def create_gateway_order(order: PaymentOrder) -> str | None:
    settings = get_settings()
    if not settings.payments_enabled:
        if settings.is_development:
            return f"mock_order_{order.id.hex[:12]}"
        raise AppError(
            "Online payments are not configured.",
            code="PAYMENTS_NOT_CONFIGURED",
            status_code=503,
        )
    async with httpx.AsyncClient(timeout=GATEWAY_TIMEOUT) as client:
        resp = await client.post(
            "https://api.razorpay.com/v1/orders",
            headers=_auth_header(),
            json={
                "amount": order.amount_paise,
                "currency": "INR",
                "receipt": str(order.id),
                "payment_capture": 1,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["id"]


def calculate_platform_fee(subtotal_paise: int, policy: Any | None) -> tuple[int, int]:
    """Return ``(platform_fee_paise, total_paise)`` for a given subtotal.

    When ``platform_fee_bps`` is 0, returns ``(0, subtotal)``. When
    ``platform_fee_exempt_under_paise`` > 0 and ``subtotal < exempt_under``,
    the fee is waived. When ``exempt_under`` == 0 and ``bps > 0``, the fee
    applies to every positive transaction.
    """
    subtotal = max(0, int(subtotal_paise or 0))
    if subtotal <= 0 or policy is None:
        return 0, subtotal
    bps = int(getattr(policy, "platform_fee_bps", 0) or 0)
    exempt_under = int(getattr(policy, "platform_fee_exempt_under_paise", 0) or 0)
    if bps <= 0 or (exempt_under > 0 and subtotal < exempt_under):
        return 0, subtotal
    fee = round(subtotal * bps / 10_000)
    return fee, subtotal + fee


async def attach_gateway_order(db: AsyncSession, order: PaymentOrder) -> PaymentOrder:
    """Create the provider order exactly once so checkout can actually open."""
    settings = get_settings()
    if order.gateway_order_id:
        if settings.payments_enabled and order.gateway_order_id.startswith("mock_order_"):
            order.gateway_order_id = None
        elif settings.payments_enabled and not order.gateway_order_id.startswith("mock_order_"):
            # Check with Razorpay whether this order was already captured/paid, or if it expired
            try:
                async with httpx.AsyncClient(timeout=GATEWAY_TIMEOUT) as client:
                    resp = await client.get(
                        f"https://api.razorpay.com/v1/orders/{order.gateway_order_id}",
                        headers=_auth_header(),
                    )
                    if resp.status_code == 200:
                        order_info = resp.json()
                        if order_info.get("status") == "paid":
                            # Order was already paid in Razorpay! Fetch payment ID and mark paid.
                            payments_resp = await client.get(
                                f"https://api.razorpay.com/v1/orders/{order.gateway_order_id}/payments",
                                headers=_auth_header(),
                            )
                            tx_id = None
                            if payments_resp.status_code == 200:
                                for item in payments_resp.json().get("items", []):
                                    if item.get("status") == "captured":
                                        tx_id = item.get("id")
                                        break
                            await mark_order_paid(db, order, transaction_id=tx_id)
                            return order
                        elif order_info.get("status") not in {"created", "attempted"}:
                            order.gateway_order_id = None
            except Exception as e:
                logger.warning("Failed checking gateway order %s: %s", order.gateway_order_id, e)
                return order
        else:
            return order
    try:
        order.gateway_order_id = await create_gateway_order(order)
        order.status = "created"
        await db.flush()
        try:
            from app.services.telegram import dispatch_payment_telegram_alert
            from app.models.user import User

            user = await db.get(User, order.user_id) if order.user_id else None
            dispatch_payment_telegram_alert(
                "initiated",
                order_id=str(order.id),
                amount_paise=order.amount_paise,
                purpose=order.purpose,
                gateway_order_id=order.gateway_order_id,
                attendee_name=user.full_name if user else None,
                attendee_email=user.email if user else None,
            )
        except Exception:
            pass
    except Exception as exc:  # pragma: no cover - provider failure path
        logger.warning("Gateway order creation failed for %s: %s", order.id, exc)
        try:
            from app.services.telegram import file_telegram_alert

            file_telegram_alert(
                "Payment gateway order failed",
                {
                    "Order": str(order.id),
                    "Amount": f"INR {order.amount_paise / 100:.2f}",
                    "Purpose": order.purpose,
                    "Error": str(exc)[:300],
                },
                severity="critical",
            )
        except Exception:  # pragma: no cover
            pass
        order.status = "failed"
        await db.flush()
        raise AppError(
            "Could not start the payment. Please try again.",
            code="PAYMENT_GATEWAY_ERROR",
            status_code=502,
        ) from exc
    return order


async def gateway_refund(payment_id: str, amount_paise: int) -> str | None:
    settings = get_settings()
    if not settings.payments_enabled:
        if settings.is_development:
            return f"mock_rfnd_{uuid.uuid4().hex[:12]}"
        raise AppError(
            "Refunds are not configured with a payment gateway.",
            code="PAYMENTS_NOT_CONFIGURED",
            status_code=503,
        )
    async with httpx.AsyncClient(timeout=GATEWAY_TIMEOUT) as client:
        resp = await client.post(
            f"https://api.razorpay.com/v1/payments/{payment_id}/refund",
            headers=_auth_header(),
            json={"amount": amount_paise},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["id"]


def _gateway_refund_sync(payment_id: str, amount_paise: int) -> str | None:
    """Blocking Razorpay refund call, executed in a worker thread.

    The refund path used to await an async HTTP call on the request loop for a
    blocking-style financial operation; running it in a thread keeps the loop
    responsive while still reporting the gateway result before anything is
    recorded as refunded.
    """
    settings = get_settings()
    if not settings.payments_enabled:
        if settings.is_development:
            return f"mock_rfnd_{uuid.uuid4().hex[:12]}"
        raise AppError(
            "Refunds are not configured with a payment gateway.",
            code="PAYMENTS_NOT_CONFIGURED",
            status_code=503,
        )
    with httpx.Client(timeout=GATEWAY_TIMEOUT) as client:
        resp = client.post(
            f"https://api.razorpay.com/v1/payments/{payment_id}/refund",
            headers=_auth_header(),
            json={"amount": amount_paise},
        )
        resp.raise_for_status()
        return resp.json().get("id")


async def create_order(
    db: AsyncSession,
    user_id: uuid.UUID,
    edition_id: uuid.UUID,
    purpose: str,
    amount_paise: int,
    linked_record_id: uuid.UUID | None = None,
) -> PaymentOrder:
    order = PaymentOrder(
        edition_id=edition_id,
        user_id=user_id,
        purpose=purpose,
        amount_paise=amount_paise,
        status="created",
        linked_record_id=linked_record_id,
    )
    db.add(order)
    await db.flush()

    try:
        gateway_id = await create_gateway_order(order)
        order.gateway_order_id = gateway_id
        await db.flush()
    except Exception as exc:
        logger.warning("Gateway order creation failed for %s: %s", order.id, exc)
        if get_settings().payments_enabled:
            raise AppError(
                "Could not initialize payment with Razorpay. Please try again or contact support.",
                code="PAYMENT_GATEWAY_ERROR",
                status_code=502,
            ) from exc
    return order


async def mark_order_paid(
    db: AsyncSession, order: PaymentOrder, transaction_id: str | None = None
) -> None:
    """Fulfil an order exactly once, even under concurrent callers.

    The Razorpay webhook and the browser's verify call can land at the same
    time. The row lock serialises them and the transaction insert ignores the
    duplicate payment id, so the second caller sees "paid" and returns instead
    of raising a unique-constraint 500 after the customer already paid.
    """
    locked = (
        await db.execute(
            select(PaymentOrder).where(PaymentOrder.id == order.id).with_for_update()
        )
    ).scalar_one_or_none()
    if locked is None:
        raise NotFound("Payment order not found.")
    order = locked
    if order.status in ("paid", "refunded"):
        return
    order.status = "paid"
    order.paid_at = datetime.now(UTC)

    payment_ref = transaction_id or f"pay_{order.id.hex[:16]}"
    dialect = db.bind.dialect.name if db.bind is not None else "postgresql"
    insert_stmt = sqlite_insert if dialect == "sqlite" else pg_insert
    await db.execute(
        insert_stmt(PaymentTransaction)
        .values(
            order_id=order.id,
            gateway_payment_id=payment_ref,
            status="captured",
            amount_paise=order.amount_paise,
        )
        .on_conflict_do_nothing(index_elements=["gateway_payment_id"])
    )
    tx = (
        await db.execute(
            select(PaymentTransaction).where(
                PaymentTransaction.gateway_payment_id == payment_ref
            )
        )
    ).scalar_one()

    if order.purpose == "pass":
        # Legacy rows only: the pass is sold as a college_registration order and
        # nothing writes purpose="pass" any more. Paying one used to activate a
        # pass with no refund path, so any money on such a row is parked for
        # finance instead of buying an entitlement nobody approved.
        logger.warning("legacy_pass_order_paid order=%s user=%s", order.id, order.user_id)
        already_committed = (
            (
                await db.execute(
                    select(func.coalesce(func.sum(Refund.amount_paise), 0)).where(
                        Refund.order_id == order.id,
                        Refund.status.in_(("pending", "processing", "processed")),
                    )
                )
            )
            .scalars()
            .one()
        ) or 0
        available = max(0, int(order.amount_paise) - int(already_committed))
        if available > 0:
            db.add(
                Refund(
                    order_id=order.id,
                    amount_paise=available,
                    reason_code="legacy_order",
                    reason_note="Payment on a retired pass order; no entitlement issued.",
                    status="pending",
                )
            )

    elif order.purpose == "registration":
        regs = list(
            (
                await db.execute(
                    select(Registration).where(Registration.order_id == order.id)
                )
            ).scalars()
        )
        # A pending add-on order paid after the pass was rejected/refunded
        # must not re-confirm registrations that were cancelled with the pass.
        from app.services.passes import pass_gate_blocked

        blocked = await pass_gate_blocked(db, order.user_id, order.edition_id)
        stranded_paise = 0
        for r in regs:
            # One team order can carry several seats. A blocked payer must not
            # drag the whole roster down, and a blocked rider must not be
            # confirmed on somebody else's payment, so the gate is per seat.
            row_blocked = (
                blocked
                if r.user_id == order.user_id
                else await pass_gate_blocked(db, r.user_id, order.edition_id)
            )
            if row_blocked:
                logger.warning(
                    "addon_payment_on_blocked_pass order=%s reg=%s reason=%s",
                    order.id,
                    r.id,
                    row_blocked,
                )
                if r.status != "cancelled":
                    r.status = "cancelled"
                    r.cancelled_at = datetime.now(UTC)
                    r.cancelled_by = "admin"
                    r.cancellation_reason = row_blocked
                if r.fee_paise > 0:
                    stranded_paise += int(r.fee_paise)
                continue
            # Only a live hold may be confirmed. Cancelled rows belong to a
            # booking that the attendee, the hold sweep or a newer booking
            # replaced; reviving them produced duplicate seats and duplicate
            # tickets while a second order was paid too. The money for those
            # rows is queued for a refund instead of vanishing.
            # Capacity can be consumed between the hold and the payment (a
            # second path, or another booking for the last place). Confirming
            # blindly produced an over-capacity seat the door then had to
            # referee; the seat is refused and the money is queued instead.
            if r.status == "reserved":
                seat_event = await db.get(Event, r.event_id)
                if seat_event is not None and seat_event.capacity:
                    from app.services.events import capacity_usage

                    used = (await capacity_usage(db, [seat_event])).get(seat_event.id, 0)
                    if used > int(seat_event.capacity):
                        r.status = "cancelled"
                        r.cancelled_at = datetime.now(UTC)
                        r.cancelled_by = "capacity"
                        r.cancellation_reason = "The event filled up before this payment arrived."
                        if r.fee_paise > 0:
                            stranded_paise += int(r.fee_paise)
                        logger.warning(
                            "addon_payment_over_capacity order=%s reg=%s used=%s capacity=%s",
                            order.id,
                            r.id,
                            used,
                            seat_event.capacity,
                        )
                        continue
            if r.status != "reserved" or r.cancelled_at is not None:
                logger.warning(
                    "addon_payment_not_revived order=%s reg=%s status=%s",
                    order.id,
                    r.id,
                    r.status,
                )
                if r.status == "cancelled" and r.fee_paise > 0:
                    stranded_paise += int(r.fee_paise)
                continue
            seat_event = await db.get(Event, r.event_id)
            if seat_event and seat_event.requires_approval:
                r.status = "pending"
            else:
                r.status = "confirmed"
                await issue_for_registration(db, r)
        if stranded_paise > 0:
            already_committed = (
                (
                    await db.execute(
                        select(func.coalesce(func.sum(Refund.amount_paise), 0)).where(
                            Refund.order_id == order.id,
                            Refund.status.in_(("pending", "processing", "processed")),
                        )
                    )
                )
                .scalars()
                .one()
            ) or 0
            available = max(0, int(order.amount_paise) - int(already_committed))
            refund_amt = min(int(stranded_paise), available)
            if refund_amt > 0:
                db.add(
                    Refund(
                        order_id=order.id,
                        amount_paise=refund_amt,
                        reason_code="booking_cancelled",
                        reason_note="Paid for a booking that was already cancelled or replaced",
                        status="pending",
                    )
                )

    elif order.purpose == "college_registration":
        from app.services.college_registrations import finalize_paid

        await finalize_paid(db, order, transaction_id=transaction_id)

    elif order.purpose == "college_registration_delta":
        from app.services.college_registrations import apply_paid_category_change

        await apply_paid_category_change(db, order)

    elif order.purpose == "included_selection_delta":
        from app.services.passes import apply_paid_selection_delta

        await apply_paid_selection_delta(db, order)

    await db.flush()
    try:
        from app.services.telegram import dispatch_payment_telegram_alert
        from app.models.user import User

        user = await db.get(User, order.user_id) if order.user_id else None
        dispatch_payment_telegram_alert(
            "success",
            order_id=str(order.id),
            amount_paise=order.amount_paise,
            purpose=order.purpose,
            payment_id=tx.gateway_payment_id,
            gateway_order_id=order.gateway_order_id,
            attendee_name=user.full_name if user else None,
            attendee_email=user.email if user else None,
        )
    except Exception:
        pass
    cache_delete_pattern("public:*")
    cache_delete_pattern("admin:dashboard:*")


async def expire_unpaid(db: AsyncSession) -> int:
    """Expire abandoned checkouts and free the capacity they were holding.

    Nothing used to call this, so every abandoned Razorpay modal left a
    `created` order forever and reserved event seats never came back.
    """
    from app.services.registrations import expire_reservations

    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(minutes=settings.unpaid_order_ttl_minutes)
    stale = list(
        (
            await db.execute(
                select(PaymentOrder).where(
                    PaymentOrder.status == "created",
                    PaymentOrder.created_at < cutoff,
                )
            )
        ).scalars()
    )
    for order in stale:
        order.status = "expired"
    released = await expire_reservations(db)
    if stale:
        cache_delete_pattern("public:*")
        cache_delete_pattern("admin:dashboard:*")
        logger.info("unpaid_orders_expired", count=len(stale))
    return len(stale) + released


def verify_webhook_signature(body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_checkout_signature(
    gateway_order_id: str, payment_id: str, signature: str
) -> bool:
    """Razorpay checkout signature: HMAC-SHA256(order_id|payment_id, key_secret)."""
    settings = get_settings()
    if not settings.razorpay_key_secret or not gateway_order_id or not payment_id:
        return False
    expected = hmac.new(
        settings.razorpay_key_secret.encode(),
        f"{gateway_order_id}|{payment_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")


async def fetch_gateway_refund(refund_id: str) -> dict[str, Any]:
    """Read the authoritative refund status from Razorpay."""
    settings = get_settings()
    if not settings.payments_enabled:
        return {}
    async with httpx.AsyncClient(timeout=GATEWAY_TIMEOUT) as client:
        resp = await client.get(
            f"https://api.razorpay.com/v1/refunds/{refund_id}",
            headers=_auth_header(),
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_gateway_payment(payment_id: str) -> dict[str, Any]:
    """Read the authoritative payment from Razorpay before marking anything paid."""
    settings = get_settings()
    if not settings.payments_enabled:
        return {}
    async with httpx.AsyncClient(timeout=GATEWAY_TIMEOUT) as client:
        resp = await client.get(
            f"https://api.razorpay.com/v1/payments/{payment_id}",
            headers=_auth_header(),
        )
        resp.raise_for_status()
        return resp.json()


async def process_webhook(
    db: AsyncSession, event_payload: dict[str, Any], event_id: str
) -> None:
    existing = (
        await db.execute(
            select(PaymentWebhookEvent).where(
                PaymentWebhookEvent.gateway_event_id == event_id
            )
        )
    ).scalar_one_or_none()
    if existing:
        return

    entry = PaymentWebhookEvent(
        gateway_event_id=event_id,
        event_type=event_payload.get("event", "unknown"),
        signature_verified=True,
        payload_hash=hashlib.sha256(
            json.dumps(event_payload, sort_keys=True, default=str).encode()
        ).hexdigest(),
        processing_status="processed",
        received_at=datetime.now(UTC),
        processed_at=datetime.now(UTC),
    )
    db.add(entry)

    event_type = event_payload.get("event")
    if event_type in {"payment.captured", "payment.authorized", "order.paid"}:
        pay_entity = event_payload.get("payload", {}).get("payment", {}).get("entity", {})
        order_id = pay_entity.get("order_id")
        if not order_id:
            order_entity = event_payload.get("payload", {}).get("order", {}).get("entity", {})
            order_id = order_entity.get("id")
        if order_id:
            order = (
                await db.execute(
                    select(PaymentOrder).where(PaymentOrder.gateway_order_id == order_id)
                )
            ).scalar_one_or_none()
            if order:
                paid_amount = int(pay_entity.get("amount") or 0)
                if paid_amount and paid_amount != order.amount_paise:
                    # Never fulfil an order for an amount the server did not set.
                    # The money is still captured, so it has to appear in the
                    # ledger and alert finance; logging alone left the attendee
                    # paid-and-unregistered with nothing to follow up.
                    entry.processing_status = "failed"
                    entry.error = (
                        f"Amount mismatch: gateway {paid_amount} vs order {order.amount_paise}"
                    )
                    logger.error(
                        "payment_amount_mismatch",
                        order=str(order.id),
                        expected=order.amount_paise,
                        received=paid_amount,
                    )
                    existing = (
                        await db.execute(
                            select(Refund).where(
                                Refund.order_id == order.id,
                                Refund.status.in_(["pending", "processing", "processed"]),
                            )
                        )
                    ).scalars().first()
                    if existing is None and paid_amount > 0:
                        db.add(
                            Refund(
                                order_id=order.id,
                                amount_paise=paid_amount,
                                reason_code="amount_mismatch",
                                reason_note=(
                                    "Captured amount did not match the order "
                                    f"(gateway {paid_amount} vs order {order.amount_paise})"
                                )[:500],
                                status="pending",
                            )
                        )
                        try:
                            from app.services.telegram import dispatch_payment_telegram_alert

                            dispatch_payment_telegram_alert(
                                "failed",
                                order_id=str(order.id),
                                amount_paise=paid_amount,
                                purpose=order.purpose,
                                payment_id=pay_entity.get("id"),
                                gateway_order_id=order_id,
                                error_message="Amount mismatch — refund queued for finance",
                            )
                        except Exception:
                            pass
                else:
                    payment_id = pay_entity.get("id") or (
                        order_entity.get("payment_id") if "order_entity" in locals() else None
                    )
                    await mark_order_paid(db, order, transaction_id=payment_id)
    elif event_type == "payment.failed":
        # In Razorpay, an individual payment failure within an order does NOT fail the order.
        # The customer is allowed to retry with another card/UPI/method until the session expires.
        # Record the attempt failure for observability without corrupting the retryable order status.
        pay_entity = event_payload.get("payload", {}).get("payment", {}).get("entity", {})
        order_id = pay_entity.get("order_id")
        logger.info(
            "razorpay_payment_attempt_failed order_id=%s payment_id=%s error=%s",
            order_id,
            pay_entity.get("id"),
            pay_entity.get("error_description"),
        )
        try:
            from app.services.telegram import dispatch_payment_telegram_alert
            order = None
            if order_id:
                order = (
                    await db.execute(
                        select(PaymentOrder).where(PaymentOrder.gateway_order_id == order_id)
                    )
                ).scalar_one_or_none()
            dispatch_payment_telegram_alert(
                "failed",
                order_id=str(order.id) if order else (order_id or "unknown"),
                amount_paise=order.amount_paise if order else int(pay_entity.get("amount") or 0),
                purpose=order.purpose if order else "payment",
                payment_id=pay_entity.get("id"),
                gateway_order_id=order_id,
                error_message=pay_entity.get("error_description"),
            )
        except Exception:
            pass
    elif event_type in {"refund.processed", "refund.failed", "refund.created"}:
        refund_entity = event_payload.get("payload", {}).get("refund", {}).get("entity", {})
        gateway_refund_id = refund_entity.get("id")
        if gateway_refund_id:
            from app.services.college_registrations import sync_gateway_refund

            await sync_gateway_refund(
                db, gateway_refund_id, failed=event_type == "refund.failed"
            )

    await db.flush()


async def refund_order(
    db: AsyncSession,
    order: PaymentOrder,
    amount_paise: int,
    reason_code: str,
    reason_note: str | None = None,
    requested_by_id: uuid.UUID | None = None,
) -> Refund:
    if order.status != "paid":
        raise ValidationFailed("Only a paid order can be refunded.")
    if amount_paise <= 0:
        raise ValidationFailed("The refund amount must be greater than zero.")

    # The cap counts money that is committed or queued. Including "pending"
    # prevents the Finance form from opening a second refund while a
    # cancellation-auto-queued pending row is waiting for confirmation.
    # "processing" is counted because a gateway refund in flight is as
    # committed as a settled one; a failure will flip it to "failed" later.
    already = (
        (
            await db.execute(
                select(func.coalesce(func.sum(Refund.amount_paise), 0)).where(
                    Refund.order_id == order.id,
                    Refund.status.in_(("pending", "processing", "processed")),
                )
            )
        )
        .scalars()
        .one()
    )
    remaining = order.amount_paise - int(already or 0)

    # A college registration can own several orders (the base pass plus every
    # category-change delta). The registration desk refunds against that whole
    # pot, so this screen must use the same total - otherwise it offers to
    # refund base money that the delta has already consumed, or refuses a
    # refund the desk can legitimately make.
    reg_row = None
    registration_remaining = None
    if order.purpose in ("college_registration", "college_registration_delta"):
        from app.models.registration import CollegeRegistration

        if order.linked_record_id is not None:
            reg_row = await db.get(CollegeRegistration, order.linked_record_id)
        if reg_row is None:
            reg_row = (
                await db.execute(
                    select(CollegeRegistration).where(
                        CollegeRegistration.order_id == order.id
                    )
                )
            ).scalars().first()
    if reg_row is not None:
        from app.services.college_registrations import (
            _collected_paise,
            _refund_order_ids,
        )

        order_ids = await _refund_order_ids(db, reg_row)
        committed = (
            (
                await db.execute(
                    select(func.coalesce(func.sum(Refund.amount_paise), 0)).where(
                        Refund.order_id.in_(order_ids),
                        Refund.status.in_(("pending", "processing", "processed")),
                    )
                )
            )
            .scalars()
            .one()
        ) or 0
        registration_remaining = await _collected_paise(db, reg_row) - int(committed)
        if amount_paise > max(registration_remaining, 0):
            raise ValidationFailed(
                f"Only INR {max(registration_remaining, 0) / 100:.2f} of this "
                "registration is still refundable."
            )

    if amount_paise > remaining and registration_remaining is None:
        raise ValidationFailed(
            f"Only INR {remaining / 100:.2f} of this order is still refundable."
        )
    if amount_paise > remaining and registration_remaining is not None:
        # A delta slice can exceed its own order only when the caller asked for
        # the whole registration; that is handled by the registration-level cap
        # above, so allow the remainder to be refunded out of the same order.
        amount_paise = min(amount_paise, remaining)

    transaction = (
        (
            await db.execute(
                select(PaymentTransaction)
                .where(PaymentTransaction.order_id == order.id)
                .order_by(PaymentTransaction.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    # Without a captured transaction there is nothing to refund at the gateway.
    # Recording a "processed" refund here used to revoke passes/tickets while
    # the attendee's money stayed with the organiser.
    if transaction is None:
        raise ValidationFailed(
            "This order has no captured payment, so it cannot be refunded through the gateway."
        )

    try:
        gateway_id = await asyncio.to_thread(
            _gateway_refund_sync, transaction.gateway_payment_id, amount_paise
        )
    except AppError:
        raise
    except Exception as exc:
        logger.warning(
            "gateway_refund_failed", order=str(order.id), error=str(exc)[:200]
        )
        raise AppError(
            "The payment gateway did not accept the refund. Nothing was changed; try again.",
            code="REFUND_GATEWAY_ERROR",
            status_code=502,
        ) from exc
    if not gateway_id:
        raise AppError(
            "The payment gateway did not return a refund id. Nothing was changed; try again.",
            code="REFUND_GATEWAY_ERROR",
            status_code=502,
        )

    # A pending request created by the cancellation cascades is the same refund:
    # settle that row instead of adding a second one for the same money.
    refund = (
        await db.execute(
            select(Refund).where(
                Refund.order_id == order.id,
                Refund.status == "pending",
                Refund.amount_paise == amount_paise,
            )
        )
    ).scalars().first()
    # "Accepted by the gateway" is not "settled". A real gateway refund stays
    # ``processing`` until refund.processed arrives (and can still turn into
    # ``failed``, which the old immediate "processed" write made impossible).
    # Without a live gateway the mock moves the money immediately.
    settings = get_settings()
    settled_now = not settings.payments_enabled
    refund_status = "processed" if settled_now else "processing"
    processed_at = datetime.now(UTC) if settled_now else None
    if refund is not None:
        refund.transaction_id = transaction.id if transaction else None
        refund.reason_code = reason_code
        refund.reason_note = reason_note or refund.reason_note
        refund.status = refund_status
        refund.approved_by = requested_by_id
        refund.gateway_refund_id = gateway_id
        refund.processed_at = processed_at
    else:
        refund = Refund(
            order_id=order.id,
            transaction_id=transaction.id if transaction else None,
            amount_paise=amount_paise,
            reason_code=reason_code,
            reason_note=reason_note,
            status=refund_status,
            requested_by=requested_by_id,
            approved_by=requested_by_id,
            gateway_refund_id=gateway_id,
            processed_at=processed_at,
        )
        db.add(refund)
    await db.flush()
    # Count both processing and processed so the refunded total is accurate
    # even when the gateway has not yet settled (live payments_enabled mode).
    refunded_total = (
        (
            await db.execute(
                select(func.coalesce(func.sum(Refund.amount_paise), 0)).where(
                    Refund.order_id == order.id,
                    Refund.status.in_(("processing", "processed")),
                )
            )
        )
        .scalars()
        .one()
    ) or 0

    full_refund = amount_paise >= remaining
    if registration_remaining is not None:
        full_refund = amount_paise >= registration_remaining
    if full_refund:
        # A full refund must also take back the entitlement it paid for.
        order.status = "refunded"
        if order.purpose == "pass" and order.linked_record_id:
            # Legacy rows only. Refunding the money must take the pass back:
            # this direction only ever removes an entitlement, so it is safe on
            # a historic order (activating one is not - see mark_order_paid).
            user_pass = await db.get(ConventionPass, order.linked_record_id)
            if user_pass is not None and user_pass.status != "refunded":
                user_pass.status = "refunded"
                await revoke_for_pass(db, user_pass.id)
                # The pass either came with a seat allowance or the attendee
                # bought seats on top. Refunding its money without releasing
                # them left a live seat and ticket behind a dead pass.
                from app.services.passes import release_event_entitlements

                await release_event_entitlements(
                    db,
                    user_id=user_pass.user_id,
                    edition_id=user_pass.edition_id,
                    reason="Legacy pass order refunded",
                    refund_paid_events=True,
                    try_gateway=settled_now,
                    actor_id=requested_by_id,
                )
        if order.purpose == "college_registration" or (
            reg_row is not None and full_refund
        ):
            # The convention pass is sold through a college_registration order.
            # Refunding it has to mirror the registration-desk rejection: the
            # bill stays, but the pass, its ticket and the free included-event
            # selections die with it. Skipping this left attendees with a live
            # QR in the portal even after their money was returned.
            from app.models.registration import CollegeRegistration

            col_reg = (
                await db.execute(
                    select(CollegeRegistration).where(
                        CollegeRegistration.order_id == order.id
                    )
                )
            ).scalars().first()
            if col_reg is None and reg_row is not None:
                col_reg = reg_row
            if col_reg is not None and col_reg.payment_status == "paid":
                col_reg.payment_status = "refunded"
                # "Completed" only once the money settled; a live gateway refund
                # is still processing, so a refund.failed webhook can correct it.
                col_reg.refund_status = "completed" if settled_now else "processing"
                col_reg.refund_amount_paise = int(refunded_total)
                col_reg.refund_id = refund.id
                user_pass = (
                    await db.execute(
                        select(ConventionPass)
                        .where(
                            ConventionPass.user_id == col_reg.user_id,
                            ConventionPass.edition_id == col_reg.edition_id,
                        )
                        .order_by(ConventionPass.created_at.desc())
                        .limit(1)
                    )
                ).scalars().first()
                if user_pass is not None and user_pass.status != "refunded":
                    user_pass.status = "refunded"
                    await revoke_for_pass(db, user_pass.id)
                # Free the attendee's seats, drop them from team rosters and
                # return the money for any paid add-on events. This is the same
                # cascade the registration desk uses on rejection, so a refunded
                # pass never leaves a live seat or an unreturned add-on payment.
                from app.services.passes import release_event_entitlements

                await release_event_entitlements(
                    db,
                    user_id=col_reg.user_id,
                    edition_id=col_reg.edition_id,
                    reason="Convention pass refunded",
                    actor_id=requested_by_id,
                )
        registrations = list(
            (
                await db.execute(
                    select(Registration).where(Registration.order_id == order.id)
                )
            ).scalars()
        )
        for reg in registrations:
            if reg.status in ("confirmed", "reserved", "pending"):
                reg.status = "cancelled"
                reg.cancelled_at = datetime.now(UTC)
                await revoke_for_registration(db, reg.id)
    elif order.purpose in ("college_registration", "college_registration_delta"):
        # Partial refund: record it on the pass so the desk can see how much has
        # gone back and finish the rest later. The pass itself stays valid (the
        # attendee kept the entitlement they were not refunded for).
        from app.models.registration import CollegeRegistration

        col_reg = reg_row or (
            await db.execute(
                select(CollegeRegistration).where(
                    CollegeRegistration.order_id == order.id
                )
            )
        ).scalars().first()
        if col_reg is not None:
            col_reg.refund_status = "completed"
            col_reg.refund_amount_paise = int(refunded_total)
            col_reg.refund_id = refund.id

    await db.flush()
    try:
        from app.services.telegram import dispatch_payment_telegram_alert
        from app.models.user import User

        user = await db.get(User, order.user_id) if order.user_id else None
        # This is money leaving, not a payment: report the refund itself (amount
        # and refund id) instead of a "Payment Successful" alert.
        dispatch_payment_telegram_alert(
            "refund",
            order_id=str(order.id),
            amount_paise=amount_paise,
            purpose=order.purpose,
            gateway_order_id=order.gateway_order_id,
            attendee_name=user.full_name if user else None,
            attendee_email=user.email if user else None,
            refund_id=refund.gateway_refund_id or str(refund.id),
            refund_status=refund.status,
        )
    except Exception:
        pass
    cache_delete_pattern("public:*")
    cache_delete_pattern("admin:dashboard:*")
    return refund


async def order_for(db: AsyncSession, order_id: uuid.UUID) -> PaymentOrder:
    row = await db.get(PaymentOrder, order_id)
    if row is None:
        raise NotFound("Payment order not found.")
    return row


def mock_payment_id() -> str:
    return f"mock_tx_{uuid.uuid4().hex[:12]}"


__all__ = [
    "_auth_header",
    "attach_gateway_order",
    "create_gateway_order",
    "gateway_refund",
    "create_order",
    "mark_order_paid",
    "expire_unpaid",
    "verify_webhook_signature",
    "verify_checkout_signature",
    "fetch_gateway_payment",
    "fetch_gateway_refund",
    "process_webhook",
    "refund_order",
    "order_for",
    "mock_payment_id",
]

