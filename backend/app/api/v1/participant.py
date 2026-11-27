"""Participant workflow: pass purchase, included selection, addons, teams, verification and tickets."""

import uuid

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, current_context
from app.core.config import get_settings
from app.core.errors import AppError, Conflict, NotFound
from app.core.rate_limit import limiter, memory_limiter
from app.db.session import get_db
from app.models.commerce import Ticket
from app.models.edition import ConventionEdition
from app.schemas.participant import (
    AddonRequest,
    CheckoutRequest,
    PassView,
    QuoteRequest,
    SelectionUpdate,
    TeamCreate,
    TeamJoin,
)
from app.schemas.registration import PaymentVerification
from app.services import (
    college_registrations as college_service,
    editions as edition_service,
    idempotency as idempotency_service,
    passes as pass_service,
    payments as payment_service,
    pricing as pricing_service,
    registrations as reg_service,
    teams as team_service,
    tickets as ticket_service,
)

router = APIRouter(prefix="/editions/{edition_id}", tags=["participant"])


async def _edition(db: AsyncSession, edition_id: uuid.UUID) -> ConventionEdition:
    return await edition_service.edition_by_id(db, edition_id)


@router.get(
    "/pass",
    dependencies=[Depends(memory_limiter("pass_read", 180, 60))],
)
async def get_pass(
    edition_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    edition = await _edition(db, edition_id)
    # Event selection shows live seats: release lapsed 24-hour holds first.
    await college_service.lazy_enforce_for_read(
        db, edition_id=edition.id, request=request
    )
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


@router.put("/pass/selections", dependencies=[Depends(limiter("pass_selections", 60, 60))])
async def update_selections(
    edition_id: uuid.UUID,
    payload: SelectionUpdate,
    request: Request,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    edition = await _edition(db, edition_id)
    # A released seat must be bookable in the same request that discovers it.
    await college_service.maybe_enforce_lapsed_compliance(
        db, edition_id=edition.id, request=request
    )
    blocked = await pass_service.pass_gate_blocked(db, ctx.user.id, edition.id)
    if blocked:
        raise Conflict(blocked, code="PASS_BLOCKED")
    user_pass = await pass_service.get_pass(db, ctx.user.id, edition.id)
    if user_pass is None:
        raise NotFound("You do not have a pass for this edition.")
    if user_pass.status != "active":
        if user_pass.status == "suspended":
            raise Conflict("Your convention pass has been suspended by the organisers.", code="PASS_BLOCKED")
        raise Conflict(f"Your convention pass is {user_pass.status}. Event selection is closed.", code="PASS_BLOCKED")
    policy = await edition_service.current_policy(db, edition.id)
    sel, order = await pass_service.set_selections(
        db, request, user_pass, payload.event_ids, policy
    )
    settings = get_settings()
    if order is not None and not settings.payments_enabled and not settings.is_development:
        raise AppError(
            "Online payments are not configured. Contact the organisers.",
            code="PAYMENTS_NOT_CONFIGURED",
            status_code=503,
        )
    out_data = sel.model_dump(by_alias=True)
    out_data["order"] = _team_payment_payload(order) if order is not None else None
    await db.commit()
    return {"data": out_data}


@router.post("/registrations", dependencies=[Depends(limiter("addon_create", 20, 60))])
async def create_registrations(
    edition_id: uuid.UUID,
    payload: AddonRequest,
    request: Request,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    edition = await _edition(db, edition_id)
    # Capacity is re-read below; free lapsed holds first so a sold-out event
    # does not reject a booking for a seat that is actually available.
    await college_service.maybe_enforce_lapsed_compliance(
        db, edition_id=edition.id, request=request
    )
    settings = get_settings()
    # Money-moving POSTs replay their stored answer for the same key instead of
    # booking (and charging) twice. The header was accepted and ignored before.
    replay_payload = {"editionId": str(edition_id), "eventIds": [str(e) for e in payload.event_ids]}
    cached = await idempotency_service.replay(
        db, ctx.user.id, "participant.registrations", idempotency_key, replay_payload
    )
    if cached is not None:
        return cached[1]
    blocked = await pass_service.pass_gate_blocked(db, ctx.user.id, edition.id)
    if blocked:
        raise Conflict(blocked, code="PASS_BLOCKED")
    regs, order = await reg_service.create_addon_registrations(
        db, request, ctx.user.id, edition, payload.event_ids
    )
    # Included selections can still be claimed for free; only a newly created
    # paid order is blocked when the gateway is not configured.
    if order is not None and not settings.payments_enabled and not settings.is_development:
        raise AppError(
            "Online payments are not configured. Contact the organisers.",
            code="PAYMENTS_NOT_CONFIGURED",
            status_code=503,
        )
    views = await reg_service.serialize_registrations(db, regs)
    out = {
        "data": {
            "registrations": [v.model_dump(by_alias=True) for v in views],
            "order": {
                "orderId": str(order.id),
                "amountPaise": order.amount_paise,
                "gatewayOrderId": order.gateway_order_id,
                "razorpayKeyId": settings.razorpay_key_id,
                "mock": settings.mock_payments_available,
            }
            if order
            else None,
        }
    }
    await db.commit()
    await idempotency_service.store(
        db,
        ctx.user.id,
        "participant.registrations",
        idempotency_key,
        replay_payload,
        out,
    )
    await db.commit()
    return out


@router.get(
    "/registrations",
    dependencies=[Depends(memory_limiter("registrations_read", 120, 60))],
)
async def my_registrations(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await college_service.lazy_enforce_for_read(db, edition_id=edition_id)
    regs = await reg_service.list_for_user(db, ctx.user.id, edition_id)
    views = await reg_service.serialize_registrations(db, regs)
    return {"data": [v.model_dump(by_alias=True) for v in views]}


@router.post("/orders/{order_id}/release")
async def release_unpaid_order(
    edition_id: uuid.UUID,
    order_id: uuid.UUID,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _edition(db, edition_id)
    result = await pricing_service.release_unpaid_order(
        db, user_id=ctx.user.id, order_id=order_id
    )
    await db.commit()
    return {"data": result}


@router.delete(
    "/registrations/{registration_id}",
    dependencies=[Depends(limiter("registration_cancel", 20, 60))],
)
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


# --------------------------------------------------------------------------- #
# Unified event worklist: one list, one server price, pay only the difference.
# --------------------------------------------------------------------------- #
@router.get(
    "/worklist",
    dependencies=[Depends(memory_limiter("worklist_read", 180, 60))],
)
async def get_worklist(
    edition_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    edition = await _edition(db, edition_id)
    await college_service.lazy_enforce_for_read(
        db, edition_id=edition.id, request=request
    )
    policy = await edition_service.current_policy(db, edition.id)
    blocked = await pass_service.pass_gate_blocked(db, ctx.user.id, edition.id)
    data = await pricing_service.build_worklist(
        db, user_id=ctx.user.id, edition=edition, policy=policy
    )
    data["gate"] = blocked
    if blocked:
        # The list still explains the event, but nothing is selectable: the
        # portal shows the pass/registration reason instead of a dead Add.
        for row in data["rows"]:
            row["actions"] = []
    user_pass = await pass_service.get_pass(db, ctx.user.id, edition.id)
    data["passStatus"] = user_pass.status if user_pass is not None else None
    data["policyVersion"] = int(policy.version)
    return {"data": data}


@router.get(
    "/basket",
    dependencies=[Depends(memory_limiter("basket_read", 180, 60))],
)
async def get_basket(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    edition = await _edition(db, edition_id)
    quote = await pricing_service.open_basket(db, ctx.user.id, edition.id)
    return {"data": pricing_service.basket_payload(quote)}


@router.post(
    "/basket/events",
    dependencies=[Depends(limiter("basket_add", 60, 60))],
)
async def add_to_basket(
    edition_id: uuid.UUID,
    payload: QuoteRequest,
    request: Request,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    edition = await _edition(db, edition_id)
    blocked = await pass_service.pass_gate_blocked(db, ctx.user.id, edition.id)
    if blocked:
        raise Conflict(blocked, code="PASS_BLOCKED")
    policy = await edition_service.current_policy(db, edition.id)
    quote = await pricing_service.basket_add(
        db,
        user_id=ctx.user.id,
        edition=edition,
        policy=policy,
        event_ids=payload.event_ids,
    )
    await db.commit()
    return {"data": pricing_service.basket_payload(quote)}


@router.delete(
    "/basket/events/{event_id}",
    dependencies=[Depends(limiter("basket_remove", 60, 60))],
)
async def remove_from_basket(
    edition_id: uuid.UUID,
    event_id: uuid.UUID,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    edition = await _edition(db, edition_id)
    policy = await edition_service.current_policy(db, edition.id)
    quote = await pricing_service.basket_remove(
        db,
        user_id=ctx.user.id,
        edition=edition,
        policy=policy,
        event_id=event_id,
    )
    await db.commit()
    return {"data": pricing_service.basket_payload(quote)}


@router.post("/quote", dependencies=[Depends(limiter("event_quote", 30, 60))])
async def create_quote(
    edition_id: uuid.UUID,
    payload: QuoteRequest,
    request: Request,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    edition = await _edition(db, edition_id)
    await college_service.maybe_enforce_lapsed_compliance(
        db, edition_id=edition.id, request=request
    )
    blocked = await pass_service.pass_gate_blocked(db, ctx.user.id, edition.id)
    if blocked:
        raise Conflict(blocked, code="PASS_BLOCKED")
    policy = await edition_service.current_policy(db, edition.id)
    quote = await pricing_service.build_quote(
        db,
        user_id=ctx.user.id,
        edition=edition,
        policy=policy,
        event_ids=payload.event_ids,
    )
    await db.commit()
    return {
        "data": {
            "quoteId": str(quote.id),
            "lines": quote.lines,
            "coveredPaise": int(quote.covered_paise),
            "duePaise": int(quote.due_paise),
            "expiresAt": edition_service.aware(quote.expires_at).isoformat()
            if quote.expires_at
            else None,
        }
    }


@router.post(
    "/checkout",
    dependencies=[Depends(limiter("event_checkout", 20, 60))],
)
async def checkout_quote(
    edition_id: uuid.UUID,
    payload: CheckoutRequest,
    request: Request,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.models.commerce import EventQuote

    edition = await _edition(db, edition_id)
    settings = get_settings()
    replay_payload = {"editionId": str(edition_id), "quoteId": str(payload.quote_id)}
    cached = await idempotency_service.replay(
        db, ctx.user.id, "participant.checkout", idempotency_key, replay_payload
    )
    if cached is not None:
        return cached[1]

    quote = await db.get(EventQuote, payload.quote_id)
    if quote is None or quote.user_id != ctx.user.id or quote.edition_id != edition.id:
        raise NotFound("Quote not found.")
    regs, order = await pricing_service.consume_quote(
        db, user_id=ctx.user.id, quote=quote
    )
    if order is not None and not settings.payments_enabled and not settings.is_development:
        raise AppError(
            "Online payments are not configured. Contact the organisers.",
            code="PAYMENTS_NOT_CONFIGURED",
            status_code=503,
        )
    views = await reg_service.serialize_registrations(db, regs)
    body = {
        "data": {
            "quoteId": str(quote.id),
            "registrations": [v.model_dump(by_alias=True) for v in views],
            "order": (
                {
                    "orderId": str(order.id),
                    "amountPaise": order.amount_paise,
                    "gatewayOrderId": order.gateway_order_id,
                    "razorpayKeyId": settings.razorpay_key_id,
                    "mock": settings.mock_payments_available,
                }
                if order is not None
                else None
            ),
        }
    }
    from fastapi.encoders import jsonable_encoder

    # The replay snapshot is stored as JSON; model dumps carry UUID objects.
    await idempotency_service.store(
        db,
        ctx.user.id,
        "participant.checkout",
        idempotency_key,
        replay_payload,
        jsonable_encoder(body),
    )
    await db.commit()
    return body


@router.delete(
    "/events/{event_id}",
    dependencies=[Depends(limiter("event_remove", 30, 60))],
)
async def remove_event(
    edition_id: uuid.UUID,
    event_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    edition = await _edition(db, edition_id)
    from app.services import pricing as pricing_service_local

    result = await pricing_service_local.remove_seat(
        db,
        request=request,
        user_id=ctx.user.id,
        edition=edition,
        event_id=event_id,
    )
    await db.commit()
    return {"data": result}


def _team_payment_payload(order) -> dict:
    """The same payment shape every other checkout uses.

    A team seat used to answer ``razorpayOrderId`` where the registration order
    answers ``gatewayOrderId``, so the browser had no gateway order id to open
    the checkout with.
    """
    from app.core.config import get_settings

    settings = get_settings()
    return {
        "orderId": str(order.id),
        "amountPaise": int(order.amount_paise),
        "gatewayOrderId": order.gateway_order_id,
        "razorpayKeyId": settings.razorpay_key_id,
        "mock": settings.mock_payments_available,
    }


@router.get(
    "/teams",
    dependencies=[Depends(memory_limiter("teams_read", 120, 60))],
)
async def my_teams(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # A teammate opening the team page must see a lapsed member removed and
    # leadership handed over before the roster is rendered.
    await college_service.lazy_enforce_for_read(db, edition_id=edition_id)
    teams = await team_service.list_for_user(db, ctx.user.id, edition_id)
    views = await team_service.serialize_teams(db, teams, ctx.user.id)
    data = []
    for view, team in zip(views, teams):
        payload = view.model_dump(by_alias=True)
        payment = await team_service.pending_team_payment(db, team, ctx.user.id)
        if payment is not None:
            payload["payment"] = _team_payment_payload(payment)
        data.append(payload)
    return {"data": data}


@router.post("/teams", dependencies=[Depends(limiter("team_create", 10, 60))])
async def create_team(
    edition_id: uuid.UUID,
    payload: TeamCreate,
    request: Request,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    edition = await _edition(db, edition_id)
    # A lapsed attendee's team still occupies an entry until it is released.
    await college_service.maybe_enforce_lapsed_compliance(
        db, edition_id=edition.id, request=request
    )
    team = await team_service.create_team(
        db, request, ctx.user.id, edition, payload.event_id, payload.name
    )
    views = await team_service.serialize_teams(db, [team], ctx.user.id)
    # A priced team seat is reserved until it is paid, so the portal needs the
    # order to start checkout for it.
    payment = await team_service.pending_team_payment(db, team, ctx.user.id)
    await db.commit()
    data = views[0].model_dump(by_alias=True)
    if payment is not None:
        data["payment"] = _team_payment_payload(payment)
    return {"data": data}


@router.post("/teams/join", dependencies=[Depends(limiter("team_join", 10, 60))])
async def join_team(
    edition_id: uuid.UUID,
    payload: TeamJoin,
    request: Request,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    edition = await _edition(db, edition_id)
    # Free rosters held by lapsed attendees before capacity is counted.
    await college_service.maybe_enforce_lapsed_compliance(
        db, edition_id=edition.id, request=request
    )
    team = await team_service.join_team(
        db, request, ctx.user.id, edition, payload.invite_code
    )
    views = await team_service.serialize_teams(db, [team], ctx.user.id)
    payment = await team_service.pending_team_payment(db, team, ctx.user.id)
    await db.commit()
    data = views[0].model_dump(by_alias=True)
    if payment is not None:
        data["payment"] = _team_payment_payload(payment)
    return {"data": data}


@router.delete("/teams/{team_id}")
async def leave_team(
    edition_id: uuid.UUID,
    team_id: uuid.UUID,
    disband: bool = False,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await team_service.leave_team(db, ctx.user.id, team_id, disband=disband)
    await db.commit()
    return {"data": {"left": True}}


@router.post(
    "/teams/{team_id}/rotate-invite",
    dependencies=[Depends(limiter("team_rotate_invite", 5, 60))],
)
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


@router.post(
    "/teams/{team_id}/lock",
    dependencies=[Depends(limiter("team_lock", 10, 60))],
)
async def toggle_lock(
    edition_id: uuid.UUID,
    team_id: uuid.UUID,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    team = await team_service.toggle_team_lock(db, ctx.user.id, team_id)
    views = await team_service.serialize_teams(db, [team], ctx.user.id)
    await db.commit()
    return {"data": views[0].model_dump(by_alias=True)}


@router.get(
    "/tickets",
    dependencies=[Depends(memory_limiter("tickets_read", 180, 60))],
)
async def my_tickets(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await college_service.lazy_enforce_for_read(db, edition_id=edition_id)
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


@router.get(
    "/payments/{order_id}",
    dependencies=[Depends(memory_limiter("payment_status_read", 120, 60))],
)
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


@router.post("/payments/{order_id}/mock")
async def mock_pay(
    edition_id: uuid.UUID,
    order_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    if not settings.mock_payments_available:
        raise NotFound("Mock payment is not available in this environment.")
    blocked = await pass_service.pass_gate_blocked(db, ctx.user.id, edition_id)
    if blocked:
        raise Conflict(blocked, code="PASS_BLOCKED")
    order = await payment_service.order_for(db, order_id)
    if order.user_id != ctx.user.id:
        raise NotFound("Order not found.")
    await payment_service.mark_order_paid(
        db, order, transaction_id=payment_service.mock_payment_id()
    )
    await db.commit()
    return {"data": {"paid": True, "orderId": str(order.id)}}


@router.post("/payments/verify")
async def verify_payment(
    edition_id: uuid.UUID,
    payload: PaymentVerification,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    order = await payment_service.order_for(db, payload.order_id)
    if order.user_id != ctx.user.id or order.edition_id != edition_id:
        raise NotFound("Order not found.")
    blocked = await pass_service.pass_gate_blocked(db, ctx.user.id, edition_id)
    if blocked:
        raise Conflict(blocked, code="PASS_BLOCKED")

    if order.status == "paid":
        return {"data": {"paid": True, "orderId": str(order.id)}}

    settings = get_settings()
    if settings.payments_enabled:
        if not payment_service.verify_checkout_signature(
            order.gateway_order_id or "", payload.razorpay_payment_id, payload.razorpay_signature
        ):
            raise AppError(
                "The payment signature could not be verified.",
                code="PAYMENT_SIGNATURE_INVALID",
                status_code=400,
            )
        gateway_payment = await payment_service.fetch_gateway_payment(payload.razorpay_payment_id)
        if (
            gateway_payment.get("order_id") != order.gateway_order_id
            or int(gateway_payment.get("amount") or 0) != order.amount_paise
            or gateway_payment.get("status") not in {"captured", "authorized"}
        ):
            raise AppError(
                "The payment could not be confirmed with the gateway.",
                code="PAYMENT_NOT_CONFIRMED",
                status_code=409,
            )

    await payment_service.mark_order_paid(
        db, order, transaction_id=payload.razorpay_payment_id
    )
    await db.commit()
    return {"data": {"paid": True, "orderId": str(order.id)}}


__all__ = ["router"]

