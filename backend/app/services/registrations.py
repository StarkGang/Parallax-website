"""Registrations: addon event booking, capacity checks and cancellations."""

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_delete_pattern
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.models.commerce import (
    ConventionPass,
    IncludedEventSelection,
    PaymentOrder,
    PaymentTransaction,
    Registration,
    Team,
    TeamMember,
)
from app.models.edition import ConventionEdition, Event, EventCategory
from app.models.user import User
from app.schemas.participant import RegistrationView
from app.services import notifications as notify_service
from app.services.audit import record
from app.services.editions import aware, current_policy
from app.services.events import event_open, seats_taken
from app.services.tickets import issue_for_registration, revoke_for_registration

CANCELLATION_CUTOFF_HOURS = 24


def _number(kind: str) -> str:
    prefix = "REG" if kind != "included" else "INC"
    return f"{prefix}-{secrets.token_hex(4).upper()}"


async def list_for_user(
    db: AsyncSession, user_id: uuid.UUID, edition_id: uuid.UUID
) -> list[Registration]:
    from sqlalchemy import or_
    from app.models.commerce import TeamMember

    team_subq = select(TeamMember.team_id).where(TeamMember.user_id == user_id)
    rows = list(
        (
            await db.execute(
                select(Registration)
                .where(
                    or_(
                        Registration.user_id == user_id,
                        Registration.team_id.in_(team_subq),
                    ),
                    Registration.edition_id == edition_id,
                    Registration.status.in_(["confirmed", "reserved", "pending", "cancelled"]),
                )
                .order_by(Registration.created_at.desc())
            )
        ).scalars()
    )
    seen = set()
    deduped = []
    for r in rows:
        if r.id not in seen:
            seen.add(r.id)
            deduped.append(r)
    return deduped


async def serialize_registrations(
    db: AsyncSession, registrations: list[Registration]
) -> list[RegistrationView]:
    if not registrations:
        return []
    items = []
    for r in registrations:
        event = await db.get(Event, r.event_id)
        cat = await db.get(EventCategory, event.category_id) if event else None
        team = await db.get(Team, r.team_id) if r.team_id else None
        items.append(
            RegistrationView(
                id=r.id,
                registration_number=r.registration_number,
                event_id=r.event_id,
                event_title=event.title if event else "Event",
                event_slug=event.slug if event else "",
                category=cat.name if cat else "General",
                kind=r.kind,
                fee_paise=r.fee_paise,
                status=r.status,
                created_at=aware(r.created_at),
                team_id=r.team_id,
                team_name=team.name if team else None,
                reservation_expires_at=aware(r.reservation_expires_at),
                order_id=r.order_id,
                event_starts_at=aware(event.starts_at) if event else None,
                cancelled_at=aware(r.cancelled_at) if r.cancelled_at else None,
                cancelled_by=getattr(r, "cancelled_by", None),
                cancellation_reason=getattr(r, "cancellation_reason", None),
            )
        )
    return items


async def _assert_capacity(db: AsyncSession, event: Event) -> None:
    taken = (await seats_taken(db, [event.id])).get(event.id, 0)
    if event.capacity and taken >= event.capacity:
        raise Conflict(f"Event '{event.title}' is sold out.")


async def create_addon_registrations(
    db: AsyncSession,
    request: Request,
    user_id: uuid.UUID,
    edition: ConventionEdition,
    event_ids: list[uuid.UUID],
) -> tuple[list[Registration], PaymentOrder | None]:
    # Serialise concurrent bookings from the same attendee. Two parallel
    # requests cannot both pass the duplicate/seat checks and book different
    # seats for the same events.
    await db.execute(select(User.id).where(User.id == user_id).with_for_update())

    policy = await current_policy(db, edition.id)
    user_pass = (
        await db.execute(
            select(ConventionPass).where(
                ConventionPass.user_id == user_id,
                ConventionPass.edition_id == edition.id,
            )
        )
    ).scalar_one_or_none()
    if policy.addon_requires_pass and (user_pass is None or user_pass.status != "active"):
        raise ValidationFailed("You must hold an active pass to register for add-on events.")

    unique_ids = list(dict.fromkeys(event_ids))
    if len(unique_ids) != len(event_ids):
        raise ValidationFailed("The same event was selected twice.")
    event_ids = unique_ids

    # Release abandoned unpaid holds before checking capacity.
    await expire_reservations(db)

    declared: set[uuid.UUID] = set()
    if user_pass is not None:
        declared = set(
            (
                await db.execute(
                    select(IncludedEventSelection.event_id).where(
                        IncludedEventSelection.pass_id == user_pass.id
                    )
                )
            ).scalars()
        )

    events = list(
        (
            await db.execute(
                select(Event)
                .where(
                    Event.id.in_(event_ids),
                    Event.edition_id == edition.id,
                )
                .with_for_update()
            )
        ).scalars()
    )

    if len(events) != len(event_ids):
        raise NotFound("One or more events not found.")

    total_paise = 0
    regs = []
    for e in events:
        if not event_open(e):
            raise Conflict(f"Registration for '{e.title}' is closed.")
        if e.id in declared:
            raise Conflict(
                f"'{e.title}' is already claimed inside your pass allowance. Remove it from your "
                "included selection before booking it as an add-on."
            )
        await _assert_capacity(db, e)
        # Check duplicate across every live registration state
        existing = (
            await db.execute(
                select(Registration).where(
                    Registration.user_id == user_id,
                    Registration.event_id == e.id,
                    Registration.status.in_(["confirmed", "reserved", "pending"]),
                )
            )
        ).scalar_one_or_none()
        if existing:
            raise Conflict(f"Already registered for {e.title}.")

        fee = e.addon_price_paise
        total_paise += fee
        reg = Registration(
            edition_id=edition.id,
            user_id=user_id,
            event_id=e.id,
            kind="addon",
            fee_paise=fee,
            status="confirmed" if fee == 0 else "reserved",
            registration_number=_number("addon"),
            reservation_expires_at=datetime.now(UTC) + timedelta(minutes=policy.hold_minutes),
        )
        db.add(reg)
        regs.append(reg)

    await db.flush()

    order = None
    if total_paise > 0:
        order = PaymentOrder(
            edition_id=edition.id,
            user_id=user_id,
            purpose="registration",
            amount_paise=total_paise,
            status="created",
        )
        db.add(order)
        await db.flush()
        for r in regs:
            r.order_id = order.id
        await db.flush()
        from app.services.payments import attach_gateway_order

        await attach_gateway_order(db, order)
    else:
        # Free add-ons are confirmed immediately, so they need their tickets now.
        for r in regs:
            await issue_for_registration(db, r)
        await notify_service.notify_free_registrations(db, regs)

    cache_delete_pattern("public:*")
    cache_delete_pattern("admin:dashboard:*")
    return regs, order


async def get_registration(
    db: AsyncSession, registration_id: uuid.UUID
) -> Registration:
    row = await db.get(Registration, registration_id)
    if row is None:
        raise NotFound("Registration not found.")
    return row


async def cancel_registration(
    db: AsyncSession,
    request: Request,
    user_id: uuid.UUID,
    registration_id: uuid.UUID,
    reason: str | None = None,
) -> None:
    reg = await get_registration(db, registration_id)
    if reg.user_id != user_id:
        raise NotFound("Registration not found.")
    if reg.status == "cancelled":
        return
    event = await db.get(Event, reg.event_id)
    entry = aware(event.starts_at) if event else None
    if entry is not None:
        cutoff = datetime.now(UTC) + timedelta(hours=CANCELLATION_CUTOFF_HOURS)
        if entry <= cutoff:
            raise Conflict(
                "Registrations cannot be cancelled within 24 hours of the event start. "
                "Contact the helpdesk if you cannot attend.",
                code="CANCELLATION_CLOSED",
            )
    reg.status = "cancelled"
    reg.cancelled_at = datetime.now(UTC)
    reg.cancelled_by = "user"
    reg.cancellation_reason = reason or "Cancelled by attendee"
    await revoke_for_registration(db, reg.id)
    if reg.kind == "included":
        user_pass = (
            (
                await db.execute(
                    select(ConventionPass)
                    .where(
                        ConventionPass.user_id == reg.user_id,
                        ConventionPass.edition_id == reg.edition_id,
                    )
                    .order_by(ConventionPass.created_at.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if user_pass is not None:
            await db.execute(
                delete(IncludedEventSelection).where(
                    IncludedEventSelection.pass_id == user_pass.id,
                    IncludedEventSelection.event_id == reg.event_id,
                )
            )
    cache_delete_pattern("public:*")
    cache_delete_pattern("admin:dashboard:*")
    await record(
        db,
        request,
        actor_id=user_id,
        action="registration.cancelled",
        resource_type="registration",
        resource_id=str(reg.id),
        after={"reason": reason},
    )
    await notify_service.notify_registration_cancelled(
        db, reg, actor="participant", reason=reason
    )
    await db.flush()


async def expire_reservations(db: AsyncSession) -> int:
    from sqlalchemy import update

    now = datetime.now(UTC)
    expired_ids = list(
        (
            await db.execute(
                select(Registration.id).where(
                    Registration.status == "reserved",
                    Registration.reservation_expires_at.is_not(None),
                    Registration.reservation_expires_at < now,
                )
            )
        ).scalars()
    )
    if not expired_ids:
        return 0

    await db.execute(
        update(PaymentOrder)
        .where(
            PaymentOrder.status == "created",
            PaymentOrder.purpose == "registration",
            PaymentOrder.id.in_(
                select(Registration.order_id).where(Registration.id.in_(expired_ids))
            ),
        )
        .values(status="expired")
    )
    await db.execute(
        update(Registration)
        .where(Registration.id.in_(expired_ids))
        .values(status="cancelled", cancelled_at=now)
    )
    cache_delete_pattern("public:*")
    cache_delete_pattern("admin:dashboard:*")
    return len(expired_ids)


async def team_member_count(db: AsyncSession, team_id: uuid.UUID) -> int:
    return (
        await db.execute(
            select(func.count(TeamMember.id)).where(TeamMember.team_id == team_id)
        )
    ).scalar() or 0


async def receipt_for_registration(
    db: AsyncSession,
    user_id: uuid.UUID,
    edition_id: uuid.UUID,
    registration_id: uuid.UUID,
) -> dict[str, Any]:
    """Payment slip data for one event registration.

    Owners and teammates of a team registration may read it; anybody else gets
    the same 404 as a missing row, so registration ids stay unenumerable.
    """
    reg = await db.get(Registration, registration_id)
    if reg is None or reg.edition_id != edition_id:
        raise NotFound("Registration not found.")

    if reg.user_id != user_id:
        allowed = False
        if reg.team_id is not None:
            member = (
                await db.execute(
                    select(TeamMember.id).where(
                        TeamMember.team_id == reg.team_id,
                        TeamMember.user_id == user_id,
                    )
                )
            ).scalar_one_or_none()
            allowed = member is not None
        if not allowed:
            raise NotFound("Registration not found.")

    event = await db.get(Event, reg.event_id)
    owner = await db.get(User, reg.user_id)
    edition = await db.get(ConventionEdition, edition_id)

    transaction = None
    if reg.order_id is not None:
        transaction = (
            (
                await db.execute(
                    select(PaymentTransaction)
                    .where(PaymentTransaction.order_id == reg.order_id)
                    .order_by(PaymentTransaction.created_at.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )

    paid_at = None
    if transaction is not None:
        paid_at = aware(transaction.captured_at)
    elif reg.order_id is not None:
        order = await db.get(PaymentOrder, reg.order_id)
        paid_at = aware(order.paid_at) if order is not None else None

    is_paid = (
        reg.kind == "addon"
        and reg.fee_paise > 0
        and reg.status in {"confirmed", "reserved", "cancelled"}
        and (transaction is not None or reg.status != "reserved")
    )

    return {
        "registrationNumber": reg.registration_number,
        "eventId": str(reg.event_id),
        "eventTitle": event.title if event else "Event",
        "eventVenue": event.venue_room if event else None,
        "eventStartsAt": aware(event.starts_at).isoformat() if event and event.starts_at else None,
        "kind": reg.kind,
        "status": reg.status,
        "feePaise": reg.fee_paise,
        "paidPaise": reg.fee_paise if is_paid else 0,
        "transactionId": transaction.gateway_payment_id if transaction else None,
        "paidAt": paid_at.isoformat() if paid_at else None,
        "participantName": owner.full_name if owner else None,
        "participantEmail": owner.email if owner else None,
        "editionName": edition.name if edition else None,
        "issuedAt": datetime.now(UTC).isoformat(),
    }


__all__ = [
    "_number",
    "list_for_user",
    "serialize_registrations",
    "_assert_capacity",
    "create_addon_registrations",
    "get_registration",
    "cancel_registration",
    "expire_reservations",
    "team_member_count",
    "receipt_for_registration",
]

