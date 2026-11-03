"""Razorpay webhook: signature is checked against the raw body before parsing."""

import json
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
    x_razorpay_signature: str = Header(..., alias="X-Razorpay-Signature"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    settings = get_settings()
    body = await request.body()

    if settings.razorpay_webhook_secret:
        valid = verify_webhook_signature(
            body, x_razorpay_signature, settings.razorpay_webhook_secret
        )
        if not valid:
            security_event("webhook_signature_invalid")
            return JSONResponse({"status": "invalid signature"}, status_code=400)

    try:
        payload = json.loads(body)
    except Exception:
        return JSONResponse({"status": "invalid json"}, status_code=400)

    event_id = payload.get("event_id") or payload.get("id") or "evt_unknown"
    await process_webhook(db, payload, event_id=event_id)
    await db.commit()
    return JSONResponse({"status": "ok"})


__all__ = ["router"]

