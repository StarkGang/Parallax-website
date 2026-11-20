"""Telegram Bot notification service for Parallax 2027."""

from __future__ import annotations

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
    chat_id = settings.telegram_chat_id

    if not bot_token or not chat_id:
        logger.info(
            "telegram_notification_skipped",
            reason="BOT_TOKEN or TELEGRAM_CHAT_ID not configured in environment.",
        )
        return {"sent": False, "reason": "not_configured"}

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    clean_ip = ip or "Unknown"

    # HTML formatted message
    html_text = (
        f"📬 <b>New Parallax 2027 Message Received</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>From:</b> {name}\n"
        f"📧 <b>Email:</b> {email}\n"
        f"🏷 <b>Category:</b> {category}\n"
        f"⏰ <b>Received:</b> {now_utc}\n"
        f"🌐 <b>Origin IP:</b> {clean_ip}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💬 <b>Message Content:</b>\n"
        f"{message}"
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
                        "disable_web_page_preview": True,
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
                    f"PARALLAX 2026 INQUIRY DISPATCH\n"
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
                    f"📬 <b>Long Inquiry from {name}</b>\n"
                    f"Email: {email} | Category: {category}\n"
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

