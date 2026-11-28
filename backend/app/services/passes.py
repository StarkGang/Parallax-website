"""Convention passes, bundled included selections and state transitions."""

import uuid
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_delete_pattern
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.logging import get_logger
from app.models.commerce import (
    ConventionPass,
    IncludedEventSelection,
    Registration,
    Team,
    TeamMember,
)
from app.models.edition import ConventionEdition, EditionPolicy, Event, EventCategory
from app.schemas.participant import SelectedEvent, SelectionState
from app.services.editions import accepting_bookings, aware
from app.services.events import capacity_usage, seats_left_for
from app.services.tickets import (
    issue_for_pass,
    issue_for_registration,
    revoke_for_pass,
    revoke_for_registration,
)

logger = get_logger("passes")


async def get_pass(
    db: AsyncSession, user_id: uuid.UUID, edition_id: uuid.UUID
) -> ConventionPass | None:
    from app.models.user import User

    user = await db.get(User, user_id)
    user_pass = (
        (
            await db.execute(
                select(ConventionPass)
                .where(
                    ConventionPass.user_id == user_id,
                    ConventionPass.edition_id == edition_id,
                )
                .order_by(ConventionPass.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )

    if user is not None and user.status == "suspended":
        if user_pass is None:
            return None
        # Only demote a live pass; a refunded or cancelled pass must stay
        # terminal. This branch used to overwrite "refunded" with "suspended",
        # so re-activating the account handed the pass back and re-issued its
        # entry ticket.
        if user_pass.status == "active":
            user_pass.status = "suspended"
            await revoke_for_pass(db, user_pass.id)
            await release_event_entitlements(
                db,
                user_id=user_pass.user_id,
                edition_id=user_pass.edition_id,
                reason="Your account was suspended by the organisers",
            )
            await db.flush()
        return user_pass

    if user_pass is not None and user_pass.status in ("active", "suspended", "cancelled"):
        return user_pass

    # Self-healing pass bridge: if the user has a paid college registration, activate immediately
    from app.models.registration import CollegeRegistration
    from app.services.editions import current_policy

    paid_reg = (
        await db.execute(
            select(CollegeRegistration).where(
                CollegeRegistration.user_id == user_id,
                CollegeRegistration.edition_id == edition_id,
                CollegeRegistration.payment_status == "paid",
                # A rejected or refunded registration must never resurrect its
                # pass here: rejection cancels the pass but payment_status
                # stays "paid", so without this guard the next portal visit
                # re-activated the pass and re-issued its ticket.
                CollegeRegistration.verification_status != "rejected",
                CollegeRegistration.refund_status.not_in(["initiated", "processing", "completed"]),
            )
        )
    ).scalar_one_or_none()

    if paid_reg is not None:
        policy = await current_policy(db, edition_id)
        user_pass = await activate_pass_for_registration(
            db, user_id, edition_id, policy, paid_reg.fee_paise
        )
        await db.flush()
        return user_pass

    return user_pass


async def activate_pass_for_registration(
    db: AsyncSession,
    user_id: uuid.UUID,
    edition_id: uuid.UUID,
    policy: EditionPolicy,
    price_paise: int,
) -> ConventionPass:
    """Ensure a paid college registration has an active pass and entry ticket.

    The college-registration checkout is the participant-facing purchase flow,
    but the rest of the portal (event selection, tickets, teams) reads the
    ``ConventionPass`` tables. Without this bridge a paying attendee would have
    no pass, no ticket and no team access even though money moved.
    """
    from app.models.user import User

    user = await db.get(User, user_id)
    if user is not None and user.status == "suspended":
        raise Conflict(
            "This participant's account is suspended; the pass cannot be activated.",
            code="PASS_BLOCKED",
        )

    # Never activate (or re-activate) a pass for a registration the desk has
    # rejected or refunded, no matter which caller got here.
    from app.models.registration import CollegeRegistration

    dead_reg = (
        await db.execute(
            select(CollegeRegistration).where(
                CollegeRegistration.user_id == user_id,
                CollegeRegistration.edition_id == edition_id,
                CollegeRegistration.payment_status == "paid",
                (CollegeRegistration.verification_status == "rejected")
                | (CollegeRegistration.refund_status.in_(["initiated", "processing", "completed"])),
            )
        )
    ).scalar_one_or_none()
    if dead_reg is not None:
        raise Conflict(
            "This participant's registration was rejected or refunded; "
            "the pass cannot be activated.",
            code="PASS_BLOCKED",
        )
    existing = (
        (
            await db.execute(
                select(ConventionPass)
                .where(
                    ConventionPass.user_id == user_id,
                    ConventionPass.edition_id == edition_id,
                )
                .order_by(ConventionPass.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if existing is not None and existing.status == "suspended":
        raise Conflict(
            "This participant's pass is suspended by the organisers; it cannot be activated.",
            code="PASS_BLOCKED",
        )

    now = datetime.now(UTC)
    if existing is None:
        existing = ConventionPass(
            edition_id=edition_id,
            user_id=user_id,
            price_paise=price_paise,
            policy_version=policy.version,
            lunch_days=policy.lunch_included_days or [],
            status="active",
            paid_at=now,
        )
        db.add(existing)
        await db.flush()
    else:
        existing.status = "active"
        existing.paid_at = existing.paid_at or now
        # The price is a receipt, not a live pointer at the current policy.
        # Rewriting it on every activation made a pass sold under v1 claim the
        # v2 price that was never collected.
        if existing.price_paise is None:
            existing.price_paise = price_paise
        existing.policy_version = policy.version
        existing.lunch_days = policy.lunch_included_days or []
        await db.flush()

    await issue_for_pass(db, existing)
    await db.flush()
    return existing


async def pass_gate_blocked(db: AsyncSession, user_id: uuid.UUID, edition_id: uuid.UUID) -> str | None:
    """Return a reason string when the attendee's college registration is
    rejected or refunded, or when their pass/account is suspended, blocking
    event selection and add-on purchases.
    """
    from app.models.user import User

    user = await db.get(User, user_id)
    if user is not None and user.status == "suspended":
        return "Your account has been suspended by the organisers. Event selection and add-on purchases are closed."

    user_pass = (
        await db.execute(
            select(ConventionPass).where(
                ConventionPass.user_id == user_id,
                ConventionPass.edition_id == edition_id,
            ).order_by(ConventionPass.created_at.desc()).limit(1)
        )
    ).scalars().first()
    if user_pass is not None:
        if user_pass.status == "suspended":
            return "Your convention pass has been suspended by the organisers. Event selection and add-on purchases are closed."
        if user_pass.status == "cancelled":
            return "Your convention pass is not active. Event selection and add-on purchases are closed."

    from app.models.registration import CollegeRegistration

    row = (
        await db.execute(
            select(CollegeRegistration).where(
                CollegeRegistration.user_id == user_id,
                CollegeRegistration.edition_id == edition_id,
                CollegeRegistration.payment_status.in_(["paid", "completed", "refunded"]),
                (CollegeRegistration.verification_status == "rejected")
                | (CollegeRegistration.refund_status.in_(["initiated", "processing", "completed"])),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    if row.payment_status == "refunded":
        return "Your convention pass was refunded. Event selection and add-on purchases are closed."
    if row.refund_status in ("initiated", "processing"):
        return "A refund is in progress on your convention pass. Event selection and add-on purchases are closed until it settles."
    if row.verification_status == "rejected":
        return "Your convention pass was rejected by the registration desk. Event selection and add-on purchases are closed."
    # A completed *partial* refund leaves the pass valid: the attendee kept the
    # entitlement they were not refunded for (see overall_state).
    return None


async def drop_attendance(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    edition_id: uuid.UUID,
    event_id: uuid.UUID | None = None,
) -> int:
    """Delete check-in rows that belonged to an entitlement being taken away.

    Attendance used to survive the revocation of the ticket that earned it, so
    the roster, the exports and the day counters still showed a refunded or
    cancelled attendee as present. The audit row keeps who marked it.
    """
    from sqlalchemy import delete

    from app.models.commerce import AttendanceRecord

    statement = delete(AttendanceRecord).where(
        AttendanceRecord.user_id == user_id,
        AttendanceRecord.edition_id == edition_id,
    )
    if event_id is not None:
        statement = statement.where(AttendanceRecord.event_id == event_id)
    result = await db.execute(statement)
    return int(result.rowcount or 0)


async def release_event_entitlements(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    edition_id: uuid.UUID,
    reason: str,
    refund_paid_events: bool = True,
    actor_id: uuid.UUID | None = None,
) -> dict[str, int]:
    """Free every event seat a pass holder still holds, and return their money.

    A pass that is no longer active must not leave the attendee holding paid
    seats: the seat blocks someone else, and the ticket is a promise the door
    cannot honour. ``pending`` seats (an event that needs desk approval) count
    as held seats too and are cancelled here, so a revoke really does remove
    every event registration. Rejection and full refunds always did this, but
    suspension and a plain pass-status change did not, so the portal kept
    listing "confirmed" seats for a cancelled pass.

    Money never moves from here. Every paid order whose seats this releases gets
    one **pending** refund request with its full remaining amount; the finance
    desk approves it in the ledger. That is the same rule as a user
    cancellation, and it means an admin reject/revoke cannot take money out of
    the gateway by accident. ``refund_paid_events=False`` (the desk unticked the
    box) creates nothing and the money stays on the order as paid and retained.
    """
    from app.models.commerce import PaymentOrder, Refund
    from app.services.teams import purge_user_from_teams

    regs = list(
        (
            await db.execute(
                select(Registration).where(
                    Registration.user_id == user_id,
                    Registration.edition_id == edition_id,
                    # ``pending`` matters: a seat on a ``requires_approval`` event
                    # waits there for the desk. Leaving it behind meant a revoked
                    # pass kept a live event registration that the roster still
                    # listed, so the revoke never actually removed the seat.
                    Registration.status.in_(["confirmed", "reserved", "pending"]),
                )
            )
        ).scalars()
    )
    paid_orders: list[uuid.UUID] = []
    for reg in regs:
        reg.status = "cancelled"
        reg.cancelled_at = datetime.now(UTC)
        reg.cancelled_by = "admin"
        reg.cancellation_reason = reason[:500]
        await revoke_for_registration(db, reg.id)
        if (
            refund_paid_events
            and reg.order_id is not None
            and (reg.fee_paise or 0) > 0
            and reg.order_id not in paid_orders
        ):
            paid_orders.append(reg.order_id)

    # A person without a valid pass cannot stay on a team roster: they would
    # occupy a team slot and appear on the door list.
    await purge_user_from_teams(db, user_id, edition_id)
    # Their tickets are gone, so their check-ins are not evidence of anything any
    # more - and the roster/export must not keep showing them as present. This
    # applies to a pass-only entry too, not just to event seats.
    await drop_attendance(db, user_id=user_id, edition_id=edition_id)

    # Included event selections must be marked cancelled when pass entitlements are released.
    user_pass_ids = list(
        (
            await db.execute(
                select(ConventionPass.id).where(
                    ConventionPass.user_id == user_id,
                    ConventionPass.edition_id == edition_id,
                )
            )
        ).scalars()
    )
    if user_pass_ids:
        await db.execute(
            update(IncludedEventSelection)
            .where(IncludedEventSelection.pass_id.in_(user_pass_ids))
            .values(status="cancelled")
        )
        if refund_paid_events:
            delta_orders = list(
                (
                    await db.execute(
                        select(PaymentOrder.id).where(
                            PaymentOrder.user_id == user_id,
                            PaymentOrder.edition_id == edition_id,
                            PaymentOrder.purpose == "included_selection_delta",
                            PaymentOrder.status == "paid",
                            PaymentOrder.linked_record_id.in_(user_pass_ids),
                        )
                    )
                ).scalars()
            )
            for oid in delta_orders:
                if oid not in paid_orders:
                    paid_orders.append(oid)

    await db.flush()

    refunded = 0
    queued = 0  # refunded stays 0: nothing is settled from here any more
    for order_id in paid_orders:
        order = (
            await db.execute(
                select(PaymentOrder)
                .where(PaymentOrder.id == order_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalars().first()
        if order is None or order.status != "paid":
            continue
        still_claimed = (
            await db.execute(
                select(func.count(Registration.id)).where(
                    Registration.order_id == order.id,
                    Registration.status.in_(("confirmed", "reserved", "pending")),
                )
            )
        ).scalar() or 0
        if still_claimed:
            continue
        already_committed = int(
            (
                await db.execute(
                    select(func.coalesce(func.sum(Refund.amount_paise), 0)).where(
                        Refund.order_id == order.id,
                        Refund.status.in_(("pending", "processing", "processed")),
                    )
                )
            ).scalar()
            or 0
        )
        available = max(0, int(order.amount_paise) - already_committed)
        if available <= 0:
            continue
        # Money never leaves the gateway from here. An admin reject/revoke (and
        # every system cascade that frees seats) only *queues* the refund, so the
        # desk decides it in the ledger - the same rule as a user cancellation.
        db.add(
            Refund(
                order_id=order.id,
                amount_paise=available,
                reason_code="pass_not_active",
                reason_note=reason[:500],
                status="pending",
                requested_by=actor_id,
            )
        )
        queued += 1
    if regs:
        cache_delete_pattern("public:*")
        cache_delete_pattern("admin:dashboard:*")
    return {"seats": len(regs), "refunded": refunded, "queued": queued}


async def selections_for(db: AsyncSession, pass_id: uuid.UUID) -> list[uuid.UUID]:
    rows = list(
        (
            await db.execute(
                select(IncludedEventSelection.event_id).where(
                    IncludedEventSelection.pass_id == pass_id
                )
            )
        ).scalars()
    )
    return rows


def _count_valid(mode: str, count: int, required: int) -> bool:
    return count == required if mode == "exact" else count <= required


def _compute_cap_excess(total_val: int, cap_paise: int | None, cap_inclusive: bool) -> int:
    if cap_paise is None:
        return 0
    if cap_inclusive:
        return max(0, total_val - cap_paise)
    return max(0, total_val - max(0, cap_paise - 1))


async def _paid_selection_delta_paise(
    db: AsyncSession, user_id: uuid.UUID, edition_id: uuid.UUID, pass_id: uuid.UUID
) -> int:
    """Difference already settled for this pass, so a swap never double-charges."""
    from app.models.commerce import PaymentOrder

    total = (
        await db.execute(
            select(func.coalesce(func.sum(PaymentOrder.amount_paise), 0)).where(
                PaymentOrder.user_id == user_id,
                PaymentOrder.edition_id == edition_id,
                PaymentOrder.purpose == "included_selection_delta",
                PaymentOrder.status == "paid",
                PaymentOrder.linked_record_id == pass_id,
            )
        )
    ).scalar_one()
    return int(total or 0)


async def sync_included_registrations(
    db: AsyncSession, user_pass: ConventionPass, event_ids: list[uuid.UUID]
) -> None:
    """Keep included registrations and their event tickets aligned with the saved selection."""
    if user_pass.status != "active":
        return

    # A saved selection is not a promise that the event is still running. Events
    # closed after the selection was saved used to be re-confirmed by the next
    # sync, which handed a cancelled event's seat and ticket back to the holder.
    if event_ids:
        open_ids = set(
            (
                await db.execute(
                    select(Event.id).where(
                        Event.id.in_(list(event_ids)),
                        Event.status.in_(["published", "open"]),
                    )
                )
            ).scalars()
        )
        event_ids = [eid for eid in event_ids if eid in open_ids]

    keep = set(event_ids)
    existing = list(
        (
            await db.execute(
                select(Registration).where(
                    Registration.user_id == user_pass.user_id,
                    Registration.edition_id == user_pass.edition_id,
                    Registration.kind == "included",
                )
            )
        ).scalars()
    )
    by_event = {row.event_id: row for row in existing}

    for event_id, row in by_event.items():
        if event_id not in keep and row.status != "cancelled":
            row.status = "cancelled"
            row.cancelled_at = datetime.now(UTC)
            await revoke_for_registration(db, row.id)

    for eid in keep:
        event_obj = await db.get(Event, eid)
        needs_approval = bool(event_obj and event_obj.requires_approval)
        target_status = "pending" if needs_approval else "confirmed"
        row = by_event.get(eid)
        if row is not None:
            if row.status == "cancelled":
                row.status = target_status
                row.cancelled_at = None
                row.cancelled_by = None
                row.cancellation_reason = None
            if row.status == "confirmed":
                await issue_for_registration(db, row)
            continue
        existing_other = (
            await db.execute(
                select(Registration).where(
                    Registration.user_id == user_pass.user_id,
                    Registration.event_id == eid,
                    Registration.status.in_(["confirmed", "reserved", "pending"]),
                )
            )
        ).scalars().first()
        if existing_other is not None:
            existing_other.kind = "included"
            if existing_other.status == "confirmed":
                await issue_for_registration(db, existing_other)
            continue

        reg = Registration(
            edition_id=user_pass.edition_id,
            user_id=user_pass.user_id,
            event_id=eid,
            kind="included",
            fee_paise=0,
            status=target_status,
            registration_number=f"INC-{uuid.uuid4().hex[:8].upper()}",
        )
        db.add(reg)
        await db.flush()
        if reg.status == "confirmed":
            await issue_for_registration(db, reg)
    await db.flush()


__all__ = [
    "get_pass",
    "activate_pass_for_registration",
    "release_event_entitlements",
    "selections_for",
    "sync_included_registrations",
]
