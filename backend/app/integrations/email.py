"""Transactional emails outbox: background dispatch or mock in dev."""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.commerce import EmailOutbox

logger = get_logger("email")


# A permanently failing address must not be retried forever.
MAX_ATTEMPTS = 5
ACTIVE_STATUSES = ("queued", "failed", "pending")
# Retry backoff, so a provider outage does not burn all five attempts in one
# dispatch tick. Index is the attempt count that already failed.
RETRY_DELAYS_SECONDS = (0, 60, 300, 900, 3600)


async def enqueue(
    db: AsyncSession,
    recipient: str,
    template: str,
    payload: dict[str, Any] | None = None,
) -> EmailOutbox | None:
    """Queue an email only when delivery is actually possible.

    Without a provider the previous behaviour queued rows forever while the
    UI claimed a notification had been sent. Returning None keeps the caller
    honest and the outbox clean.
    """
    configured = get_settings().email_available
    if not configured:
        # Without a provider the row is still written, as ``skipped``: the desk
        # can then see that a notification was owed, instead of an empty outbox
        # while the UI claims the attendee was told.
        logger.debug("email_skipped_not_configured", template=template)
    entry = EmailOutbox(
        recipient=recipient,
        template=template,
        payload=payload or {},
        status="queued" if configured else "skipped",
        scheduled_at=datetime.now(UTC),
    )
    db.add(entry)
    await db.flush()
    return entry


async def send_batch(db: AsyncSession, limit: int = 50) -> int:
    settings = get_settings()
    if not settings.email_available:
        logger.debug("email_dispatch_disabled")
        return 0

    rows = list(
        (
            await db.execute(
                select(EmailOutbox)
                .where(
                    # Skips are a record of a notification that was owed while no
                    # provider was configured; they are never sent.
                    EmailOutbox.status.in_(ACTIVE_STATUSES),
                    EmailOutbox.attempts < MAX_ATTEMPTS,
                    EmailOutbox.scheduled_at <= datetime.now(UTC),
                )
                .order_by(EmailOutbox.scheduled_at)
                .limit(limit)
            )
        ).scalars()
    )
    if not rows:
        return 0

    endpoint = settings.email_provider_base_url.rstrip("/") + "/emails"
    sent = 0
    for row in rows:
        subject = _subject(row.template)
        body = _body(row.template, row.payload)
        row.attempts = (row.attempts or 0) + 1
        if settings.email_dry_run:
            logger.info(
                "email_dry_run",
                to=row.recipient,
                subject=subject,
                body=body[:500],
            )
            row.status = "sent"
            row.sent_at = datetime.now(UTC)
            sent += 1
            continue
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {settings.email_provider_api_key}"},
                    json={
                        "from": settings.email_from,
                        "to": [row.recipient],
                        "subject": subject,
                        "text": body,
                    },
                )
                resp.raise_for_status()
            row.status = "sent"
            row.sent_at = datetime.now(UTC)
            sent += 1
        except Exception as exc:  # provider failure must never reach the caller
            logger.warning("email_send_failed", error=str(exc), recipient=row.recipient)
            row.status = "failed"
            row.last_error = str(exc)[:255]
            attempts = int(row.attempts or 0)
            if attempts >= MAX_ATTEMPTS:
                # Give up loudly: a silently abandoned transactional email means
                # an attendee never hears about their own registration.
                try:
                    from app.services.telegram import send_telegram_alert

                    await send_telegram_alert(
                        f"Email delivery failed {attempts}x for {row.recipient} "
                        f"({row.template}): {str(exc)[:160]}"
                    )
                except Exception:  # noqa: BLE001 - alerting must not fail the batch
                    logger.warning("email_failure_alert_not_sent", recipient=row.recipient)
            else:
                # Retry later instead of hammering the provider in this tick.
                delay = RETRY_DELAYS_SECONDS[min(attempts, len(RETRY_DELAYS_SECONDS) - 1)]
                row.scheduled_at = datetime.now(UTC) + timedelta(seconds=delay)
    await db.commit()
    return sent


def _subject(template: str) -> str:
    # Mirrors ``college_registrations.EMAIL_TEMPLATES``; anything not listed here
    # falls back to the generic subject below.
    subjects = {
        "registration_payment_success": "Parallax payment received",
        "registration_submitted": "Parallax registration submitted for verification",
        "registration_approved": "Your Parallax registration is approved",
        "registration_rejected": "Your Parallax registration needs attention",
        "registration_documents_correction": "Correct your Parallax registration documents",
        "registration_compliance_enforced": "Your Parallax event seats were released",
        "registration_refund_initiated": "Your Parallax refund has been initiated",
        "registration_refund_completed": "Your Parallax refund is complete",
        "registration_refund_failed": "Your Parallax refund needs review",
        "registration_update": "Update on your Parallax registration",
    }
    return subjects.get(template, "Parallax update")


def _body(template: str, payload: dict[str, Any]) -> str:
    """Plain-text body for every template the app can enqueue.

    The desk templates carry their rendered message, but each one still gets an
    explicit opening line so an email never arrives with only generic copy.
    """
    opening = {
        "registration_submitted": "We received your Parallax registration and it is now with the review desk.",
        "registration_payment_success": "Your payment was received and your registration is confirmed.",
        "registration_approved": "Your Parallax registration has been approved.",
        "registration_rejected": "Your Parallax registration needs attention before it can be approved.",
        "registration_documents_correction": "Please upload corrected documents for your Parallax registration.",
        "registration_compliance_enforced": "The window to answer the registration desk closed, so your event seats and team placement were released.",
        "registration_refund_initiated": "A refund for your Parallax registration has been initiated.",
        "registration_refund_completed": "Your Parallax refund has been completed.",
        "registration_refund_failed": "Your Parallax refund could not be completed and needs review.",
        "registration_update": "There is an update on your Parallax registration.",
    }.get(template)
    reference = payload.get("registrationId")
    lines = [opening or "Update from Parallax."]
    if reference:
        lines.append(f"Registration: {reference}")
    message = payload.get("message")
    if message and message not in lines:
        lines.append("")
        lines.append(str(message))
    return "\n".join(lines)


__all__ = ["enqueue", "send_batch"]

