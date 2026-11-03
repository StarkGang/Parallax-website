"""Registrations: addon event booking, capacity checks and cancellations."""

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.models.commerce import ConventionPass, PaymentOrder, Registration, Team
from app.models.edition import ConventionEdition, Event, EventCategory
from app.schemas.participant import RegistrationView
from app.services.audit import record
from app.services.editions import aware, current_policy
from app.services.events import seats_taken


def _number(kind: str) -> str:
    prefix = "REG" if kind != "included" else "INC"
    return f"{prefix}-{secrets.token_hex(4).upper()}"


async def list_for_user(
    db: AsyncSession, user_id: uuid.UUID, edition_id: uuid.UUID
) -> list[Registration]:
    rows = list(
        (
            await db.execute(
                select(Registration)
                .where(
                    Registration.user_id == user_id,
                    Registration.edition_id == edition_id,
                    Registration.status.in_(["confirmed", "reserved", "pending"]),
                )
                .order_by(Registration.created_at.desc())
            )
        ).scalars()
    )
    return rows


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
    policy = await current_policy(db, edition.id)
    if policy.addon_requires_pass:
        user_pass = (
            await db.execute(
                select(ConventionPass).where(
                    ConventionPass.user_id == user_id,
                    ConventionPass.edition_id == edition.id,
                    ConventionPass.status == "active",
                )
            )
        ).scalar_one_or_none()
        if user_pass is None:
            raise ValidationFailed("You must hold an active pass to register for add-on events.")

    events = list(
        (
            await db.execute(
                select(Event).where(
                    Event.id.in_(event_ids),
                    Event.edition_id == edition.id,
                )
            )
        ).scalars()
    )

    if len(events) != len(event_ids):
        raise NotFound("One or more events not found.")

    total_paise = 0
    regs = []
    for e in events:
        await _assert_capacity(db, e)
        # Check duplicate
        existing = (
            await db.execute(
                select(Registration).where(
                    Registration.user_id == user_id,
                    Registration.event_id == e.id,
                    Registration.status.in_(["confirmed", "reserved"]),
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
    reg.status = "cancelled"
    reg.cancelled_at = datetime.now(UTC)
    await record(
        db,
        request,
        actor_id=user_id,
        action="registration.cancelled",
        resource_type="registration",
        resource_id=str(reg.id),
        after={"reason": reason},
    )
    await db.flush()


async def expire_reservations(db: AsyncSession) -> int:
    from sqlalchemy import update

    now = datetime.now(UTC)
    result = await db.execute(
        update(Registration)
        .where(
            Registration.status == "reserved",
            Registration.reservation_expires_at < now,
        )
        .values(status="cancelled", cancelled_at=now)
    )
    return result.rowcount or 0


async def team_member_count(db: AsyncSession, team_id: uuid.UUID) -> int:
    from app.models.commerce import TeamMember

    return (
        await db.execute(
            select(func.count(TeamMember.id)).where(TeamMember.team_id == team_id)
        )
    ).scalar() or 0


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
]

