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
from app.models.commerce import (
    ConventionPass,
    PaymentOrder,
    PaymentTransaction,
    PaymentWebhookEvent,
    Refund,
    Registration,
)
from app.services.passes import (
    selections_for,
    sync_included_registrations,
)
from app.services.tickets import (
    issue_for_pass,
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

    if order.purpose == "pass" and order.linked_record_id:
        user_pass = await db.get(ConventionPass, order.linked_record_id)
        if user_pass:
            user_pass.status = "active"
            user_pass.paid_at = datetime.now(UTC)
            await issue_for_pass(db, user_pass)
            await sync_included_registrations(
                db, user_pass, await selections_for(db, user_pass.id)
            )

    elif order.purpose == "registration":
        regs = list(
            (
                await db.execute(
                    select(Registration).where(Registration.order_id == order.id)
                )
            ).scalars()
        )
        for r in regs:
            r.status = "confirmed"
            await issue_for_registration(db, r)

    elif order.purpose == "college_registration":
        from app.services.college_registrations import finalize_paid

        await finalize_paid(db, order, transaction_id=transaction_id)

    elif order.purpose == "college_registration_delta":
        from app.services.college_registrations import apply_paid_category_change

        await apply_paid_category_change(db, order)

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

    already = (
        (
            await db.execute(
                select(func.coalesce(func.sum(Refund.amount_paise), 0)).where(
                    Refund.order_id == order.id,
                    Refund.status == "processed",
                )
            )
        )
        .scalars()
        .one()
    )
    remaining = order.amount_paise - int(already or 0)
    if amount_paise > remaining:
        raise ValidationFailed(
            f"Only INR {remaining / 100:.2f} of this order is still refundable."
        )

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

    refund = Refund(
        order_id=order.id,
        transaction_id=transaction.id if transaction else None,
        amount_paise=amount_paise,
        reason_code=reason_code,
        reason_note=reason_note,
        status="processed",
        requested_by=requested_by_id,
        approved_by=requested_by_id,
        gateway_refund_id=gateway_id,
        processed_at=datetime.now(UTC),
    )
    db.add(refund)

    if amount_paise >= remaining:
        # A full refund must also take back the entitlement it paid for.
        order.status = "refunded"
        if order.purpose == "pass" and order.linked_record_id:
            user_pass = await db.get(ConventionPass, order.linked_record_id)
            if user_pass is not None:
                user_pass.status = "refunded"
                await revoke_for_pass(db, user_pass.id)
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
            payment_id=transaction.gateway_payment_id if transaction else None,
            gateway_order_id=order.gateway_order_id,
            attendee_name=user.full_name if user else None,
            attendee_email=user.email if user else None,
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

