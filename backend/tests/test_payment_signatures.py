import hashlib
import hmac
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.commerce import PaymentOrder
from app.models.edition import ConventionEdition
from app.models.user import User
from app.services.payments import (
    expire_unpaid,
    verify_checkout_signature,
    verify_webhook_signature,
)


def test_checkout_signature_validates_order_and_payment_pair():
    secret = "test-secret"
    message = b"order_123|pay_456"
    signature = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()

    assert verify_checkout_signature("order_123", "pay_456", signature, secret)
    assert not verify_checkout_signature("order_other", "pay_456", signature, secret)


def test_webhook_signature_uses_exact_raw_body():
    secret = "test-webhook-secret"
    body = b'{"event":"payment.captured","payload":{}}'
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert verify_webhook_signature(body, signature, secret)
    assert not verify_webhook_signature(body + b" ", signature, secret)


@pytest.mark.asyncio
async def test_expire_unpaid_closes_stale_orders(db_session):
    """A stale unpaid order must stop holding a seat, not linger as created."""
    edition = await db_session.scalar(select(ConventionEdition))
    user = await db_session.scalar(select(User))
    assert edition is not None and user is not None

    stale = PaymentOrder(
        edition_id=edition.id,
        user_id=user.id,
        purpose="addon",
        amount_paise=1000,
        status="created",
    )
    stale.created_at = datetime.now(UTC) - timedelta(hours=2)
    fresh = PaymentOrder(
        edition_id=edition.id,
        user_id=user.id,
        purpose="addon",
        amount_paise=1000,
        status="created",
    )
    db_session.add_all([stale, fresh])
    await db_session.commit()

    expired = await expire_unpaid(db_session)
    await db_session.commit()

    assert expired >= 1
    assert (await db_session.get(PaymentOrder, stale.id)).status == "expired"
    assert (await db_session.get(PaymentOrder, fresh.id)).status == "created"
