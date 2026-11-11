import hashlib
import hmac

import pytest
from httpx import AsyncClient
from sqlalchemy import select, func

from app.core.config import get_settings
from app.models.commerce import PaymentWebhookEvent


@pytest.mark.asyncio
async def test_webhook_fails_closed_without_secret(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(get_settings(), "razorpay_webhook_secret", None)
    response = await client.post(
        "/api/v1/webhooks/razorpay",
        content=b'{"event":"unknown"}',
        headers={"X-Razorpay-Signature": "invalid"},
    )
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_webhook_signature_raw_body_and_duplicate_event_id(client, db_session, monkeypatch):
    secret = "unit-test-webhook-secret"
    monkeypatch.setattr(get_settings(), "razorpay_webhook_secret", secret)
    body = b'{"event":"subscription.paused"}'
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    headers = {
        "X-Razorpay-Signature": signature,
        "X-Razorpay-Event-Id": "evt_unit_test_001",
    }

    first = await client.post("/api/v1/webhooks/razorpay", content=body, headers=headers)
    duplicate = await client.post("/api/v1/webhooks/razorpay", content=body, headers=headers)
    assert first.status_code == duplicate.status_code == 200
    count = await db_session.scalar(
        select(func.count()).select_from(PaymentWebhookEvent).where(
            PaymentWebhookEvent.gateway_event_id == "evt_unit_test_001"
        )
    )
    assert count == 1

