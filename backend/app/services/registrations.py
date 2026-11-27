"""Registrations: addon event booking, capacity checks and cancellations."""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

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
from app.services.audit import record
from app.services.editions import accepting_bookings, aware, current_policy
from app.services.events import capacity_usage, event_open
from app.services.tickets import issue_for_registration, revoke_for_registration

CANCELLATION_CUTOFF_HOURS = 24


def _number(kind: str) -> str:
    prefix = "REG" if kind != "included" else "INC"
    return f"{prefix}-{secrets.token_hex(4).upper()}"


async def list_for_user(
    db: AsyncSession, user_id: uuid.UUID, edition_id: uuid.UUID
) -> list[Registration]:
    """The attendee's own seats for this edition.

    This used to also return every teammate's registration (anything whose
    ``team_id`` pointed at a team the user belongs to), so a three-person team
    put three "confirmed" rows on the page, one of them owned by somebody else.
    An attendee who was cancelled while their leader stayed confirmed therefore
    saw "confirmed" seats for a pass that no longer existed.
    """
    rows = list(
        (
            await db.execute(
                select(Registration)
                .where(
                    Registration.user_id == user_id,
                    Registration.edition_id == edition_id,
                    Registration.status.in_(
                        ["confirmed", "reserved", "pending", "cancelled"]
                    ),
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
        # Payment reference for receipt line items. Looked up for every
        # registration (including cancelled ones) so the bill keeps showing
        # paid events after a pass rejection/refund revokes their tickets.
        order = await db.get(PaymentOrder, r.order_id) if r.order_id else None
        txn = None
        if order is not None:
            res = await db.execute(
                select(PaymentTransaction)
                .where(PaymentTransaction.order_id == order.id)
                .order_by(PaymentTransaction.captured_at.desc())
            )
            txn = res.scalars().first()
        paid_at = order.paid_at if order is not None and order.paid_at else (txn.captured_at if txn else None)
        # A per-team entry is paid once by whoever created it. The joiner's
        # event stays on their list, but the money belongs on the payer's bill.
        billable = int(r.fee_paise or 0) > 0
        covered_by_team = bool(
            team is not None and team.order_id is not None and not billable
        )
        payer_id = None
        if covered_by_team:
            payer_id = getattr(team, "paid_by_user_id", None)
        elif order is not None:
            payer_id = order.user_id
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
                price_basis=r.price_basis or r.kind,
                created_at=aware(r.created_at),
                team_id=r.team_id,
                team_name=team.name if team else None,
                reservation_expires_at=aware(r.reservation_expires_at),
                order_id=r.order_id,
                event_starts_at=aware(event.starts_at) if event else None,
                event_status=event.status if event else None,
                cancelled_at=aware(r.cancelled_at) if r.cancelled_at else None,
                cancelled_by=getattr(r, "cancelled_by", None),
                cancellation_reason=getattr(r, "cancellation_reason", None),
                gateway_order_id=order.gateway_order_id if order else None,
                payment_id=txn.gateway_payment_id if txn else None,
                paid_at=aware(paid_at) if paid_at else None,
                payment_status=order.status if order else None,
                billable=billable,
                billing_role=(
                    "payer"
                    if billable
                    else "team_covered"
                    if covered_by_team
                    else "self"
                ),
                payer_user_id=payer_id,
            )
        )
    return items


async def _assert_capacity(db: AsyncSession, event: Event) -> None:
    # Capacity is counted in the unit the event declared: people for individual
    # events, teams (entries) for team events.
    taken = (await capacity_usage(db, [event])).get(event.id, 0)
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

    if not accepting_bookings(edition):
        raise Conflict("This convention is no longer accepting new bookings.")

    policy = await current_policy(db, edition.id)
    user = await db.get(User, user_id)
    if user is not None and user.status == "suspended":
        raise ValidationFailed("Your account has been suspended by the organisers. Add-on event registrations are closed.")

    user_pass = (
        await db.execute(
            select(ConventionPass).where(
                ConventionPass.user_id == user_id,
                ConventionPass.edition_id == edition.id,
            ).order_by(ConventionPass.created_at.desc()).limit(1)
        )
    ).scalars().first()
    if user_pass is not None and user_pass.status == "suspended":
        raise ValidationFailed("Your convention pass has been suspended by the organisers. Add-on event registrations are closed.")
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
            if existing.status in ("reserved", "pending"):
                # Stale or abandoned unpaid reservation: cancel it cleanly so retry or re-booking succeeds
                existing.status = "cancelled"
                existing.cancelled_at = datetime.now(UTC)
                existing.cancelled_by = "superseded"
                existing.cancellation_reason = "Superseded by new booking attempt"
                # The replaced order must not stay payable: paying it later
                # revived the cancelled row and charged the attendee twice.
                if existing.order_id is not None:
                    old_order = await db.get(PaymentOrder, existing.order_id)
                    if old_order is not None and old_order.status == "created":
                        old_order.status = "expired"
                await revoke_for_registration(db, existing.id)
            else:
                raise Conflict(f"Already registered for {e.title}.")

        fee = e.addon_price_paise
        is_free = fee == 0
        initial_status = (
            ("pending" if e.requires_approval else "confirmed")
            if is_free
            else "reserved"
        )
        total_paise += fee
        reg = Registration(
            edition_id=edition.id,
            user_id=user_id,
            event_id=e.id,
            kind="addon",
            fee_paise=fee,
            status=initial_status,
            registration_number=_number("addon"),
            reservation_expires_at=None if is_free else (datetime.now(UTC) + timedelta(minutes=policy.hold_minutes)),
        )
        db.add(reg)
        regs.append(reg)

    await db.flush()

    order = None
    paid_regs = [r for r in regs if r.fee_paise > 0]
    confirmed_free_regs = [r for r in regs if r.fee_paise == 0 and r.status == "confirmed"]

    # Free add-on events without manual approval are confirmed immediately and tickets issued
    for r in confirmed_free_regs:
        await issue_for_registration(db, r)

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
        for r in paid_regs:
            r.order_id = order.id
        await db.flush()
        from app.services.payments import attach_gateway_order

        await attach_gateway_order(db, order)

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
    if reg.team_id is not None:
        team = await db.get(Team, reg.team_id)
        if team is not None and team.status == "locked":
            raise Conflict(
                "This team roster is locked and cannot be modified. "
                "Unlock the team first or contact an organiser.",
                code="TEAM_LOCKED",
            )
    event = await db.get(Event, reg.event_id)
    entry = aware(event.starts_at) if event else None
    # Cancelling stays possible until CANCELLATION_CUTOFF_HOURS before the start;
    # the policy's refund rule decides only whether money comes back. Reading
    # refund_rules as the cancellation window used to block cancellations that
    # the published policy never forbade.
    from app.services.editions import current_policy

    try:
        policy = await current_policy(db, reg.edition_id)
    except Exception:
        policy = None
    rules = (getattr(policy, "refund_rules", None) or {}) if policy is not None else {}
    refund_allowed = bool(rules.get("allowed", True))
    try:
        refund_deadline_hours = int(rules.get("deadlineHours"))
    except (TypeError, ValueError):
        refund_deadline_hours = CANCELLATION_CUTOFF_HOURS
    if entry is not None:
        cutoff = datetime.now(UTC) + timedelta(hours=CANCELLATION_CUTOFF_HOURS)
        if entry <= cutoff:
            raise Conflict(
                f"Registrations cannot be cancelled within {CANCELLATION_CUTOFF_HOURS} hours of the event start. "
                "Contact the helpdesk if you cannot attend.",
                code="CANCELLATION_CLOSED",
            )
    refundable = bool(
        refund_allowed
        and entry is not None
        and datetime.now(UTC) + timedelta(hours=refund_deadline_hours) <= entry
    )
    reg.status = "cancelled"
    reg.cancelled_at = datetime.now(UTC)
    reg.cancelled_by = "user"
    reg.cancellation_reason = reason or "Cancelled by attendee"
    await revoke_for_registration(db, reg.id)
    # Close the unpaid checkout for this seat; otherwise it stayed payable and
    # a late payment re-confirmed the cancelled booking.
    if reg.order_id is not None:
        order = await db.get(PaymentOrder, reg.order_id)
        if order is not None and order.status == "created":
            order.status = "expired"
        if (
            order is not None
            and order.status == "paid"
            and reg.fee_paise > 0
            and refundable
        ):
            from app.models.commerce import Refund as RefundRow

            # A ``per_team`` order belongs to the team. If teammates are still
            # on a team that survives this cancellation, the fee stays with
            # them instead of being handed back to the leaver.
            shared_with_team = False
            if reg.team_id is not None:
                team = await db.get(Team, reg.team_id)
                if team is not None and team.order_id == order.id:
                    remaining = (
                        await db.execute(
                            select(func.count(TeamMember.id)).where(
                                TeamMember.team_id == team.id,
                                TeamMember.user_id != reg.user_id,
                            )
                        )
                    ).scalar() or 0
                    shared_with_team = remaining > 0
            if shared_with_team:
                already = None
            else:
                already = (
                    await db.execute(
                        select(RefundRow).where(
                            RefundRow.order_id == order.id,
                            RefundRow.status.in_(["pending", "processing", "processed"]),
                        )
                    )
                ).scalars().first()
            if already is None:
                db.add(
                    RefundRow(
                        order_id=order.id,
                        amount_paise=min(int(reg.fee_paise), int(order.amount_paise)),
                        reason_code="attendee_cancelled",
                        reason_note=reason or "Cancelled by attendee before the deadline",
                        status="pending",
                    )
                )
    if reg.team_id is not None:
        from app.services.teams import on_team_registration_cancelled
        await on_team_registration_cancelled(db, reg)
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
    if reg.status == "cancelled":
        from app.services.passes import drop_attendance

        await drop_attendance(
            db, user_id=user_id, edition_id=reg.edition_id, event_id=reg.event_id
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

    # The sweep and the gateway can race: if the order was paid between the
    # SELECT above and this UPDATE, cancelling its registration would keep the
    # money and drop the seat. Those rows are left to the payment flow.
    paid_order_ids = set(
        (
            await db.execute(
                select(Registration.id)
                .join(PaymentOrder, PaymentOrder.id == Registration.order_id)
                .where(
                    Registration.id.in_(expired_ids),
                    PaymentOrder.status == "paid",
                )
            )
        ).scalars()
    )
    expired_ids = [reg_id for reg_id in expired_ids if reg_id not in paid_order_ids]
    if not expired_ids:
        return 0

    await db.execute(
        update(Registration)
        .where(Registration.id.in_(expired_ids))
        .values(status="cancelled", cancelled_at=now)
    )
    # A team seat is a roster slot as well as a seat: dropping the row alone
    # left the person on the roster with no seat (and, for a leader, a team
    # nobody could pay for). Hand the cancellation to the team lifecycle.
    from app.services.teams import on_team_registration_cancelled

    team_rows = list(
        (
            await db.execute(
                select(Registration).where(
                    Registration.id.in_(expired_ids),
                    Registration.team_id.is_not(None),
                )
            )
        ).scalars()
    )
    for row in team_rows:
        await on_team_registration_cancelled(db, row)
    cache_delete_pattern("public:*")
    cache_delete_pattern("admin:dashboard:*")
    return len(expired_ids)


async def team_member_count(db: AsyncSession, team_id: uuid.UUID) -> int:
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

