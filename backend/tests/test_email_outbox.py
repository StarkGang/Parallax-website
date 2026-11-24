"""EMAIL-001: the outbox is gated, retried, capped and dispatched."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import email as email_outbox
from app.models.commerce import EmailOutbox


def _settings(**overrides) -> SimpleNamespace:
    base = dict(
        email_available=True,
        email_dry_run=False,
        email_provider_api_key="test-key",
        email_from="conventions@parallax.test",
        email_provider_base_url="https://mail.example.test",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


async def _queue(db: AsyncSession, *, status: str = "queued", attempts: int = 0) -> EmailOutbox:
    row = EmailOutbox(
        recipient="attendee@example.com",
        template="registration_approved",
        payload={"registrationId": "PX-ABC123", "message": "Approved by the desk."},
        status=status,
        attempts=attempts,
        scheduled_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    db.add(row)
    await db.flush()
    return row


@pytest.mark.asyncio
async def test_enqueue_is_skipped_when_email_is_unavailable(db_session: AsyncSession):
    with patch.object(email_outbox, "get_settings", return_value=_settings(email_available=False)):
        result = await email_outbox.enqueue(
            db_session, recipient="a@example.com", template="registration_approved"
        )
    assert result is None
    count = await db_session.scalar(select(func.count()).select_from(EmailOutbox))
    assert count == 0


@pytest.mark.asyncio
async def test_queued_rows_become_sent_in_dry_run(db_session: AsyncSession):
    row = await _queue(db_session)
    with patch.object(email_outbox, "get_settings", return_value=_settings(email_dry_run=True)):
        sent = await email_outbox.send_batch(db_session)
    await db_session.refresh(row)
    assert sent >= 1
    assert row.status == "sent"
    assert row.sent_at is not None
    assert row.attempts == 1


@pytest.mark.asyncio
async def test_pending_status_is_picked_up(db_session: AsyncSession):
    row = await _queue(db_session, status="pending")
    with patch.object(email_outbox, "get_settings", return_value=_settings(email_dry_run=True)):
        await email_outbox.send_batch(db_session)
    await db_session.refresh(row)
    assert row.status == "sent"


@pytest.mark.asyncio
async def test_provider_failure_marks_failed_and_never_raises(db_session: AsyncSession):
    row = await _queue(db_session)

    class _Response:
        status_code = 500

        def raise_for_status(self):
            raise RuntimeError("provider exploded")

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            return _Response()

    with patch.object(email_outbox, "get_settings", return_value=_settings()):
        with patch.object(email_outbox.httpx, "AsyncClient", lambda **kwargs: _Client()):
            sent = await email_outbox.send_batch(db_session)

    await db_session.refresh(row)
    assert sent == 0
    assert row.status == "failed"
    assert row.attempts == 1
    assert row.last_error


@pytest.mark.asyncio
async def test_attempt_cap_is_respected(db_session: AsyncSession):
    row = await _queue(db_session, status="failed", attempts=email_outbox.MAX_ATTEMPTS)
    with patch.object(email_outbox, "get_settings", return_value=_settings(email_dry_run=True)):
        await email_outbox.send_batch(db_session)
    await db_session.refresh(row)
    assert row.status == "failed"
    assert row.attempts == email_outbox.MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_future_scheduled_rows_are_not_sent(db_session: AsyncSession):
    row = await _queue(db_session)
    row.scheduled_at = datetime.now(UTC) + timedelta(hours=1)
    await db_session.flush()
    with patch.object(email_outbox, "get_settings", return_value=_settings(email_dry_run=True)):
        await email_outbox.send_batch(db_session)
    await db_session.refresh(row)
    assert row.status == "queued"


def test_subject_and_body_cover_every_template():
    templates = [
        "verification_code",
        "registration_submitted",
        "registration_payment_success",
        "registration_approved",
        "registration_rejected",
        "registration_documents_correction",
        "registration_refund_initiated",
        "registration_refund_completed",
        "registration_refund_failed",
        "registration_update",
    ]
    for template in templates:
        assert email_outbox._subject(template) != "Parallax update"
        body = email_outbox._body(template, {"registrationId": "PX-1", "code": "123456"})
        assert "[object Object]" not in body
        if template != "verification_code":
            assert "PX-1" in body
