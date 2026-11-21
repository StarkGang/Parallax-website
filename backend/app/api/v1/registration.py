"""Participant college registration: category, documents, payment, status and receipts."""

from __future__ import annotations

import html
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, current_context
from app.core.config import get_settings
from app.core.errors import AppError, Conflict, NotFound
from app.core.rate_limit import limiter
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
from app.services import payments as payment_service

router = APIRouter(prefix="/editions/{edition_id}/registration", tags=["registration"])


async def _edition(db: AsyncSession, edition_id: uuid.UUID) -> ConventionEdition:
    return await edition_service.edition_by_id(db, edition_id)


@router.get("")
async def get_registration(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _edition(db, edition_id)
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
    data = await read_upload_limited(file, 512_000, label="Document")
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


@router.get("/documents/{document_id}/content")
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
    row, order = await service.submit_for_payment(db, request, ctx.user, edition)
    await db.commit()
    view = await service.serialize_registration(db, row)
    return {
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
                if order
                else None
            ),
        }
    }


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


def _receipt_html(
    row,
    *,
    title: str,
    confirmation: bool,
    instructions: str | None,
    refund_policy: str | None,
) -> str:
    paid_at = (
        edition_service.aware(row.paid_at).strftime("%d %b %Y, %H:%M UTC")
        if row.paid_at
        else "-"
    )
    amount = f"INR {(row.fee_paise + (row.additional_paid_paise or 0)) / 100:,.2f}"
    safe = lambda value: html.escape(str(value or "-"))  # noqa: E731
    status_note = (
        "Your documents have been verified and your registration is approved."
        if confirmation
        else "Your payment is received. Your seat is confirmed only after the registration desk verifies your documents."
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<title>{html.escape(title)} · {safe(row.registration_number)}</title>
<style>
body{{font-family:ui-sans-serif,system-ui,Segoe UI,Roboto,sans-serif;background:#071018;color:#e8f4ff;margin:0;padding:40px}}
.card{{max-width:720px;margin:0 auto;border:1px solid #1c3b52;border-radius:18px;padding:32px;background:#0b1a26}}
h1{{font-size:22px;letter-spacing:.08em;text-transform:uppercase;margin:0 0 4px;color:#38bdf8}}
p.sub{{color:#8fb0c6;margin:0 0 24px}} table{{width:100%;border-collapse:collapse;margin:16px 0}}
td{{padding:9px 0;border-bottom:1px solid #163246;font-size:14px}} td:first-child{{color:#8fb0c6;width:44%}}
.total{{font-size:18px;color:#38bdf8}} .note{{font-size:13px;color:#8fb0c6;line-height:1.6;margin-top:18px}}
.badge{{display:inline-block;padding:4px 10px;border-radius:99px;border:1px solid #38bdf8;color:#38bdf8;font-size:11px;letter-spacing:.1em;text-transform:uppercase}}
</style></head>
<body><div class="card">
<span class="badge">{'Registration confirmation' if confirmation else 'Payment receipt'}</span>
<h1>{html.escape(title)}</h1>
<p class="sub">PARALLAX · ISTE State Student Convention</p>
<table>
<tr><td>Registration ID</td><td><b>{safe(row.registration_number)}</b></td></tr>
<tr><td>Participant</td><td>{safe(row.full_name)}<br/><span style="color:#8fb0c6">{safe(row.email)}</span></td></tr>
<tr><td>College</td><td>{safe(row.college_name)}</td></tr>
<tr><td>Category</td><td>{safe(row.category_name)}</td></tr>
<tr><td>Payment transaction</td><td>{safe(row.transaction_id)}</td></tr>
<tr><td>Paid on</td><td>{paid_at}</td></tr>
<tr><td>Payment status</td><td>{safe(row.payment_status)}</td></tr>
<tr><td>Verification status</td><td>{safe(row.verification_status)}</td></tr>
<tr><td class="total">Amount paid</td><td class="total">{amount}</td></tr>
</table>
<p class="note">{html.escape(status_note)}</p>
{ f'<p class="note"><b>Payment instructions:</b> {html.escape(instructions)}</p>' if instructions else '' }
{ f'<p class="note"><b>Refund policy:</b> {html.escape(refund_policy)}</p>' if refund_policy else '' }
<p class="note">This document is generated from the Parallax registration database. Amounts are in INR and include all applicable taxes.</p>
</div></body></html>"""


async def _receipt_response(
    ctx: AuthContext,
    db: AsyncSession,
    edition_id: uuid.UUID,
    *,
    confirmation: bool,
) -> Response:
    row = await service.registration_for_user(db, ctx.user.id, edition_id)
    if row is None:
        raise NotFound("Registration not found.")
    if confirmation and row.verification_status != "approved":
        raise Conflict(
            "Your registration is not approved yet, so a confirmation cannot be issued.",
            code="NOT_APPROVED",
        )
    if row.payment_status not in {"paid", "refunded"}:
        raise Conflict("A receipt is available only after payment.", code="PAYMENT_REQUIRED")
    db_settings = await service.settings_for(db, edition_id)
    title = "Registration confirmation" if confirmation else "Payment receipt"
    body = _receipt_html(
        row,
        title=title,
        confirmation=confirmation,
        instructions=db_settings.payment_instructions if db_settings else None,
        refund_policy=db_settings.refund_policy if db_settings else None,
    )
    filename = f"{'confirmation' if confirmation else 'receipt'}-{row.registration_number or row.id}.html"
    return HTMLResponse(
        content=body,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/receipt")
async def receipt(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> Response:
    return await _receipt_response(ctx, db, edition_id, confirmation=False)


@router.get("/confirmation")
async def confirmation(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> Response:
    return await _receipt_response(ctx, db, edition_id, confirmation=True)


__all__ = ["router"]
