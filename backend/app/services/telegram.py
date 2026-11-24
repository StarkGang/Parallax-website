"""Telegram Bot notification service for Parallax 2027."""

from __future__ import annotations

import asyncio
import html
import io
import time
import logging
from datetime import datetime, timezone
import structlog
import httpx

from app.core.config import get_settings

logger = structlog.get_logger()

# Telegram text messages cannot exceed 4096 characters
TELEGRAM_MAX_TEXT_LEN = 4000


async def send_telegram_inquiry(
    name: str,
    email: str,
    category: str,
    message: str,
    ip: str | None = None,
) -> dict:
    """Send an inquiry notification to the organizing team via Telegram Bot API.

    If the formatted message exceeds Telegram's 4000 character limit, it is
    automatically sent as a text document attachment.
    """
    settings = get_settings()
    bot_token = settings.effective_telegram_bot_token
    chat_id = settings.effective_telegram_chat_id

    if not bot_token or not chat_id or settings.is_test:
        logger.info(
            "telegram_notification_skipped",
            reason="BOT_TOKEN or TELEGRAM_CHAT_ID not configured in environment.",
        )
        return {"sent": False, "reason": "not_configured"}

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    clean_ip = ip or "Unknown"

    # HTML-escape user inputs so reserved characters like &, <, > don't break Telegram HTML parser
    safe_name = html.escape(name or "Anonymous")
    safe_email = html.escape(email or "No email")
    safe_category = html.escape(category or "General")
    safe_message = html.escape(message or "")

    # HTML formatted message
    html_text = (
        f"📬 <b>New Parallax 2027 Message Received</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>From:</b> {safe_name}\n"
        f"📧 <b>Email:</b> {safe_email}\n"
        f"🏷 <b>Category:</b> {safe_category}\n"
        f"⏰ <b>Received:</b> {now_utc}\n"
        f"🌐 <b>Origin IP:</b> {clean_ip}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💬 <b>Message Content:</b>\n"
        f"{safe_message}"
    )

    base_url = f"https://api.telegram.org/bot{bot_token}"

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            if len(html_text) <= TELEGRAM_MAX_TEXT_LEN:
                # Send standard text message
                res = await client.post(
                    f"{base_url}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": html_text,
                        "parse_mode": "HTML",
                        "link_preview_options": {"is_disabled": True},
                    },
                )
                res_data = res.json()
                if not res_data.get("ok"):
                    logger.warning(
                        "telegram_send_message_error",
                        status_code=res.status_code,
                        response=res_data,
                    )
                    return {"sent": False, "error": res_data.get("description")}
                return {"sent": True, "method": "text", "message_id": res_data.get("result", {}).get("message_id")}
            else:
                # Exceeds limit: upload as document file with metadata caption
                file_content = (
                    f"PARALLAX 2027 INQUIRY DISPATCH\n"
                    f"==============================\n"
                    f"From:     {name}\n"
                    f"Email:    {email}\n"
                    f"Category: {category}\n"
                    f"Time:     {now_utc}\n"
                    f"IP:       {clean_ip}\n"
                    f"Length:   {len(message)} characters\n"
                    f"==============================\n\n"
                    f"FULL MESSAGE:\n"
                    f"{message}\n"
                ).encode("utf-8")

                caption = (
                    f"📬 <b>Long Inquiry from {safe_name}</b>\n"
                    f"Email: {safe_email} | Category: {safe_category}\n"
                    f"Message exceeds {TELEGRAM_MAX_TEXT_LEN} chars. Full text attached."
                )

                files = {
                    "document": ("inquiry_message.txt", io.BytesIO(file_content), "text/plain; charset=utf-8")
                }
                data = {
                    "chat_id": chat_id,
                    "caption": caption[:1024],
                    "parse_mode": "HTML",
                }

                res = await client.post(f"{base_url}/sendDocument", data=data, files=files)
                res_data = res.json()
                if not res_data.get("ok"):
                    logger.warning(
                        "telegram_send_document_error",
                        status_code=res.status_code,
                        response=res_data,
                    )
                    return {"sent": False, "error": res_data.get("description")}
                return {"sent": True, "method": "document", "message_id": res_data.get("result", {}).get("message_id")}

    except Exception as exc:
        logger.warning("telegram_dispatch_failed", error=str(exc))
        return {"sent": False, "error": str(exc)}


async def send_telegram_registration(
    full_name: str,
    email: str,
    phone: str,
    college: str,
    tier_name: str,
    amount_paid: str,
    reference: str,
) -> dict:
    """Send a real-time alert to the organizing desk when an attendee purchases a convention pass."""
    settings = get_settings()
    bot_token = settings.effective_telegram_bot_token
    chat_id = settings.effective_telegram_chat_id

    if not bot_token or not chat_id or settings.is_test:
        return {"sent": False, "reason": "not_configured"}

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # HTML-escape user registration details
    safe_name = html.escape(full_name or "Attendee")
    safe_email = html.escape(email or "")
    safe_phone = html.escape(phone or "")
    safe_college = html.escape(college or "College Student")
    safe_tier = html.escape(tier_name or "Convention Pass")
    safe_ref = html.escape(reference or "")

    html_text = (
        f"🎟 <b>New Parallax 2027 Pass Purchased!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Attendee:</b> {safe_name}\n"
        f"📧 <b>Email:</b> {safe_email}\n"
        f"📱 <b>Phone:</b> {safe_phone}\n"
        f"🏛 <b>College:</b> {safe_college}\n"
        f"🏷 <b>Tier:</b> {safe_tier}\n"
        f"💰 <b>Amount:</b> {amount_paid}\n"
        f"🆔 <b>Ref:</b> <code>{safe_ref}</code>\n"
        f"⏰ <b>Time:</b> {now_utc}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
    base_url = f"https://api.telegram.org/bot{bot_token}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(
                f"{base_url}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": html_text,
                    "parse_mode": "HTML",
                    "link_preview_options": {"is_disabled": True},
                },
            )
            return {"sent": res.is_success, "status_code": res.status_code}
    except Exception as exc:
        logger.warning("telegram_registration_alert_failed", error=str(exc))
        return {"sent": False, "error": str(exc)}


_payment_alerts_seen: dict[str, float] = {}


async def send_telegram_payment_notification(
    event_type: str,  # 'initiated' | 'success' | 'failed'
    order_id: str,
    amount_paise: int,
    purpose: str,
    payment_id: str | None = None,
    gateway_order_id: str | None = None,
    attendee_name: str | None = None,
    attendee_email: str | None = None,
    error_message: str | None = None,
) -> dict:
    """Send real-time payment alerts (initiated, success, failed) to Telegram with deduplication and low timeout."""
    settings = get_settings()
    bot_token = settings.effective_telegram_bot_token
    chat_id = settings.effective_telegram_chat_id
    if not bot_token or not chat_id or settings.is_test:
        return {"sent": False, "reason": "not_configured"}

    # Deduplicate: prevent spamming duplicate alerts for the same order and event
    dedup_key = f"{order_id}:{event_type}"
    now = time.monotonic()
    if dedup_key in _payment_alerts_seen:
        if now - _payment_alerts_seen[dedup_key] < 300.0:
            return {"sent": False, "reason": "duplicate_suppressed"}
    _payment_alerts_seen[dedup_key] = now
    if len(_payment_alerts_seen) > 300:
        for k in list(_payment_alerts_seen)[:150]:
            _payment_alerts_seen.pop(k, None)

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    amount_inr = f"₹{amount_paise / 100:.2f}" if amount_paise else "₹0.00"

    safe_name = html.escape(attendee_name or "Attendee")
    safe_email = html.escape(attendee_email or "")
    safe_purpose = html.escape(purpose.replace("_", " ").title())
    safe_order_id = html.escape(str(order_id))
    safe_gateway_order = html.escape(str(gateway_order_id or "—"))
    safe_pay_id = html.escape(str(payment_id or "—"))

    if event_type == "initiated":
        header = "💳 <b>Payment Initiated</b>"
        body = (
            f"👤 <b>Attendee:</b> {safe_name}\n"
            f"📧 <b>Email:</b> {safe_email}\n"
            f"💰 <b>Amount:</b> {amount_inr}\n"
            f"🎯 <b>Purpose:</b> {safe_purpose}\n"
            f"📦 <b>Order ID:</b> <code>{safe_order_id}</code>\n"
            f"🌐 <b>Gateway Order:</b> <code>{safe_gateway_order}</code>\n"
            f"⏰ <b>Started At:</b> {now_utc}"
        )
    elif event_type == "success":
        header = "✅ <b>Payment Successful</b>"
        body = (
            f"👤 <b>Attendee:</b> {safe_name}\n"
            f"📧 <b>Email:</b> {safe_email}\n"
            f"💰 <b>Amount:</b> {amount_inr}\n"
            f"🎯 <b>Purpose:</b> {safe_purpose}\n"
            f"🆔 <b>Payment ID:</b> <code>{safe_pay_id}</code>\n"
            f"📦 <b>Order ID:</b> <code>{safe_order_id}</code>\n"
            f"⏰ <b>Confirmed At:</b> {now_utc}"
        )
    elif event_type == "failed":
        safe_err = html.escape(str(error_message or "Bank declined or transaction cancelled")[:200])
        header = "⚠️ <b>Payment Attempt Failed</b>"
        body = (
            f"👤 <b>Attendee:</b> {safe_name}\n"
            f"💰 <b>Amount:</b> {amount_inr}\n"
            f"🎯 <b>Purpose:</b> {safe_purpose}\n"
            f"🆔 <b>Payment ID:</b> <code>{safe_pay_id}</code>\n"
            f"📦 <b>Order ID:</b> <code>{safe_order_id}</code>\n"
            f"❌ <b>Reason:</b> {safe_err}\n"
            f"⏰ <b>Failed At:</b> {now_utc}"
        )
    else:
        return {"sent": False, "reason": "unknown_event_type"}

    text = f"{header}\n━━━━━━━━━━━━━━━━━━━━━━\n{body}\n━━━━━━━━━━━━━━━━━━━━━━"
    base_url = f"https://api.telegram.org/bot{bot_token}"

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            res = await client.post(
                f"{base_url}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "link_preview_options": {"is_disabled": True},
                },
            )
            return {"sent": res.is_success, "status_code": res.status_code}
    except Exception as exc:
        logger.warning("telegram_payment_notification_failed", error=str(exc))
        return {"sent": False, "error": str(exc)}


def dispatch_payment_telegram_alert(
    event_type: str,
    order_id: str,
    amount_paise: int,
    purpose: str,
    payment_id: str | None = None,
    gateway_order_id: str | None = None,
    attendee_name: str | None = None,
    attendee_email: str | None = None,
    error_message: str | None = None,
) -> None:
    """Non-blocking, deduplicated payment dispatch suitable for Vercel/serverless environments."""
    async def _safe_dispatch_runner() -> None:
        try:
            res = await send_telegram_payment_notification(
                event_type=event_type,
                order_id=order_id,
                amount_paise=amount_paise,
                purpose=purpose,
                payment_id=payment_id,
                gateway_order_id=gateway_order_id,
                attendee_name=attendee_name,
                attendee_email=attendee_email,
                error_message=error_message,
            )
            if not res.get("sent"):
                logger.warning(
                    "telegram_payment_alert_not_sent",
                    event_type=event_type,
                    order_id=order_id,
                    reason=res.get("reason") or res.get("error"),
                )
        except Exception as exc:
            logger.error(
                "telegram_payment_alert_background_exception",
                event_type=event_type,
                order_id=order_id,
                error=str(exc),
                exc_info=True,
            )

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(
            _safe_dispatch_runner(),
            name="parallax-payment-telegram-alert",
        )
    except Exception as exc:
        logger.error(
            "telegram_payment_dispatch_scheduling_failed",
            event_type=event_type,
            order_id=order_id,
            error=str(exc),
            exc_info=True,
        )



# ---------------------------------------------------------------------------
# Operational alerting
#
# Critical events (failed payments, unhandled server errors, security notices)
# are pushed to the same organizing channel as the attendee alerts. Sending is
# best-effort: a missing token, a network error or a flood of duplicate logs
# must never break a request.
# ---------------------------------------------------------------------------

_ALERT_MIN_GAP_SECONDS = 1.5
_ALERT_REPEAT_WINDOW_SECONDS = 300.0
_ALERT_FP_MAX = 400
_last_alert_sent_at = 0.0
_seen_alerts: dict[str, float] = {}

_SEVERITY_MARK = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}


async def send_telegram_alert(
    title: str,
    fields: dict[str, object] | None = None,
    severity: str = "info",
    footer: str | None = None,
) -> dict:
    """Post an operational alert to the organizing Telegram channel."""
    settings = get_settings()
    bot_token = settings.effective_telegram_bot_token
    chat_id = settings.effective_telegram_chat_id
    if not bot_token or not chat_id or settings.is_test:
        return {"sent": False, "reason": "not_configured"}

    lines = [
        f"{_SEVERITY_MARK.get(severity, 'ℹ️')} <b>{html.escape(str(title))}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for key, value in (fields or {}).items():
        lines.append(f"• <b>{html.escape(str(key))}:</b> {html.escape(str(value))}")
    lines.append(f"⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    if footer:
        lines.append(f"<i>{html.escape(footer)}</i>")

    text = "\n".join(lines)[:TELEGRAM_MAX_TEXT_LEN]
    base_url = f"https://api.telegram.org/bot{bot_token}"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.post(
                f"{base_url}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "link_preview_options": {"is_disabled": True},
                },
            )
            return {"sent": res.is_success, "status_code": res.status_code}
    except Exception as exc:
        logger.warning("telegram_alert_failed", error=str(exc))
        return {"sent": False, "error": str(exc)}


def file_telegram_alert(
    title: str,
    fields: dict[str, object] | None = None,
    severity: str = "info",
    footer: str | None = None,
) -> None:
    """Fire-and-forget alert: throttled, de-duplicated and never blocking."""
    global _last_alert_sent_at

    settings = get_settings()
    if (
        not settings.effective_telegram_bot_token
        or not settings.effective_telegram_chat_id
        or settings.is_test
    ):
        return

    now = time.monotonic()
    fingerprint = f"{title}|{sorted((fields or {}).items())}"[:_ALERT_FP_MAX]
    last_seen = _seen_alerts.get(fingerprint)
    if last_seen is not None and now - last_seen < _ALERT_REPEAT_WINDOW_SECONDS:
        return
    if now - _last_alert_sent_at < _ALERT_MIN_GAP_SECONDS:
        return

    _seen_alerts[fingerprint] = now
    _last_alert_sent_at = now
    if len(_seen_alerts) > 200:
        for key in list(_seen_alerts)[:100]:
            _seen_alerts.pop(key, None)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No event loop (sync context such as a CLI script): drop the alert.
        return

    loop.create_task(
        send_telegram_alert(title, fields, severity=severity, footer=footer),
        name="parallax-telegram-alert",
    )


class TelegramLogHandler(logging.Handler):
    """Forwards ERROR+ application logs to Telegram.

    Deduplication and throttling live in ``file_telegram_alert`` so a failing
    dependency cannot flood the channel.
    """

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - IO path
        try:
            if record.levelno < logging.ERROR:
                return
            message = record.getMessage()
            file_telegram_alert(
                f"{record.levelname} · {record.name}",
                {
                    "event": message[:700],
                    "module": f"{record.module}:{record.lineno}",
                },
                severity="critical" if record.levelno >= logging.CRITICAL else "warning",
            )
        except Exception:
            pass
