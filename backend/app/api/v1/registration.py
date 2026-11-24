"""Participant college registration: category, documents, payment, status and receipts."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Header, Query, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, current_context
from app.core.config import get_settings
from app.core.errors import AppError, NotFound
from app.core.rate_limit import limiter, memory_limiter
from app.core.text import safe_filename
from app.core.uploads import read_upload_limited
from app.db.session import get_db
from app.integrations.storage import get_document_storage
from app.models.commerce import PaymentOrder
from app.models.edition import ConventionEdition
from app.models.registration import RegistrationNotification
from app.schemas.registration import (
    CategoryChangeRequest,
    PaymentVerification,
    RegistrationProfile,
)
from app.services import college_registrations as service
from app.services import editions as edition_service
from app.services import idempotency as idempotency_service
from app.services import payments as payment_service

router = APIRouter(prefix="/editions/{edition_id}/registration", tags=["registration"])


async def _edition(db: AsyncSession, edition_id: uuid.UUID) -> ConventionEdition:
    return await edition_service.edition_by_id(db, edition_id)


@router.get(
    "",
    dependencies=[Depends(memory_limiter("registration_read", 120, 60))],
)
async def get_registration(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _edition(db, edition_id)
    await service.lazy_enforce_for_read(db, edition_id=edition_id)
    config = await service.public_config(db, edition_id)
    row = await service.registration_for_user(db, ctx.user.id, edition_id)
    notifications = [
        service.notification_payload(item)
        for item in await service.notifications_for(db, ctx.user.id, edition_id)
    ]
    return {
        "data": {
            **config,
            "registration": (
                await service.serialize_registration(db, row, include_documents=True)
                if row
                else None
            ),
            "notifications": notifications,
            "profileDefaults": {
                "fullName": ctx.user.full_name,
                "email": ctx.user.email,
                "phone": ctx.user.phone_e164,
            },
        }
    }


@router.put("/profile", dependencies=[Depends(limiter("registration_profile", 40, 60))])
async def save_profile(
    edition_id: uuid.UUID,
    payload: RegistrationProfile,
    request: Request,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    edition = await _edition(db, edition_id)
    row = await service.create_or_update_profile(
        db, request, ctx.user, edition, payload.model_dump()
    )
    await db.commit()
    return {"data": await service.serialize_registration(db, row)}


@router.post(
    "/documents/{doc_type}",
    dependencies=[Depends(limiter("registration_document", 30, 300))],
)
async def upload_document(
    edition_id: uuid.UUID,
    doc_type: str,
    request: Request,
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    edition = await _edition(db, edition_id)
    max_bytes = 102_400 if doc_type == "photo" else 512_000
    label = "Passport photo" if doc_type == "photo" else "Document"
    data = await read_upload_limited(file, max_bytes, label=label)
    document = await service.save_document(
        db,
        request,
        ctx.user,
        edition,
        doc_type,
        data,
        file.filename,
    )
    await db.commit()
    row = await service.registration_for_user(db, ctx.user.id, edition_id)
    assert row is not None
    return {
        "data": {
            "document": service.document_payload(document, edition_id, row.id),
            "registration": await service.serialize_registration(db, row),
        }
    }


@router.delete(
    "/documents/{doc_type}",
    dependencies=[Depends(limiter("registration_document_delete", 30, 300))],
)
async def delete_document(
    edition_id: uuid.UUID,
    doc_type: str,
    request: Request,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    edition = await _edition(db, edition_id)
    row = await service.delete_document(db, request, ctx.user, edition, doc_type)
    await db.commit()
    return {
        "data": {
            "registration": await service.serialize_registration(db, row),
        }
    }


@router.get(
    "/documents/{document_id}/content",
    dependencies=[Depends(memory_limiter("document_content", 120, 60))],
)
async def document_content(
    edition_id: uuid.UUID,
    document_id: uuid.UUID,
    download: bool = Query(default=False),
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> Response:
    document = await service.document_for_user(
        db, ctx.user.id, edition_id, document_id
    )
    try:
        data = await get_document_storage().get(document.storage_key)
    except FileNotFoundError:
        raise NotFound("The stored document could not be found.")
    disposition = "attachment" if download else "inline"
    filename = safe_filename(
        document.original_name, fallback=f"{document.doc_type}.bin"
    )
    return Response(
        content=data,
        media_type=document.mime,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; frame-ancestors 'self'",
        },
    )


@router.post("/submit", dependencies=[Depends(limiter("registration_submit", 10, 300))])
async def submit_registration(
    edition_id: uuid.UUID,
    request: Request,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    edition = await _edition(db, edition_id)
    settings = get_settings()
    if not settings.payments_enabled and not settings.is_development:
        raise AppError(
            "Online payments are not configured. Contact the organisers.",
            code="PAYMENTS_NOT_CONFIGURED",
            status_code=503,
        )
    # A retried or double-clicked submit must not create a second payable order.
    replay_payload = {"editionId": str(edition_id), "route": "submit"}
    cached = await idempotency_service.replay(
        db, ctx.user.id, "registration.submit", idempotency_key, replay_payload
    )
    if cached is not None:
        return cached[1]
    row, order = await service.submit_for_payment(db, request, ctx.user, edition)
    await db.commit()
    view = await service.serialize_registration(db, row)
    out = {
        "data": {
            "registration": view,
            "payment": (
                {
                    "orderId": str(order.id),
                    "amountPaise": order.amount_paise,
                    "gatewayOrderId": order.gateway_order_id,
                    "razorpayKeyId": settings.razorpay_key_id,
                    "mock": settings.mock_payments_available,
                }
                if order and order.status != "paid"
                else None
            ),
        }
    }
    await idempotency_service.store(
        db, ctx.user.id, "registration.submit", idempotency_key, replay_payload, out
    )
    await db.commit()
    return out


@router.post("/payment/verify", dependencies=[Depends(limiter("registration_payment_verify", 20, 60))])
async def verify_payment(
    edition_id: uuid.UUID,
    payload: PaymentVerification,
    request: Request,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await service.verify_checkout_payment(
        db,
        request,
        ctx.user,
        edition_id,
        order_id=payload.order_id,
        payment_id=payload.razorpay_payment_id,
        signature=payload.razorpay_signature,
    )
    await db.commit()
    return {"data": await service.serialize_registration(db, row)}


@router.get("/payments/{order_id}")
async def payment_status(
    edition_id: uuid.UUID,
    order_id: uuid.UUID,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    order = await payment_service.order_for(db, order_id)
    if order.user_id != ctx.user.id or order.edition_id != edition_id:
        raise NotFound("Payment order not found.")
    row = await service.registration_for_user(db, ctx.user.id, edition_id)
    return {
        "data": {
            "orderId": str(order.id),
            "status": order.status,
            "amountPaise": order.amount_paise,
            "purpose": order.purpose,
            "paidAt": edition_service.aware(order.paid_at).isoformat()
            if order.paid_at
            else None,
            "registration": (
                await service.serialize_registration(db, row) if row else None
            ),
        }
    }


@router.post(
    "/payments/{order_id}/mock",
    dependencies=[Depends(limiter("registration_mock_payment", 10, 60))],
)
async def mock_payment(
    edition_id: uuid.UUID,
    order_id: uuid.UUID,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    if not settings.mock_payments_available:
        raise NotFound("Mock payment is not available in this environment.")
    order = await payment_service.order_for(db, order_id)
    if (
        order.user_id != ctx.user.id
        or order.edition_id != edition_id
        or order.purpose
        not in {"college_registration", "college_registration_delta"}
    ):
        raise NotFound("Payment order not found.")
    await payment_service.mark_order_paid(
        db, order, transaction_id=payment_service.mock_payment_id()
    )
    await db.commit()
    row = await service.registration_for_user(db, ctx.user.id, edition_id)
    assert row is not None
    return {
        "data": {
            "paid": True,
            "orderId": str(order.id),
            "registration": await service.serialize_registration(db, row),
        }
    }


@router.post("/resubmit", dependencies=[Depends(limiter("registration_resubmit", 10, 300))])
async def resubmit(
    edition_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await service.resubmit(db, request, ctx.user, edition_id)
    await db.commit()
    return {"data": await service.serialize_registration(db, row)}


@router.post("/category-change", dependencies=[Depends(limiter("registration_category_change", 10, 300))])
async def request_category_change(
    edition_id: uuid.UUID,
    payload: CategoryChangeRequest,
    request: Request,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    if not settings.payments_enabled and not settings.is_development:
        raise AppError(
            "Category changes need online payments, which are not configured.",
            code="PAYMENTS_NOT_CONFIGURED",
            status_code=503,
        )
    change = await service.request_category_change(
        db, request, ctx.user, edition_id, payload.category_id, payload.note
    )
    await db.commit()
    return {"data": {"id": str(change.id), "status": change.status}}


@router.get("/category-change/payment")
async def category_change_payment(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await service.registration_for_user(db, ctx.user.id, edition_id)
    if row is None:
        raise NotFound("Registration not found.")
    change = await service.awaiting_change(db, row.id)
    if change is None or change.order_id is None:
        raise NotFound("No additional payment is pending.")
    order = await db.get(PaymentOrder, change.order_id)
    if order is None:
        raise NotFound("Payment order not found.")
    settings = get_settings()
    return {
        "data": {
            "orderId": str(order.id),
            "amountPaise": order.amount_paise,
            "gatewayOrderId": order.gateway_order_id,
            "razorpayKeyId": settings.razorpay_key_id,
            "mock": settings.mock_payments_available,
            "status": order.status,
        }
    }


@router.post(
    "/notifications/{notification_id}/read",
    dependencies=[Depends(limiter("notification_read", 60, 60))],
)
async def mark_notification_read(
    edition_id: uuid.UUID,
    notification_id: uuid.UUID,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await db.get(RegistrationNotification, notification_id)
    if (
        row is None
        or row.user_id != ctx.user.id
        or row.edition_id != edition_id
    ):
        raise NotFound("Notification not found.")
    row.read_at = row.read_at or datetime.now(UTC)
    await db.commit()
    return {"data": {"read": True}}


async def _qr_payload(
    ctx: AuthContext, edition_id: uuid.UUID, request: Request, db: AsyncSession
) -> str:
    """Text the participant's pass QR must contain.

    The server decides *what* the code says (a signed token); drawing the code
    is a frontend concern, so no SVG is generated or served here.
    """
    from app.services import tickets as ticket_service

    row = await service.registration_for_user(db, ctx.user.id, edition_id)
    base_url = ticket_service.entry_base_url(str(request.base_url).rstrip("/"))
    # One definition, shared with the ID card studio: paid means the pass ticket,
    # otherwise the signed public code.
    token = await ticket_service.registration_entry_payload(db, row, base_url=base_url)
    if token:
        return token
    # Nothing issued yet: the portal still shows a code for the desk to read,
    # signed so the public page cannot be enumerated.
    reg_num = (
        row.registration_number
        if row and row.registration_number
        else f"PRX-{str(ctx.user.id)[:6].upper()}"
    )
    return f"{base_url}/c/{ticket_service.public_registration_code(reg_num)}"


@router.get(
    "/qr-token",
    dependencies=[Depends(memory_limiter("registration_qr", 60, 60))],
)
async def registration_qr_token(
    edition_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the signed payload for the pass QR so the browser draws it."""
    return {"data": {"payload": await _qr_payload(ctx, edition_id, request, db)}}


@router.get("/pass-card")
async def pass_card(
    edition_id: uuid.UUID,
) -> RedirectResponse:
    """Redirect to the frontend portal where the ID card is rendered interactively."""
    return RedirectResponse(url="/portal/registration", status_code=303)


@router.get("/receipt")
async def receipt(
    edition_id: uuid.UUID,
) -> RedirectResponse:
    """Redirect to the frontend portal where the receipt is rendered interactively."""
    return RedirectResponse(url="/portal/registration", status_code=303)


@router.get("/confirmation")
async def confirmation(
    edition_id: uuid.UUID,
) -> RedirectResponse:
    """Redirect to the frontend portal where the confirmation is rendered interactively."""
    return RedirectResponse(url="/portal/registration", status_code=303)


__all__ = ["router"]
