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
        created_at=datetime.now(UTC),
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
                .order_by(EmailOutbox.created_at)
                .limit(limit)
            )
        ).scalars()
    )
    sent = 0
    for row in rows:
        subject = _subject(row.template)
        body = _body(row.template, row.payload)
        row.attempts = (row.attempts or 0) + 1
        row.last_attempt_at = datetime.now(UTC)
        try:
            if settings.resend_api_key and settings.resend_configured:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        "https://api.resend.com/emails",
                        headers={"Authorization": f"Bearer {settings.resend_api_key}"},
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
            row.error_message = str(exc)[:255]
    await db.commit()
    return sent


def _subject(template: str) -> str:
    subjects = {
        "verification_code": "Your Parallax verification code",
        "pass_confirmed": "Your Parallax pass is confirmed",
        "registration_confirmed": "Parallax registration confirmed",
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

