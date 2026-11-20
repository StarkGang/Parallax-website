"""Transactional emails outbox: background dispatch or mock in dev."""

from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.commerce import EmailOutbox

logger = get_logger("email")


async def enqueue(
    db: AsyncSession,
    recipient: str,
    template: str,
    payload: dict[str, Any] | None = None,
) -> EmailOutbox:
    entry = EmailOutbox(
        recipient=recipient,
        template=template,
        payload=payload or {},
        status="queued",
    )
    db.add(entry)
    await db.flush()
    return entry


async def send_batch(db: AsyncSession, limit: int = 50) -> int:
    settings = get_settings()
    rows = list(
        (
            await db.execute(
                select(EmailOutbox)
                .where(EmailOutbox.status.in_(["queued", "failed"]))
                .order_by(EmailOutbox.scheduled_at)
                .limit(limit)
            )
        ).scalars()
    )
    if not rows:
        return 0
    if not settings.email_enabled:
        logger.info("email_dispatch_disabled", queued=len(rows))
        return 0
    if not settings.email_provider_api_key or not settings.email_from:
        message = "EMAIL_ENABLED requires EMAIL_PROVIDER_API_KEY and EMAIL_FROM"
        for row in rows:
            row.attempts = (row.attempts or 0) + 1
            row.status = "failed"
            row.last_error = message
        await db.commit()
        logger.error("email_provider_misconfigured")
        return 0

    sent = 0
    for row in rows:
        subject = _subject(row.template)
        body = _body(row.template, row.payload)
        row.attempts = (row.attempts or 0) + 1
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://api.resend.com/emails",
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
        except Exception as exc:
            logger.warning("email_send_failed", error=str(exc), recipient=row.recipient)
            row.status = "failed"
            row.last_error = str(exc)[:255]
    await db.commit()
    return sent


def _subject(template: str) -> str:
    subjects = {
        "verification_code": "Your Parallax verification code",
        "pass_confirmed": "Your Parallax pass is confirmed",
        "registration_confirmed": "Parallax registration confirmed",
        "registration_payment_success": "Parallax payment received",
        "registration_submitted": "Parallax registration submitted for verification",
        "registration_approved": "Your Parallax registration is approved",
        "registration_rejected": "Your Parallax registration needs attention",
        "registration_documents_correction": "Correct your Parallax registration documents",
        "registration_refund_initiated": "Your Parallax refund has been initiated",
        "registration_refund_completed": "Your Parallax refund is complete",
        "registration_refund_failed": "Your Parallax refund needs review",
        "refund_processed": "Your Parallax refund was processed",
    }
    return subjects.get(template, "Parallax update")


def _body(template: str, payload: dict[str, Any]) -> str:
    if template == "verification_code":
        return f"Your verification code is {payload.get('code', '')}. It expires in 10 minutes."
    if template == "pass_confirmed":
        return "Your convention pass is confirmed. Open the participant portal to view your entry QR."
    if template == "registration_confirmed":
        return f"Your registration for {payload.get('event_title', 'event')} is confirmed."
    if template == "refund_processed":
        return "Your refund has been processed."
    return payload.get("message", "Update from Parallax.")


__all__ = ["enqueue", "send_batch"]

