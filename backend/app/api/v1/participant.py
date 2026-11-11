"""Participant workflow: pass purchase, included selection, addons, teams, verification and tickets."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, current_context
from app.core.config import get_settings
from app.core.errors import AppError, NotFound, ValidationFailed
from app.db.session import get_db
from app.models.commerce import ConventionPass, PaymentOrder, Registration, Ticket
from app.models.edition import ConventionEdition
from app.schemas.participant import (
    AddonRequest,
    EmailConfirm,
    PassView,
    PaymentOrderView,
    RegistrationView,
    SelectionState,
    SelectionUpdate,
    TeamCreate,
    TeamJoin,
    TeamView,
    TicketView,
    VerificationView,
)
from app.schemas.common import CamelModel
from app.services import (
    editions as edition_service,
    idempotency as idempotency_service,
    passes as pass_service,
    payments as payment_service,
    registrations as reg_service,
    teams as team_service,
    tickets as ticket_service,
    verification as verif_service,
)

router = APIRouter(prefix="/editions/{edition_id}", tags=["participant"])


class CheckoutSignature(CamelModel):
    razorpay_payment_id: str = Field(min_length=8, max_length=80)
    razorpay_order_id: str = Field(min_length=8, max_length=80)
    razorpay_signature: str = Field(min_length=32, max_length=128)


async def _edition(db: AsyncSession, edition_id: uuid.UUID) -> ConventionEdition:
    return await edition_service.edition_by_id(db, edition_id)


async def _require_registration_open(db: AsyncSession) -> None:
    from app.services.system_settings import require_registration_open

    await require_registration_open(db)


@router.get("/pass")
async def get_pass(
    edition_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    edition = await _edition(db, edition_id)
    user_pass = await pass_service.get_pass(db, ctx.user.id, edition.id)
    if user_pass is None:
        return {"data": None}
    policy = await edition_service.current_policy(db, edition.id)
    sel = await pass_service.selection_state(db, user_pass, policy)
    view = PassView(
        id=user_pass.id,
        edition_id=user_pass.edition_id,
        price_paise=user_pass.price_paise,
        policy_version=user_pass.policy_version,
        status=user_pass.status,
        lunch_days=user_pass.lunch_days or [],
        paid_at=edition_service.aware(user_pass.paid_at),
        selection=sel,
        created_at=edition_service.aware(user_pass.created_at),
    )
    return {"data": view.model_dump(by_alias=True)}


@router.post("/pass/order")
async def create_pass_order(
    edition_id: uuid.UUID,
    request: Request,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _require_registration_open(db)
    edition = await _edition(db, edition_id)
    policy = await edition_service.current_policy(db, edition.id)

    replayed = await idempotency_service.replay(
        db, ctx.user.id, request.url.path, idempotency_key, {}
    )
    if replayed:
        status_code, body = replayed
        return body

    user_pass, order = await pass_service.create_pass_order(
        db, ctx.user.id, edition, policy
    )
    settings = get_settings()
    out = {
        "data": {
            "orderId": str(order.id),
            "amountPaise": order.amount_paise,
            "gatewayOrderId": order.gateway_order_id,
            "razorpayKeyId": settings.razorpay_key_id,
            "mock": not settings.payments_enabled,
        }
    }
    await idempotency_service.store(
        db, ctx.user.id, request.url.path, idempotency_key, {}, out
    )
    await db.commit()
    return out


@router.put("/pass/selections")
async def update_selections(
    edition_id: uuid.UUID,
    payload: SelectionUpdate,
    request: Request,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _require_registration_open(db)
    edition = await _edition(db, edition_id)
    user_pass = await pass_service.get_pass(db, ctx.user.id, edition.id)
    if user_pass is None:
        raise NotFound("You do not have a pass for this edition.")
    policy = await edition_service.current_policy(db, edition.id)
    sel = await pass_service.set_selections(
        db, request, user_pass, payload.event_ids, policy
    )
    await db.commit()
    return {"data": sel.model_dump(by_alias=True)}


@router.post("/registrations")
async def create_registrations(
    edition_id: uuid.UUID,
    payload: AddonRequest,
    request: Request,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _require_registration_open(db)
    edition = await _edition(db, edition_id)
    regs, order = await reg_service.create_addon_registrations(
        db, request, ctx.user.id, edition, payload.event_ids
    )
    views = await reg_service.serialize_registrations(db, regs)
    settings = get_settings()
    out = {
        "data": {
            "registrations": [v.model_dump(by_alias=True) for v in views],
            "order": {
                "orderId": str(order.id),
                "amountPaise": order.amount_paise,
                "gatewayOrderId": order.gateway_order_id,
                "razorpayKeyId": settings.razorpay_key_id,
                "mock": not settings.payments_enabled,
            }
            if order
            else None,
        }
    }
    await db.commit()
    return out


@router.get("/registrations")
async def my_registrations(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    regs = await reg_service.list_for_user(db, ctx.user.id, edition_id)
    views = await reg_service.serialize_registrations(db, regs)
    return {"data": [v.model_dump(by_alias=True) for v in views]}


@router.delete("/registrations/{registration_id}")
async def cancel_registration(
    edition_id: uuid.UUID,
    registration_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await reg_service.cancel_registration(db, request, ctx.user.id, registration_id)
    await db.commit()
    return {"data": {"cancelled": True}}


@router.get("/teams")
async def my_teams(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    teams = await team_service.list_for_user(db, ctx.user.id, edition_id)
    views = await team_service.serialize_teams(db, teams, ctx.user.id)
    return {"data": [v.model_dump(by_alias=True) for v in views]}


@router.post("/teams")
async def create_team(
    edition_id: uuid.UUID,
    payload: TeamCreate,
    request: Request,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _require_registration_open(db)
    edition = await _edition(db, edition_id)
    team = await team_service.create_team(
        db, request, ctx.user.id, edition, payload.event_id, payload.name
    )
    views = await team_service.serialize_teams(db, [team], ctx.user.id)
    await db.commit()
    return {"data": views[0].model_dump(by_alias=True)}


@router.post("/teams/join")
async def join_team(
    edition_id: uuid.UUID,
    payload: TeamJoin,
    request: Request,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _require_registration_open(db)
    edition = await _edition(db, edition_id)
    team = await team_service.join_team(
        db, request, ctx.user.id, edition, payload.invite_code
    )
    views = await team_service.serialize_teams(db, [team], ctx.user.id)
    await db.commit()
    return {"data": views[0].model_dump(by_alias=True)}


@router.delete("/teams/{team_id}")
async def leave_team(
    edition_id: uuid.UUID,
    team_id: uuid.UUID,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await team_service.leave_team(db, ctx.user.id, team_id)
    await db.commit()
    return {"data": {"left": True}}


@router.post("/teams/{team_id}/rotate-invite")
async def rotate_invite(
    edition_id: uuid.UUID,
    team_id: uuid.UUID,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    team = await team_service.get_team(db, team_id)
    if team.leader_id != ctx.user.id:
        raise NotFound("You are not the team leader.")
    code = await team_service.rotate_invite(db, team)
    await db.commit()
    return {"data": {"inviteCode": code}}


@router.get("/verification")
async def verification_status(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    status = await verif_service.status_for(db, ctx.user, edition_id)
    return {"data": status}


@router.post("/verification")
async def submit_verification(
    edition_id: uuid.UUID,
    request: Request,
    method: Annotated[str, Form()],
    institution_email: Annotated[str | None, Form()] = None,
    file: UploadFile | None = File(None),
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    edition = await _edition(db, edition_id)
    file_bytes = await file.read() if file else None
    res = await verif_service.submit(
        db,
        request,
        ctx.user,
        edition,
        method=method,
        institution_email=institution_email,
        file_bytes=file_bytes,
        filename=file.filename if file else None,
        content_type=file.content_type if file else None,
    )
    await db.commit()
    return {"data": res}


@router.post("/verification/confirm")
async def confirm_verification_email(
    edition_id: uuid.UUID,
    payload: EmailConfirm,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    edition = await _edition(db, edition_id)
    ok = await verif_service.confirm_email(db, ctx.user, edition.id, payload.code)
    await db.commit()
    return {"data": {"verified": ok}}


@router.get("/tickets")
async def my_tickets(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = list(
        (
            await db.execute(
                select(Ticket)
                .where(
                    Ticket.user_id == ctx.user.id,
                    Ticket.edition_id == edition_id,
                    Ticket.status.in_(["active", "valid"]),
                )
            )
        ).scalars()
    )
    payloads = [await ticket_service.ticket_payload(db, t) for t in rows]
    return {"data": payloads}


@router.get("/tickets/{ticket_id}/qr")
async def ticket_qr(
    edition_id: uuid.UUID,
    ticket_id: uuid.UUID,
    request: Request,
    accent: str = Query(default="cyan", max_length=20),
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> Response:
    t = await db.get(Ticket, ticket_id)
    if t is None or t.user_id != ctx.user.id or t.edition_id != edition_id:
        raise NotFound("Ticket not found.")
    svg = ticket_service.qr_svg(ticket_service.ticket_token_for(t.id), accent=accent)
    return Response(content=svg, media_type="image/svg+xml")


@router.get("/payments/{order_id}")
async def payment_status(
    edition_id: uuid.UUID,
    order_id: uuid.UUID,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    order = await payment_service.order_for(db, order_id)
    if order.user_id != ctx.user.id or order.edition_id != edition_id:
        raise NotFound("Order not found.")
    return {
        "data": {
            "id": str(order.id),
            "status": order.status,
            "amountPaise": order.amount_paise,
            "purpose": order.purpose,
            "paidAt": edition_service.aware(order.paid_at).isoformat() if order.paid_at else None,
        }
    }


@router.post("/payments/{order_id}/verify")
async def verify_checkout(
    edition_id: uuid.UUID,
    order_id: uuid.UUID,
    payload: CheckoutSignature,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Validate Checkout's signature; only the webhook can settle the order as paid."""
    settings = get_settings()
    order = await payment_service.order_for(db, order_id)
    if order.user_id != ctx.user.id or order.edition_id != edition_id:
        raise NotFound("Order not found.")
    if not settings.payments_enabled or not settings.razorpay_key_secret:
        raise AppError("Payment verification is unavailable.", status_code=503)
    if payload.razorpay_order_id != order.gateway_order_id:
        raise ValidationFailed("The payment does not belong to this order.")
    if not payment_service.verify_checkout_signature(
        payload.razorpay_order_id,
        payload.razorpay_payment_id,
        payload.razorpay_signature,
        settings.razorpay_key_secret,
    ):
        raise ValidationFailed("Payment signature verification failed.")
    return {"data": {"verified": True, "status": order.status}}


@router.post("/payments/{order_id}/mock")
async def mock_pay(
    edition_id: uuid.UUID,
    order_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    if settings.payments_enabled:
        raise AppError("Mock payment is not available in this environment.", status_code=400)
    order = await payment_service.order_for(db, order_id)
    if order.user_id != ctx.user.id:
        raise NotFound("Order not found.")
    await payment_service.mark_order_paid(
        db, order, transaction_id=payment_service.mock_payment_id()
    )
    await db.commit()
    return {"data": {"paid": True, "orderId": str(order.id)}}


__all__ = ["router"]

