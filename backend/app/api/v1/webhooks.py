"""Razorpay webhook: signature is checked against the raw body before parsing."""

import json
import hashlib
from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger, security_event
from app.db.session import get_db
from app.services.payments import process_webhook, verify_webhook_signature

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = get_logger("webhooks")


@router.post("/razorpay")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str | None = Header(None, alias="X-Razorpay-Signature"),
    x_razorpay_event_id: str | None = Header(None, alias="X-Razorpay-Event-Id"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    settings = get_settings()
    if request.headers.get("content-length") and int(request.headers["content-length"]) > settings.max_request_body_bytes:
        return JSONResponse({"status": "payload too large"}, status_code=413)
    body = await request.body()
    if len(body) > settings.max_request_body_bytes:
        return JSONResponse({"status": "payload too large"}, status_code=413)

    if not settings.razorpay_webhook_secret:
        return JSONResponse({"status": "webhook secret is not configured"}, status_code=503)
    if not x_razorpay_signature or not verify_webhook_signature(
        body, x_razorpay_signature, settings.razorpay_webhook_secret
    ):
        security_event("webhook_signature_invalid")
        return JSONResponse({"status": "invalid signature"}, status_code=400)

    try:
        payload = json.loads(body)
    except Exception:
        return JSONResponse({"status": "invalid json"}, status_code=400)

    event_id = x_razorpay_event_id or hashlib.sha256(body).hexdigest()
    await process_webhook(db, payload, event_id=event_id)
    await db.commit()
    return JSONResponse({"status": "ok"})


__all__ = ["router"]

