"""Admin registration desk: verification queue, documents, refunds and configuration."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_permission
from app.core.text import safe_filename
from app.core.errors import Conflict, NotFound
from app.db.session import get_db
from app.integrations.storage import get_document_storage
from app.schemas.registration import (
    AdminRegistrationDetailsUpdate,
    CategoryChangeDecision,
    RefundAction,
    RegistrationConfigUpdate,
    RegistrationDecision,
    RegistrationNote,
    RequestDocuments,
)
from app.services import college_registrations as service

router = APIRouter(
    prefix="/editions/{edition_id}/admin/registration", tags=["admin-registration"]
)


def _role(ctx: AuthContext, edition_id: uuid.UUID) -> str:
    return ctx.role_for(edition_id) or (ctx.roles[0] if ctx.roles else "super_admin")


@router.get("/config")
async def get_config(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    config = await service.public_config(db, edition_id)
    return {"data": config}


@router.patch("/config")
async def update_config(
    edition_id: uuid.UUID,
    payload: RegistrationConfigUpdate,
    request: Request,
    ctx: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    data = payload.model_dump(exclude_unset=True)
    settings_update = data.get("settings")
    if settings_update is not None:
        # An explicit null date is meaningful (clear the window), so keep keys
        # that were supplied but let the service validate their order.
        settings_update = payload.settings.model_dump(exclude_unset=True) if payload.settings else None
    categories = {
        code: (item.model_dump(exclude_unset=True) if hasattr(item, "model_dump") else item)
        for code, item in (payload.categories or {}).items()
    }
    result = await service.update_config(
        db,
        request,
        edition_id,
        ctx.user,
        _role(ctx, edition_id),
        settings_update=settings_update,
        category_updates=categories,
    )
    await db.commit()
    config = await service.public_config(db, edition_id)
    return {"data": {"result": result, **config}}


@router.get("")
async def list_registrations(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("registration.read")),
    db: AsyncSession = Depends(get_db),
    category: str | None = None,
    verification_status: str | None = Query(default=None, alias="verificationStatus"),
    payment_status: str | None = Query(default=None, alias="paymentStatus"),
    refund_status: str | None = Query(default=None, alias="refundStatus"),
    state: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500, alias="pageSize"),
) -> dict:
    # The desk must see expired requests already enforced, not as live holds.
    await service.lazy_enforce_for_read(db, edition_id=edition_id)
    rows, total, counts = await service.admin_rows(
        db,
        edition_id,
        category=category,
        verification_status=verification_status,
        payment_status=payment_status,
        refund_status=refund_status,
        state=state,
        q=q,
        page=page,
        page_size=page_size,
    )
    return {
        "data": rows,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "counts": counts,
    }


@router.get("/{registration_id}")
async def registration_detail(
    edition_id: uuid.UUID,
    registration_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("registration.read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await service.lazy_enforce_for_read(db, edition_id=edition_id)
    return {"data": await service.admin_detail(db, edition_id, registration_id)}


@router.get("/{registration_id}/documents/{document_id}/content")
async def document_content(
    edition_id: uuid.UUID,
    registration_id: uuid.UUID,
    document_id: uuid.UUID,
    download: bool = Query(default=False),
    ctx: AuthContext = Depends(require_permission("registration.read")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    document = await service.document_for_admin(
        db, edition_id, registration_id, document_id
    )
    if getattr(document, "external_url", None) or not document.storage_key or str(document.storage_key).startswith("external:"):
        raise NotFound("This document is an external link and has no stored file.")
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


@router.patch("/{registration_id}/details")
async def update_details(
    edition_id: uuid.UUID,
    registration_id: uuid.UUID,
    payload: AdminRegistrationDetailsUpdate,
    request: Request,
    ctx: AuthContext = Depends(require_permission("registration.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await service.registration_by_id(db, edition_id, registration_id)
    await service.admin_update_details(
        db,
        request,
        row,
        payload.model_dump(exclude_unset=True),
        ctx.user,
        _role(ctx, edition_id),
    )
    await db.commit()
    return {"data": await service.admin_detail(db, edition_id, registration_id)}


@router.post("/{registration_id}/notes")
async def add_note(
    edition_id: uuid.UUID,
    registration_id: uuid.UUID,
    payload: RegistrationNote,
    request: Request,
    ctx: AuthContext = Depends(require_permission("registration.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await service.registration_by_id(db, edition_id, registration_id)
    await service.add_note(
        db, request, row, payload.note, ctx.user, _role(ctx, edition_id)
    )
    await db.commit()
    return {"data": await service.admin_detail(db, edition_id, registration_id)}


@router.post("/{registration_id}/decision")
async def decide(
    edition_id: uuid.UUID,
    registration_id: uuid.UUID,
    payload: RegistrationDecision,
    request: Request,
    ctx: AuthContext = Depends(require_permission("registration.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await service.registration_by_id(db, edition_id, registration_id)
    if payload.decision == "approved":
        await service.approve(
            db, request, row, ctx.user, _role(ctx, edition_id), notes=payload.notes
        )
    else:
        await service.reject(
            db,
            request,
            row,
            ctx.user,
            _role(ctx, edition_id),
            reason_code=payload.reason_code,
            reason=payload.reason,
            notes=payload.notes,
            initiate_refund_workflow=bool(payload.initiate_refund),
            refund_events=bool(payload.refund_events),
            can_initiate_refund=bool(
                ctx.has("finance.write", edition_id)
                or ctx.has_global("finance.write")
            ),
        )
    await db.commit()
    return {"data": await service.admin_detail(db, edition_id, registration_id)}


@router.post("/{registration_id}/request-documents")
async def request_documents(
    edition_id: uuid.UUID,
    registration_id: uuid.UUID,
    payload: RequestDocuments,
    request: Request,
    ctx: AuthContext = Depends(require_permission("registration.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await service.registration_by_id(db, edition_id, registration_id)
    await service.request_documents(
        db,
        request,
        row,
        ctx.user,
        _role(ctx, edition_id),
        payload.documents,
        payload.message,
        refund_pass_on_expiry=bool(payload.refund_pass_on_expiry),
        refund_events_on_expiry=bool(payload.refund_events_on_expiry),
    )
    await db.commit()
    return {"data": await service.admin_detail(db, edition_id, registration_id)}


@router.post("/{registration_id}/refund")
async def refund(
    edition_id: uuid.UUID,
    registration_id: uuid.UUID,
    payload: RefundAction,
    request: Request,
    ctx: AuthContext = Depends(require_permission("finance.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await service.registration_by_id(db, edition_id, registration_id)
    await service.refund_action(
        db,
        request,
        row,
        ctx.user,
        _role(ctx, edition_id),
        action=payload.action,
        amount_paise=payload.amount_paise,
        note=payload.note,
        gateway_refund_id=payload.gateway_refund_id,
    )
    await db.commit()
    return {"data": await service.admin_detail(db, edition_id, registration_id)}


@router.post("/{registration_id}/category-change")
async def decide_category_change(
    edition_id: uuid.UUID,
    registration_id: uuid.UUID,
    payload: CategoryChangeDecision,
    request: Request,
    ctx: AuthContext = Depends(require_permission("registration.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await service.registration_by_id(db, edition_id, registration_id)
    change = await service.pending_change(db, row.id)
    if change is None:
        raise NotFound("No pending category change request.")
    result = await service.decide_category_change(
        db,
        request,
        row,
        change,
        ctx.user,
        _role(ctx, edition_id),
        approve_change=payload.decision == "approved",
        note=payload.note,
        settlement=payload.settlement,
    )
    await db.commit()
    return {
        "data": {"result": result, "registration": await service.admin_detail(db, edition_id, registration_id)},
    }


@router.get("/{registration_id}/receipt")
async def admin_receipt(
    edition_id: uuid.UUID,
    registration_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("registration.read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await service.registration_by_id(db, edition_id, registration_id)
    if row.payment_status not in {"paid", "refunded"}:
        raise Conflict("This registration has no successful payment.")
    return {
        "data": {
            "registrationNumber": row.registration_number,
            "amountPaise": row.fee_paise + (row.additional_paid_paise or 0),
            "transactionId": row.transaction_id,
            "paymentStatus": row.payment_status,
            "refundStatus": row.refund_status,
            "paidAt": row.paid_at.isoformat() if row.paid_at else None,
        }
    }


__all__ = ["router"]
