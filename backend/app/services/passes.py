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
from app.models.edition import ConventionEdition, EditionPolicy, Event
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
        if user_pass.status in ("active", "pending"):
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

    if user_pass is not None and user_pass.status in ("active", "suspended", "cancelled", "revoked"):
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
        if user_pass.status in ("cancelled", "revoked"):
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
    try_gateway: bool = True,
    actor_id: uuid.UUID | None = None,
) -> dict[str, int]:
    """Free every event seat a pass holder still holds, and return their money.

    A pass that is no longer active must not leave the attendee holding paid
    seats: the seat blocks someone else, and the ticket is a promise the door
    cannot honour. Rejection and full refunds always did this, but suspension
    and a plain pass-status change did not, so the portal kept listing
    "confirmed" seats for a cancelled pass.

    Paid add-on orders are refunded straight away. When the gateway call fails
    the money is recorded as a pending refund instead of disappearing.

    ``try_gateway=False`` is for callers whose operator may not move money
    (a rejection without ``finance.write``): the seats are still freed and a
    pending refund request is left for the finance desk instead of starting a
    gateway refund on their behalf.
    """
    from app.models.commerce import PaymentOrder, Refund
    from app.services.teams import purge_user_from_teams

    regs = list(
        (
            await db.execute(
                select(Registration).where(
                    Registration.user_id == user_id,
                    Registration.edition_id == edition_id,
                    Registration.status.in_(["confirmed", "reserved"]),
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
    queued = 0
    for order_id in paid_orders:
        order = await db.get(PaymentOrder, order_id)
        if order is None or order.status != "paid":
            continue
        # A ``per_team`` order pays for the whole roster. Refunding it because
        # the payer's pass lapsed would leave the remaining teammates holding
        # seats nobody paid for, so the order stays with a team that still has
        # members (leadership has already moved to one of them).
        team_id = (
            await db.execute(select(Team.id).where(Team.order_id == order.id))
        ).scalars().first()
        if team_id is not None:
            live_members = (
                await db.execute(
                    select(func.count(TeamMember.id)).where(
                        TeamMember.team_id == team_id
                    )
                )
            ).scalar() or 0
            if live_members:
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
        if not try_gateway:
            db.add(
                Refund(
                    order_id=order.id,
                    amount_paise=order.amount_paise,
                    reason_code="pass_not_active",
                    reason_note=reason[:500],
                    status="pending",
                    requested_by=actor_id,
                )
            )
            queued += 1
            continue
        try:
            from app.services.payments import refund_order

            await refund_order(
                db,
                order,
                amount_paise=order.amount_paise,
                reason_code="pass_not_active",
                reason_note=reason[:500],
                requested_by_id=actor_id,
            )
            refunded += 1
        except Exception as exc:  # a gateway outage must not lose the money
            logger.warning(
                "event_refund_on_pass_release_failed order=%s error=%s",
                order_id,
                str(exc)[:200],
            )
            db.add(
                Refund(
                    order_id=order.id,
                    amount_paise=order.amount_paise,
                    reason_code="pass_not_active",
                    reason_note=f"{reason} (gateway refund failed: {str(exc)[:200]})"[:500],
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


def _message(
    mode: str,
    count: int,
    required: int,
    cap_paise: int | None,
    value: int,
    cap_inclusive: bool,
    due_paise: int = 0,
) -> str | None:
    if _count_valid(mode, count, required):
        if due_paise > 0:
            return (
                f"Selections exceed the included allowance by INR {due_paise / 100:.2f}. "
                "Pay the difference to confirm."
            )
        return None
    if mode == "exact":
        return f"Select exactly {required} included event{'s' if required != 1 else ''}."
    return f"Select up to {required} included event{'s' if required != 1 else ''}."


async def selection_state(
    db: AsyncSession, user_pass: ConventionPass, policy: EditionPolicy
) -> SelectionState:
    chosen_ids = set(await selections_for(db, user_pass.id))

    events = list(
        (
            await db.execute(
                select(Event)
                .where(
                    Event.edition_id == user_pass.edition_id,
                    Event.included_eligible.is_(True),
                    Event.status.in_(["published", "open"]),
                )
                .order_by(Event.sort_order, Event.starts_at)
            )
        ).scalars()
    )

    taken = await capacity_usage(db, events) if events else {}
    deadline = aware(policy.selection_change_deadline)
    locked = bool(deadline and datetime.now(UTC) > deadline)

    selected_events = []
    total_val = 0
    count = 0
    for e in events:
        is_sel = e.id in chosen_ids
        seats = taken.get(e.id, 0)
        seats_left = seats_left_for(e, seats)
        selectable = is_sel or (not locked and (seats_left is None or seats_left > 0))
        if is_sel:
            count += 1
            total_val += e.base_value_paise
        selected_events.append(
            SelectedEvent(
                event_id=e.id,
                slug=e.slug,
                title=e.title,
                category=e.slug,
                format=e.format,
                base_value_paise=e.base_value_paise,
                addon_price_paise=e.addon_price_paise,
                starts_at=aware(e.starts_at),
                accent=e.accent,
                selected=is_sel,
                status=e.status,
                capacity=e.capacity,
                seats_taken=seats,
                seats_left=seats_left,
                selectable=selectable,
            )
        )

    mode = policy.included_selection_mode or "exact"
    cap_paise = policy.included_value_cap_paise
    cap_inclusive = bool(policy.cap_inclusive)
    required = policy.included_event_count

    excess_paise = _compute_cap_excess(total_val, cap_paise, cap_inclusive)
    paid_delta_paise = await _paid_selection_delta_paise(
        db, user_pass.user_id, user_pass.edition_id, user_pass.id
    )
    due_paise = max(0, excess_paise - paid_delta_paise)
    valid = _count_valid(mode, count, required) and not locked

    return SelectionState(
        pass_id=user_pass.id,
        pass_status=user_pass.status,
        selections=selected_events,
        count=count,
        value_paise=total_val,
        cap_paise=cap_paise,
        remaining_paise=max(0, cap_paise - total_val) if cap_paise is not None else None,
        excess_paise=excess_paise,
        paid_delta_paise=paid_delta_paise,
        due_paise=due_paise,
        required_count=required,
        up_to=mode == "up_to",
        mode=mode,
        cap_inclusive=cap_inclusive,
        valid=valid,
        deadline=deadline,
        locked=locked,
        message=(
            "Included selections are locked after the change deadline."
            if locked
            else _message(mode, count, required, cap_paise, total_val, cap_inclusive, due_paise)
        ),
    )


async def set_selections(
    db: AsyncSession,
    request: Request,
    user_pass: ConventionPass,
    event_ids: list[uuid.UUID],
    policy: EditionPolicy,
) -> tuple[SelectionState, "object | None"]:
    from app.models.commerce import PaymentOrder

    deadline = aware(policy.selection_change_deadline)
    if deadline and datetime.now(UTC) > deadline:
        raise Conflict("The deadline to change included event selections has passed.")
    if user_pass.status not in ("pending", "active"):
        raise Conflict("This pass is no longer active, so its selections cannot be changed.")
    edition = await db.get(ConventionEdition, user_pass.edition_id)
    if edition is not None and not accepting_bookings(edition):
        raise Conflict("This convention is no longer accepting new bookings.")

    # Serialise concurrent saves: one row lock on the pass stops parallel
    # requests from the same attendee, the event locks below stop two different
    # attendees from claiming the same last seat.
    await db.execute(
        select(ConventionPass.id).where(ConventionPass.id == user_pass.id).with_for_update()
    )

    unique_ids = list(dict.fromkeys(event_ids))
    if len(unique_ids) != len(event_ids):
        raise ValidationFailed("The same event was selected twice.")

    mode = policy.included_selection_mode or "exact"
    required = policy.included_event_count
    if not _count_valid(mode, len(unique_ids), required):
        raise ValidationFailed(
            f"Select exactly {required} included events."
            if mode == "exact"
            else f"Select up to {required} included events."
        )

    events: list[Event] = []
    if unique_ids:
        events = list(
            (
                await db.execute(
                    select(Event)
                    .where(
                        Event.id.in_(unique_ids),
                        Event.edition_id == user_pass.edition_id,
                    )
                    .with_for_update()
                )
            ).scalars()
        )
        if len(events) != len(unique_ids):
            raise NotFound("One or more events were not found.")
        for event in events:
            if not event.included_eligible or event.status not in ("published", "open"):
                raise ValidationFailed(f"'{event.title}' is not eligible for included selection.")
            if event.format == "team":
                # Claiming a team event as an included seat produced a lone
                # "confirmed" seat on a team fixture that no team covered.
                raise ValidationFailed(
                    f"'{event.title}' is a team event. And a team seat is created by "
                    "joining or creating a team.",
                    code="TEAM_EVENT_REQUIRES_TEAM",
                )

    if events:
        from app.services.events import capacity_usage

        event_titles = {event.id: event.title for event in events}
        conflicting = list(
            (
                await db.execute(
                    select(Registration).where(
                        Registration.user_id == user_pass.user_id,
                        Registration.edition_id == user_pass.edition_id,
                        Registration.event_id.in_(unique_ids),
                        Registration.kind.in_(["addon", "team"]),
                        Registration.status.in_(["confirmed", "reserved", "pending"]),
                    )
                )
            ).scalars()
        )
        real_conflicts = []
        team_conflicts = []
        for row in conflicting:
            if row.status == "reserved":
                # Stale unpaid add-on reservation: cancel it so attendee can claim as included pass event
                row.status = "cancelled"
                row.cancelled_at = datetime.now(UTC)
                row.cancelled_by = "superseded"
                row.cancellation_reason = "Superseded by included pass selection"
                from app.services.tickets import revoke_for_registration
                await revoke_for_registration(db, row.id)
            elif row.team_id is not None:
                # A team seat is one seat: claiming the same event as an
                # included event used to create a second confirmed row and a
                # second ticket for the same person, and the event counted them
                # twice against its capacity.
                team_conflicts.append(row)
            else:
                real_conflicts.append(row)
        if team_conflicts or real_conflicts:
            names = ", ".join(
                event_titles.get(row.event_id, "an event")
                for row in (team_conflicts + real_conflicts)
            )
            if team_conflicts:
                raise Conflict(
                    f"You are already on a team for {names}. A team seat is already your seat "
                    "for that event, so it cannot also be claimed with your pass."
                )
            raise Conflict(
                f"An add-on booking already exists for {names}. Cancel it before including it in the pass."
            )

        already_chosen = set(await selections_for(db, user_pass.id))
        taken = await capacity_usage(db, events)
        own_ids = set(
            (
                await db.execute(
                    select(Registration.event_id).where(
                        Registration.user_id == user_pass.user_id,
                        Registration.event_id.in_(unique_ids),
                        Registration.status.in_(["confirmed", "reserved"]),
                    )
                )
            ).scalars()
        )
        for event in events:
            if event.id in already_chosen:
                continue
            used = taken.get(event.id, 0)
            # An entry-counted event is measured in teams, not people, so the
            # attendee's own seat cannot be discounted from it.
            if (event.capacity_unit or "participants") != "entries" and event.id in own_ids:
                used -= 1
            if event.capacity and used >= event.capacity:
                raise Conflict(
                    f"'{event.title}' is full. Remove it from your selection or contact the organisers."
                )

    total = sum(e.base_value_paise for e in events)
    excess_paise = _compute_cap_excess(
        total, policy.included_value_cap_paise, bool(policy.cap_inclusive)
    )
    paid_delta_paise = await _paid_selection_delta_paise(
        db, user_pass.user_id, user_pass.edition_id, user_pass.id
    )
    due_paise = max(0, excess_paise - paid_delta_paise)

    if due_paise > 0:
        # Only one difference order may be open at a time. Leaving the previous
        # one alive let an attendee pay twice for the same difference when they
        # changed their mind between two saved drafts.
        await db.execute(
            update(PaymentOrder)
            .where(
                PaymentOrder.user_id == user_pass.user_id,
                PaymentOrder.edition_id == user_pass.edition_id,
                PaymentOrder.purpose == "included_selection_delta",
                PaymentOrder.status == "created",
                PaymentOrder.linked_record_id == user_pass.id,
            )
            .values(status="expired")
        )
        order = PaymentOrder(
            edition_id=user_pass.edition_id,
            user_id=user_pass.user_id,
            purpose="included_selection_delta",
            amount_paise=due_paise,
            status="created",
            linked_record_id=user_pass.id,
            notes={
                "passId": str(user_pass.id),
                "eventIds": [str(eid) for eid in unique_ids],
                "excessPaise": excess_paise,
                "paidDeltaPaise": paid_delta_paise,
            },
        )
        db.add(order)
        await db.flush()
        from app.services.payments import attach_gateway_order

        await attach_gateway_order(db, order)
        state = await selection_state(db, user_pass, policy)
        # The saved rows are still the previous selection until the difference
        # is paid, so describe the draft the order is for instead of the stale
        # saved state.
        state.count = len(unique_ids)
        state.value_paise = total
        state.excess_paise = excess_paise
        state.paid_delta_paise = paid_delta_paise
        state.due_paise = due_paise
        if policy.included_value_cap_paise is not None:
            state.remaining_paise = max(0, policy.included_value_cap_paise - total)
        state.valid = _count_valid(
            policy.included_selection_mode, len(unique_ids), policy.included_event_count
        )
        state.message = _message(
            policy.included_selection_mode,
            len(unique_ids),
            policy.included_event_count,
            policy.included_value_cap_paise,
            total,
            bool(policy.cap_inclusive),
            due_paise,
        )
        return state, order

    await db.execute(
        delete(IncludedEventSelection).where(IncludedEventSelection.pass_id == user_pass.id)
    )

    snapshots = {e.id: e.base_value_paise for e in events}
    for eid in unique_ids:
        db.add(
            IncludedEventSelection(
                pass_id=user_pass.id,
                event_id=eid,
                base_value_paise_snapshot=snapshots.get(eid, 0),
                status="active",
            )
        )

    await db.flush()
    await sync_included_registrations(db, user_pass, unique_ids)
    cache_delete_pattern("public:*")
    cache_delete_pattern("admin:dashboard:*")
    return await selection_state(db, user_pass, policy), None


async def apply_paid_selection_delta(db: AsyncSession, order) -> None:
    """Confirm included event selections after an over-cap difference is paid.

    Nothing is saved when the order is created: seats and tickets only appear
    after the money is verified, so an abandoned checkout never grants entry.
    """
    from app.models.commerce import Refund

    pass_id = order.linked_record_id
    if pass_id is None and isinstance(order.notes, dict) and order.notes.get("passId"):
        pass_id = uuid.UUID(str(order.notes["passId"]))
    user_pass = await db.get(ConventionPass, pass_id) if pass_id else None
    raw_ids = (order.notes or {}).get("eventIds") or []
    event_ids = [uuid.UUID(str(eid)) for eid in raw_ids]

    def _refund(reason_code: str, note: str) -> None:
        db.add(
            Refund(
                order_id=order.id,
                amount_paise=int(order.amount_paise),
                reason_code=reason_code,
                reason_note=note[:500],
                status="pending",
            )
        )

    blocked = await pass_gate_blocked(db, order.user_id, order.edition_id)
    if user_pass is None or user_pass.status != "active" or blocked:
        _refund(
            "pass_blocked",
            blocked or "Convention pass is no longer active.",
        )
        return

    events = list(
        (
            await db.execute(
                select(Event).where(
                    Event.id.in_(event_ids),
                    Event.edition_id == user_pass.edition_id,
                    Event.included_eligible.is_(True),
                    Event.status.in_(["published", "open"]),
                )
            )
        ).scalars()
    )
    if len(events) != len(event_ids):
        _refund(
            "event_unavailable",
            "One or more selected events closed before payment completed.",
        )
        return

    from app.services.editions import current_policy

    policy = await current_policy(db, user_pass.edition_id)
    total = sum(e.base_value_paise for e in events)
    required_excess = _compute_cap_excess(
        total, policy.included_value_cap_paise, bool(policy.cap_inclusive)
    )
    # Money already paid before this order. A second order for a difference
    # that is already covered (a stale draft, or two tabs paying at once) is
    # refunded instead of charging the same difference twice. An order that no
    # longer covers the difference (an event value changed while it sat unpaid)
    # is refunded too, so nothing is confirmed underpaid.
    paid_total = await _paid_selection_delta_paise(
        db, user_pass.user_id, user_pass.edition_id, user_pass.id
    )
    prior_paid = max(0, paid_total - int(order.amount_paise))
    covered = prior_paid + int(order.amount_paise)
    count_ok = _count_valid(
        policy.included_selection_mode, len(event_ids), policy.included_event_count
    )
    if not count_ok or prior_paid >= required_excess or covered < required_excess:
        _refund(
            "duplicate_selection_delta",
            "The included-event difference was already covered or the selection changed.",
        )
        return

    await db.execute(
        delete(IncludedEventSelection).where(IncludedEventSelection.pass_id == user_pass.id)
    )
    snapshots = {e.id: e.base_value_paise for e in events}
    for eid in event_ids:
        db.add(
            IncludedEventSelection(
                pass_id=user_pass.id,
                event_id=eid,
                base_value_paise_snapshot=snapshots.get(eid, 0),
                status="active",
            )
        )
    await db.flush()
    await sync_included_registrations(db, user_pass, event_ids)
    cache_delete_pattern("public:*")
    cache_delete_pattern("admin:dashboard:*")


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
    "selection_state",
    "set_selections",
    "sync_included_registrations",
]
