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
from app.core.rate_limit import _subject, consume
from app.core.sessions import token_from_request
from app.core.uploads import read_upload_limited
from app.models.commerce import PaymentWebhookEvent
from app.models.edition import ConventionEdition
from app.models.registration import CollegeRegistration, RegistrationCategory
from app.models.user import User
from app.services.tickets import public_registration_code


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
@pytest.mark.asyncio
async def test_direct_login_is_rate_limited_per_email_and_ip(client: AsyncClient):
    # The limiter uses fixed windows aligned to the epoch, so a run that
    # straddles a 5-minute boundary legitimately resets the counter halfway
    # through. Retry on a fresh email in that case instead of failing on the
    # clock; within one window the 20-then-429 sequence is exact.
    headers = {"x-forwarded-for": "203.0.113.77"}
    for _ in range(3):
        email = f"limit-{uuid.uuid4().hex[:8]}@test.local"
        statuses = []
        for _ in range(21):
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "role": "participant"},
                headers=headers,
            )
            statuses.append(response.status_code)
        if statuses[:20] == [200] * 20:
            assert statuses[20] == 429
            return
    pytest.fail(f"login limiter never blocked: {statuses}")

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
async def test_rate_limit_ignores_unverified_cookie_subject(db_session):
    """A caller-chosen cookie must not buy a fresh rate-limit bucket."""
    from starlette.requests import Request

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/me",
            "query_string": b"",
            "headers": [
                (b"cookie", b"px_session=chosen-by-the-caller"),
                (b"x-forwarded-for", b"203.0.113.44"),
            ],
            "client": ("127.0.0.1", 5555),
        }
    )
    assert await _subject(db_session, request) == "ip:203.0.113.44"


@pytest.mark.asyncio
async def test_session_token_in_query_string_is_ignored():
    """Session tokens must never be accepted from a URL."""
    from starlette.requests import Request

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/me",
            "query_string": b"token=leaked-session-token",
            "headers": [],
            "client": ("127.0.0.1", 5555),
        }
    )
    assert token_from_request(request) is None


@pytest.mark.asyncio
async def test_credential_page_escapes_participant_html(client: AsyncClient, db_session):
    """The public QR verification page must not render participant HTML."""
    edition = await db_session.scalar(select(ConventionEdition).limit(1))
    category = await db_session.scalar(
        select(RegistrationCategory)
        .where(RegistrationCategory.edition_id == edition.id)
        .limit(1)
    )
    # A dedicated account: the first row in the table may already hold a
    # registration for this edition from another test in the same run.
    user = await db_session.scalar(select(User).where(User.email == "xss@test.local"))
    if user is None:
        user = User(
            email="xss@test.local",
            email_normalized="xss@test.local",
            full_name="XSS Tester",
        )
        db_session.add(user)
        await db_session.flush()
    number = f"PX-ESC-{uuid.uuid4().hex[:6].upper()}"
    db_session.add(
        CollegeRegistration(
            edition_id=edition.id,
            user_id=user.id,
            category_id=category.id,
            category_code=category.code,
            category_name="<b>ISTE</b>",
            full_name="<script>alert('xss')</script>",
            email="xss@test.local",
            college_name="<img src=x onerror=alert(1)>",
            payment_status="paid",
            verification_status="approved",
            registration_number=number,
        )
    )
    await db_session.commit()

    # A bare registration number must not resolve: the public page is only
    # reachable through a signed code this server issued.
    unsigned = await client.get(
        f"/api/v1/public/c/{number}", headers={"Accept": "text/html"}
    )
    assert unsigned.status_code == 200
    assert "<script>alert" not in unsigned.text
    assert "&lt;script&gt;" not in unsigned.text
    assert unsigned.json()["data"]["valid"] is False

    response = await client.get(
        f"/api/v1/public/c/{public_registration_code(number)}",
        headers={"Accept": "text/html"},
    )
    assert response.status_code == 200
    assert "<script>alert" not in response.text
    assert "&lt;script&gt;" in response.text
    assert "<img src=x" not in response.text
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


@pytest.mark.asyncio
async def test_upload_reader_stops_at_limit():
    upload = UploadFile(filename="big.png", file=io.BytesIO(b"x" * (2 * 1024 * 1024)))
    with pytest.raises(AppError) as caught:
        await read_upload_limited(upload, 1024 * 1024, label="Document")
    assert caught.value.status_code == 413
    assert caught.value.code == "FILE_TOO_LARGE"