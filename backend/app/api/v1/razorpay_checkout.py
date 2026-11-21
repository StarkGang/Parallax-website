"""Razorpay Standard Web Checkout API endpoints.

Implements standard order creation and payment signature verification.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
import httpx
try:
    import razorpay
except ImportError:  # pragma: no cover
    razorpay = None
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.models.commerce import PaymentOrder
from app.services.payments import mark_order_paid

router = APIRouter(tags=["razorpay-checkout"])
logger = get_logger("razorpay_checkout")


class CreateOrderRequest(BaseModel):
    amount: int = Field(..., description="Amount in paise (minimum 100 paise = 1 INR)")
    currency: str = Field("INR", description="Currency code (e.g. INR)")
    receipt: str | None = Field(None, description="Optional internal receipt ID")
    notes: dict[str, Any] | None = Field(None, description="Optional metadata key-value pairs")


class CreateOrderResponse(BaseModel):
    order_id: str
    amount: int
    currency: str
    key_id: str | None = None
    # Aliases for frontend convenience
    orderId: str | None = None
    keyId: str | None = None


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str | None = None
    razorpay_payment_id: str | None = None
    razorpay_signature: str | None = None
    order_id: str | None = None
    payment_id: str | None = None
    signature: str | None = None


class VerifyPaymentResponse(BaseModel):
    status: str
    message: str
    order_id: str
    payment_id: str


@router.post(
    "/create-order",
    response_model=CreateOrderResponse,
    dependencies=[Depends(limiter("create_order", 60, 60))],
)
async def create_razorpay_order(
    payload: CreateOrderRequest,
) -> CreateOrderResponse:
    """Create a Razorpay order for Standard Web Checkout."""
    # 1. Validate amount >= 100 paise
    if payload.amount is None or payload.amount < 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Amount must be at least 100 paise (1 INR).",
        )

    settings = get_settings()
    key_id = settings.razorpay_key_id
    key_secret = settings.razorpay_key_secret

    # 2. Validate credentials
    if not key_id or not key_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Razorpay credentials not configured or unauthorized.",
        )

    # 3. Create order via Razorpay SDK (with httpx fallback)
    receipt = payload.receipt or f"rcpt_{uuid.uuid4().hex[:12]}"
    order_data: dict[str, Any] = {
        "amount": int(payload.amount),
        "currency": payload.currency.upper(),
        "receipt": receipt,
    }
    if payload.notes:
        order_data["notes"] = payload.notes

    try:
        if razorpay is not None:
            client = razorpay.Client(auth=(key_id, key_secret))
            order = client.order.create(data=order_data)
        else:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(8.0, connect=4.0, read=6.0)
            ) as client:
                res = await client.post(
                    "https://api.razorpay.com/v1/orders",
                    auth=(key_id, key_secret),
                    json=order_data,
                )
                if res.status_code == 401:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Razorpay authentication failed. Verify RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET.",
                    )
                if res.status_code >= 400:
                    raise HTTPException(
                        status_code=res.status_code,
                        detail=f"Razorpay API error: {res.text}",
                    )
                order = res.json()

        order_id = order.get("id")
        if not order_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Razorpay did not return an order ID.",
            )

        return CreateOrderResponse(
            order_id=order_id,
            amount=int(order.get("amount", payload.amount)),
            currency=str(order.get("currency", payload.currency.upper())),
            key_id=key_id,
            orderId=order_id,
            keyId=key_id,
        )

    except HTTPException:
        raise
    except Exception as exc:
        if razorpay and isinstance(exc, getattr(razorpay.errors, "AuthenticationError", ().__class__)):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Razorpay authentication failed. Verify RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET.",
            )
        if razorpay and isinstance(exc, getattr(razorpay.errors, "BadRequestError", ().__class__)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Razorpay request rejected: {exc}",
            )
        logger.error("razorpay_order_creation_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create Razorpay order: {exc}",
        )


@router.post(
    "/verify-payment",
    response_model=VerifyPaymentResponse,
    dependencies=[Depends(limiter("verify_payment", 60, 60))],
)
async def verify_razorpay_payment(
    payload: VerifyPaymentRequest,
    db: AsyncSession = Depends(get_db),
) -> VerifyPaymentResponse:
    """Verify the Razorpay payment signature using HMAC-SHA256."""
    order_id = payload.razorpay_order_id or payload.order_id
    payment_id = payload.razorpay_payment_id or payload.payment_id
    signature = payload.razorpay_signature or payload.signature

    # 1. Missing fields check -> return 400
    if not order_id or not payment_id or not signature:
        missing = []
        if not order_id:
            missing.append("razorpay_order_id")
        if not payment_id:
            missing.append("razorpay_payment_id")
        if not signature:
            missing.append("razorpay_signature")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required fields: {', '.join(missing)}",
        )

    settings = get_settings()
    key_secret = settings.razorpay_key_secret
    if not key_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Razorpay key secret is not configured.",
        )

    # 2. Algorithm: HMAC-SHA256(order_id + "|" + payment_id, KEY_SECRET)
    data_to_sign = f"{order_id}|{payment_id}".encode("utf-8")
    expected_signature = hmac.new(
        key_secret.encode("utf-8"),
        data_to_sign,
        hashlib.sha256,
    ).hexdigest()

    # 3. Compare signatures with constant-time compare
    if not hmac.compare_digest(expected_signature, signature):
        logger.warning(
            "razorpay_signature_mismatch",
            order_id=order_id,
            payment_id=payment_id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment signature verification failed.",
        )

    # 4. If linked to an internal database order, mark as paid
    db_order = (
        await db.execute(
            select(PaymentOrder).where(PaymentOrder.gateway_order_id == order_id)
        )
    ).scalar_one_or_none()

    if db_order and db_order.status != "paid":
        await mark_order_paid(db, db_order, transaction_id=payment_id)

    return VerifyPaymentResponse(
        status="success",
        message="Payment verified successfully.",
        order_id=order_id,
        payment_id=payment_id,
    )

