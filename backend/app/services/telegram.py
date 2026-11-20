"""Telegram Bot notification service for Parallax 2027."""

from __future__ import annotations

import html
import io
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

    if not bot_token or not chat_id:
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

    if not bot_token or not chat_id:
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

