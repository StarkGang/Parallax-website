"""Payments: Razorpay order generation, webhooks, mock payment in dev and refunds."""

import base64
import hmac
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, NotFound, ValidationFailed
from app.models.commerce import (
    ConventionPass,
    PaymentOrder,
    PaymentTransaction,
    PaymentWebhookEvent,
    Refund,
    Registration,
)
from app.services.passes import activate_mock_pass
from app.services.tickets import issue_for_pass, issue_for_registration


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
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["id"]


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
    except Exception:
        pass
    return order


async def mark_order_paid(
    db: AsyncSession, order: PaymentOrder, transaction_id: str | None = None
) -> None:
    if order.status == "paid":
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
            user_pass.status = "active"
            user_pass.paid_at = datetime.now(UTC)
            await issue_for_pass(db, user_pass)

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

    await db.flush()


async def expire_unpaid(db: AsyncSession) -> int:
    return 0


def verify_webhook_signature(body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
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
    if event_type == "payment.captured":
        pay_entity = event_payload.get("payload", {}).get("payment", {}).get("entity", {})
        order_id = pay_entity.get("order_id")
        if order_id:
            order = (
                await db.execute(
                    select(PaymentOrder).where(PaymentOrder.gateway_order_id == order_id)
                )
            ).scalar_one_or_none()
            if order:
                await mark_order_paid(db, order, transaction_id=pay_entity.get("id"))

    await db.flush()


async def refund_order(
    db: AsyncSession,
    order: PaymentOrder,
    amount_paise: int,
    reason_code: str,
    reason_note: str | None = None,
    requested_by_id: uuid.UUID | None = None,
) -> Refund:
    refund = Refund(
        order_id=order.id,
        amount_paise=amount_paise,
        reason_code=reason_code,
        reason_note=reason_note,
        status="processed",
        requested_by=requested_by_id,
        approved_by=requested_by_id,
        processed_at=datetime.now(UTC),
    )
    db.add(refund)
    order.status = "refunded"
    await db.flush()
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
    "create_gateway_order",
    "gateway_refund",
    "create_order",
    "mark_order_paid",
    "expire_unpaid",
    "verify_webhook_signature",
    "process_webhook",
    "refund_order",
    "order_for",
    "mock_payment_id",
    "order_url_token",
]

