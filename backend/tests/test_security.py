"""Security regressions: rate limits, webhook fail-closed, origins and upload caps."""

import hashlib
import hmac
import io
import json
import uuid

import pytest
from fastapi import UploadFile
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.errors import AppError
from app.core.rate_limit import consume
from app.core.uploads import read_upload_limited
from app.models.commerce import PaymentWebhookEvent


@pytest.mark.asyncio
async def test_rate_limit_blocks_after_limit(db_session):
    bucket = f"test-{uuid.uuid4().hex}"
    subject = "ip:203.0.113.10"
    first, _ = await consume(db_session, bucket, subject, 2, 60)
    second, _ = await consume(db_session, bucket, subject, 2, 60)
    third, retry_after = await consume(db_session, bucket, subject, 2, 60)
    assert (first, second, third) == (True, True, False)
    assert retry_after > 0


@pytest.mark.asyncio
async def test_direct_login_is_rate_limited_per_email_and_ip(client: AsyncClient):
    headers = {"x-forwarded-for": "203.0.113.77"}
    email = f"limit-{uuid.uuid4().hex[:8]}@test.local"
    statuses = []
    for _ in range(21):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "role": "participant"},
            headers=headers,
        )
        statuses.append(response.status_code)
    assert statuses[:20] == [200] * 20
    assert statuses[20] == 429


@pytest.mark.asyncio
async def test_foreign_vercel_origin_is_rejected(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "origin-test@test.local", "role": "participant"},
        headers={"Origin": "https://parallax-iste-evil.vercel.app"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ORIGIN_REJECTED"


@pytest.mark.asyncio
async def test_staff_cannot_bypass_enforced_mfa(client: AsyncClient, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "mfa_enforced", True)
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@parallax.local", "role": "admin"},
    )
    assert login.status_code == 200, login.text
    edition = await client.get("/api/v1/public/editions/current")
    edition_id = edition.json()["data"]["id"]
    blocked = await client.get(f"/api/v1/editions/{edition_id}/admin/overview")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "MFA_REQUIRED"


@pytest.mark.asyncio
async def test_chunked_body_without_content_length_is_limited(client: AsyncClient, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "max_request_body_bytes", 64)

    async def chunks():
        yield b"x" * 128

    response = await client.post(
        "/api/v1/auth/login",
        content=chunks(),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


@pytest.mark.asyncio
async def test_razorpay_webhook_fails_closed_without_secret(
    client: AsyncClient, db_session, monkeypatch
):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_webhook_secret", None)
    event_id = f"evt_missing_{uuid.uuid4().hex}"
    response = await client.post(
        "/api/v1/webhooks/razorpay",
        content=json.dumps({"event": "payment.captured", "event_id": event_id}),
        headers={"X-Razorpay-Signature": "not-a-real-signature"},
    )
    assert response.status_code == 503
    count = await db_session.scalar(
        select(func.count(PaymentWebhookEvent.id)).where(
            PaymentWebhookEvent.gateway_event_id == event_id
        )
    )
    assert count == 0


@pytest.mark.asyncio
async def test_razorpay_webhook_accepts_valid_signature(
    client: AsyncClient, db_session, monkeypatch
):
    from app.core.config import get_settings

    settings = get_settings()
    secret = "test-webhook-secret"
    monkeypatch.setattr(settings, "razorpay_webhook_secret", secret)
    event_id = f"evt_valid_{uuid.uuid4().hex}"
    body = json.dumps({"event": "payment.failed", "event_id": event_id}).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    response = await client.post(
        "/api/v1/webhooks/razorpay",
        content=body,
        headers={"X-Razorpay-Signature": signature},
    )
    assert response.status_code == 200
    count = await db_session.scalar(
        select(func.count(PaymentWebhookEvent.id)).where(
            PaymentWebhookEvent.gateway_event_id == event_id
        )
    )
    assert count == 1


@pytest.mark.asyncio
async def test_upload_reader_stops_at_limit():
    upload = UploadFile(filename="big.png", file=io.BytesIO(b"x" * (2 * 1024 * 1024)))
    with pytest.raises(AppError) as caught:
        await read_upload_limited(upload, 1024 * 1024, label="Document")
    assert caught.value.status_code == 413
    assert caught.value.code == "FILE_TOO_LARGE"