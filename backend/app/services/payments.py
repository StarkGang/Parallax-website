"""Payments: Razorpay order generation, webhooks, mock payment in dev and refunds."""

import base64
import hmac
import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_delete_pattern
from app.core.config import get_settings
from app.core.errors import AppError, Conflict, NotFound, ValidationFailed
from app.models.commerce import (
    ConventionPass,
    PaymentOrder,
    PaymentTransaction,
    PaymentWebhookEvent,
    Refund,
    Registration,
)
from app.models.edition import EligibilityVerification
from app.services.passes import (
    activate_mock_pass,
    selections_for,
    sync_included_registrations,
)
from app.services.tickets import (
    issue_for_pass,
    issue_for_registration,
    revoke_for_pass,
    revoke_for_registration,
)

logger = logging.getLogger(__name__)


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
        return f"mock_order_{order.id.hex[:12]}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            "https://api.razorpay.com/v1/orders",
            headers=_auth_header(),
            json={
                "amount": order.amount_paise,
                "currency": "INR",
                "receipt": str(order.id),
                "notes": {
                    "user_id": str(order.user_id),
                    "edition_id": str(order.edition_id),
                    "purpose": order.purpose,
                    "internal_order_id": str(order.id),
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["id"]


async def attach_gateway_order(db: AsyncSession, order: PaymentOrder) -> PaymentOrder:
    """Create the provider order exactly once so checkout can actually open."""
    if order.gateway_order_id:
        return order
    try:
        order.gateway_order_id = await create_gateway_order(order)
        order.status = "created"
        await db.flush()
    except Exception as exc:  # pragma: no cover - provider failure path
        logger.warning("Gateway order creation failed for %s: %s", order.id, exc)
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
        return f"mock_rfnd_{uuid.uuid4().hex[:12]}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"https://api.razorpay.com/v1/payments/{payment_id}/refund",
            headers=_auth_header(),
            json={"amount": amount_paise},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["id"]


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
        order.status = "failed"
        await db.flush()
        raise AppError(
            "Could not start the payment. Please try again.",
            code="PAYMENT_GATEWAY_ERROR",
            status_code=502,
        ) from exc
    return order


async def mark_order_paid(
    db: AsyncSession, order: PaymentOrder, transaction_id: str | None = None
) -> None:
    if order.status in ("paid", "refunded"):
        return
    order.status = "paid"
    order.paid_at = datetime.now(UTC)

    tx = PaymentTransaction(
        order_id=order.id,
        gateway_payment_id=transaction_id or f"pay_{uuid.uuid4().hex[:12]}",
        status="captured",
        amount_paise=order.amount_paise,
    )
    db.add(tx)

    if order.purpose == "pass" and order.linked_record_id:
        user_pass = await db.get(ConventionPass, order.linked_record_id)
        if user_pass:
            verified = await db.scalar(
                select(EligibilityVerification.id).where(
                    EligibilityVerification.user_id == order.user_id,
                    EligibilityVerification.edition_id == order.edition_id,
                    EligibilityVerification.status == "verified",
                )
            ) is not None
            user_pass.status = "active" if verified else "pending_verification"
            user_pass.paid_at = datetime.now(UTC)
            if verified:
                await issue_for_pass(db, user_pass)
                await sync_included_registrations(
                    db, user_pass, await selections_for(db, user_pass.id)
                )

    elif order.purpose == "registration":
        verified = await db.scalar(
            select(EligibilityVerification.id).where(
                EligibilityVerification.user_id == order.user_id,
                EligibilityVerification.edition_id == order.edition_id,
                EligibilityVerification.status == "verified",
            )
        ) is not None
        regs = list(
            (
                await db.execute(
                    select(Registration).where(Registration.order_id == order.id)
                )
            ).scalars()
        )
        for r in regs:
            r.status = "confirmed" if verified else "pending_verification"
            if verified:
                await issue_for_registration(db, r)

    await db.flush()
    cache_delete_pattern("public:*")
    cache_delete_pattern("admin:dashboard:*")


async def _finalize_full_refund(db: AsyncSession, order: PaymentOrder) -> None:
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
    for registration in registrations:
        if registration.status in ("confirmed", "reserved", "pending", "pending_verification"):
            registration.status = "cancelled"
            registration.cancelled_at = datetime.now(UTC)
            await revoke_for_registration(db, registration.id)


PAYMENT_ORDER_TTL = timedelta(minutes=30)

UNPAID_ORDER_STATUSES = ("created", "pending")


async def expire_unpaid(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    ttl: timedelta = PAYMENT_ORDER_TTL,
) -> int:
    """Expire stale unpaid orders so held passes and seats are released.

    No capture happens here. A provider capture that arrives after expiry is
    still honoured by the webhook, which settles the order through
    mark_order_paid because "expired" is not a terminal paid state.
    """
    moment = now or datetime.now(UTC)
    cutoff = moment - ttl
    stale = list(
        (
            await db.execute(
                select(PaymentOrder)
                .where(
                    PaymentOrder.status.in_(UNPAID_ORDER_STATUSES),
                    PaymentOrder.paid_at.is_(None),
                    PaymentOrder.created_at < cutoff,
                )
                .with_for_update()
            )
        ).scalars()
    )
    for order in stale:
        order.status = "expired"
        if order.expires_at is None:
            order.expires_at = cutoff
        if order.purpose == "pass" and order.linked_record_id:
            user_pass = await db.get(ConventionPass, order.linked_record_id)
            if user_pass is not None and user_pass.status == "pending":
                user_pass.status = "expired"
                await revoke_for_pass(db, user_pass.id)
        registrations = list(
            (
                await db.execute(
                    select(Registration).where(Registration.order_id == order.id)
                )
            ).scalars()
        )
        for registration in registrations:
            if registration.status in ("reserved", "pending"):
                registration.status = "cancelled"
                registration.cancelled_at = moment
                await revoke_for_registration(db, registration.id)
    if stale:
        await db.flush()
        cache_delete_pattern("public:*")
        cache_delete_pattern("admin:dashboard:*")
    return len(stale)


def verify_webhook_signature(body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_checkout_signature(order_id: str, payment_id: str, signature: str, secret: str) -> bool:
    """Verify Checkout's order/payment signature without treating the callback as settlement."""
    message = f"{order_id}|{payment_id}".encode()
    expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


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
    if existing and existing.processing_status in {"processed", "failed"}:
        return

    entry = existing or PaymentWebhookEvent(
        gateway_event_id=event_id,
        event_type=event_payload.get("event", "unknown"),
        signature_verified=True,
        payload_hash=hashlib.sha256(
            json.dumps(event_payload, sort_keys=True, default=str).encode()
        ).hexdigest(),
        processing_status="pending",
        received_at=datetime.now(UTC),
    )
    if existing is None:
        db.add(entry)

    event_type = event_payload.get("event")
    if event_type in {"payment.captured", "payment.failed"}:
        pay_entity = event_payload.get("payload", {}).get("payment", {}).get("entity", {})
        order_id = pay_entity.get("order_id")
        if order_id:
            order = (
                await db.execute(
                    select(PaymentOrder).where(PaymentOrder.gateway_order_id == order_id)
                )
            ).scalar_one_or_none()
            if event_type == "payment.captured" and order is None:
                raise AppError(
                    "Payment order is not available for reconciliation yet.",
                    code="WEBHOOK_RETRY",
                    status_code=503,
                )
            if order and event_type == "payment.captured":
                # Never attach a capture for a mismatched amount or currency to an order.
                if int(pay_entity.get("amount", -1)) != order.amount_paise or pay_entity.get("currency") != order.currency:
                    entry.processing_status = "failed"
                    entry.error = "Captured amount or currency did not match the order."
                else:
                    await mark_order_paid(db, order, transaction_id=pay_entity.get("id"))
            elif order and event_type == "payment.failed" and order.status not in ("paid", "refunded"):
                order.status = "failed"

    elif event_type == "refund.processed":
        refund_entity = event_payload.get("payload", {}).get("refund", {}).get("entity", {})
        gateway_refund_id = refund_entity.get("id")
        if gateway_refund_id:
            refund = await db.scalar(select(Refund).where(Refund.gateway_refund_id == gateway_refund_id))
            if refund is None:
                raise AppError(
                    "Refund is not available for reconciliation yet.",
                    code="WEBHOOK_RETRY",
                    status_code=503,
                )
            if refund:
                refund.status = "processed"
                refund.processed_at = datetime.now(UTC)
                order = await db.get(PaymentOrder, refund.order_id)
                if order:
                    already = await db.scalar(select(func.coalesce(func.sum(Refund.amount_paise), 0)).where(
                        Refund.order_id == order.id, Refund.status == "processed"
                    ))
                    if int(already or 0) >= order.amount_paise:
                        await _finalize_full_refund(db, order)

    if entry.processing_status != "failed":
        entry.processing_status = "processed"
        entry.processed_at = datetime.now(UTC)
    await db.flush()


async def refund_order(
    db: AsyncSession,
    order: PaymentOrder,
    amount_paise: int,
    reason_code: str,
    reason_note: str | None = None,
    requested_by_id: uuid.UUID | None = None,
    idempotency_key: str | None = None,
) -> Refund:
    locked_order = await db.scalar(
        select(PaymentOrder).where(PaymentOrder.id == order.id).with_for_update()
    )
    if locked_order is not None:
        order = locked_order
    idempotency_key = idempotency_key or f"refund:{order.id}:{reason_code}:{amount_paise}"
    previous = await db.scalar(select(Refund).where(Refund.idempotency_key == idempotency_key))
    if previous is not None:
        if (
            previous.order_id != order.id
            or previous.amount_paise != amount_paise
            or previous.reason_code != reason_code
        ):
            raise Conflict("This idempotency key was already used for another refund.")
        if previous.status != "failed":
            return previous
        previous.status = "pending"
        previous.reason_note = reason_note
        refund = previous
    else:
        refund = None

    if order.status != "paid":
        raise ValidationFailed("Only a paid order can be refunded.")
    if amount_paise <= 0:
        raise ValidationFailed("The refund amount must be greater than zero.")

    already = (
        (
            await db.execute(
                select(func.coalesce(func.sum(Refund.amount_paise), 0)).where(
                    Refund.order_id == order.id,
                    Refund.status.in_(("pending", "processed")),
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
    if refund is None:
        refund = Refund(
            order_id=order.id,
            transaction_id=transaction.id if transaction else None,
            amount_paise=amount_paise,
            reason_code=reason_code,
            reason_note=reason_note,
            status="pending",
            requested_by=requested_by_id,
            approved_by=requested_by_id,
            idempotency_key=idempotency_key,
        )
        db.add(refund)
    await db.flush()

    try:
        if transaction is not None:
            gateway_id = await gateway_refund(transaction.gateway_payment_id, amount_paise)
            refund.gateway_refund_id = gateway_id
        refund.status = "processed" if not get_settings().payments_enabled else "pending"
        if refund.status == "processed":
            refund.processed_at = datetime.now(UTC)
    except Exception as exc:
        refund.status = "failed"
        refund.reason_note = reason_note
        await db.flush()
        raise AppError("The refund request failed. It can be retried safely.", code="REFUND_GATEWAY_ERROR", status_code=502) from exc

    if amount_paise >= remaining and refund.status == "processed":
        await _finalize_full_refund(db, order)

    await db.flush()
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


def order_url_token(order_id: uuid.UUID) -> str:
    return f"ord_{order_id.hex}"


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
    "process_webhook",
    "refund_order",
    "order_for",
    "mock_payment_id",
    "order_url_token",
]

