"""Event pricing: one server-side quote instead of free/paid screen sections.

The participant no longer picks from an "included" list and a "paid" list. They
choose events; this module decides, deterministically, which of them the pass
allowance covers and what is left to pay. Checkout charges exactly that
difference.

Everything here is integer paise. Three rules keep the money honest:

1. A confirmed seat is frozen. Its ``kind`` and ``fee_paise`` are never re-priced
   by a later selection, so a repack can only affect seats that are not yet
   confirmed.
2. A quote is a real row. Checkout consumes it once, which makes retries and
   double clicks idempotent.
3. A negative difference is a refund to the original method. There is no
   wallet and no store credit.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_delete_pattern
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.models.commerce import (
    ConventionPass,
    EventQuote,
    PaymentOrder,
    Refund,
    Registration,
    Team,
    TeamMember,
)
from app.models.edition import ConventionEdition, EditionPolicy, Event
from app.models.user import User
from app.services.audit import record
from app.services.editions import accepting_bookings, aware, current_policy
from app.services.events import capacity_usage, event_open
from app.services.tickets import issue_for_registration, revoke_for_registration

QUOTE_TTL_MINUTES = 20
LIVE_SEAT_STATUSES = ("confirmed", "reserved", "pending")
INCLUDED = "included"
FREE = "free"
ADDON = "addon"
TEAM_PER_PARTICIPANT = "team_per_participant"


# --------------------------------------------------------------------------- #
# Allowance packing (pure)
# --------------------------------------------------------------------------- #
def base_value(event: Event) -> int:
    return max(0, int(event.base_value_paise or 0))


def list_price(event: Event) -> int:
    return max(0, int(event.addon_price_paise or 0))


def allowance_pack(
    events: list[Event],
    *,
    count: int,
    cap_paise: int | None,
    cap_inclusive: bool,
    frozen_count: int = 0,
    frozen_value: int = 0,
    pack_order: int = 0,
) -> list[uuid.UUID]:
    """Which of ``events`` the pass covers.

    ``count == -1`` means unlimited event count (only ``cap_paise`` limits
    coverage). ``pack_order``: ``0`` = cheapest first (default), ``1`` = most
    expensive first. ``frozen_*`` are already-confirmed included seats.
    """
    unlimited_count = int(count) < 0
    remaining_count = None if unlimited_count else max(0, int(count) - int(frozen_count))
    if (remaining_count is not None and remaining_count <= 0) or not events:
        return []
    remaining_value = None
    if cap_paise is not None:
        remaining_value = max(0, int(cap_paise) - int(frozen_value))
    reverse_value = int(pack_order or 0) == 1
    ordered = sorted(
        events,
        key=lambda e: (
            -base_value(e) if reverse_value else base_value(e),
            aware(e.starts_at) or datetime.min,
            str(e.id),
        ),
    )
    covered: list[uuid.UUID] = []
    used = 0
    for event in ordered:
        if remaining_count is not None and len(covered) >= remaining_count:
            break
        value = base_value(event)
        if not event.included_eligible:
            continue
        if remaining_value is not None:
            nxt = used + value
            if (nxt > remaining_value) if cap_inclusive else (nxt >= remaining_value):
                continue
        covered.append(event.id)
        used += value
    return covered


def team_basis(event: Event, policy: EditionPolicy) -> str:
    # per_team (leader-pays) has been removed: every member pays their own seat.
    return TEAM_PER_PARTICIPANT


def _kind_for(event: Event, price: int, covered: bool) -> tuple[str, str, int]:
    """(registration kind, price basis, amount due)."""
    if covered:
        return INCLUDED, INCLUDED, 0
    if price <= 0:
        return FREE, FREE, 0
    return ADDON, ADDON, price


# --------------------------------------------------------------------------- #
# Quote
# --------------------------------------------------------------------------- #
async def _live_regs(
    db: AsyncSession, user_id: uuid.UUID, edition_id: uuid.UUID
) -> dict[uuid.UUID, Registration]:
    rows = list(
        (
            await db.execute(
                select(Registration).where(
                    Registration.user_id == user_id,
                    Registration.edition_id == edition_id,
                    Registration.status.in_(LIVE_SEAT_STATUSES),
                )
            )
        ).scalars()
    )
    return {row.event_id: row for row in rows}


async def _frozen_allowance(
    db: AsyncSession, user_id: uuid.UUID, edition_id: uuid.UUID
) -> tuple[int, int]:
    rows = list(
        (
            await db.execute(
                select(Registration).where(
                    Registration.user_id == user_id,
                    Registration.edition_id == edition_id,
                    Registration.kind == INCLUDED,
                    Registration.status == "confirmed",
                )
            )
        ).scalars()
    )
    count = 0
    value = 0
    for row in rows:
        event = await db.get(Event, row.event_id)
        if event is None:
            continue
        count += 1
        value += base_value(event)
    return count, value


async def _assert_bookable(
    db: AsyncSession,
    user_id: uuid.UUID,
    edition: ConventionEdition,
    policy: EditionPolicy,
    events: list[Event],
) -> None:
    user = await db.get(User, user_id)
    if user is not None and user.status == "suspended":
        raise ValidationFailed(
            "Your account has been suspended by the organisers. Event registration is closed."
        )
    user_pass = (
        await db.execute(
            select(ConventionPass)
            .where(
                ConventionPass.user_id == user_id,
                ConventionPass.edition_id == edition.id,
            )
            .order_by(ConventionPass.created_at.desc())
            .limit(1)
        )
    ).scalars().first()
    if user_pass is not None and user_pass.status == "suspended":
        raise ValidationFailed(
            "Your convention pass has been suspended by the organisers. Event registration is closed."
        )
    if policy.addon_requires_pass and (
        user_pass is None or user_pass.status != "active"
    ):
        raise ValidationFailed("You must hold an active pass to register for events.")

    taken = await capacity_usage(db, events)
    for event in events:
        if not event_open(event):
            raise Conflict(f"Registration for '{event.title}' is closed.")
        used = taken.get(event.id, 0)
        if event.capacity and used >= int(event.capacity):
            raise Conflict(f"Event '{event.title}' is sold out.")
        if event.starts_at and aware(event.starts_at) <= datetime.now(UTC):
            raise Conflict(f"'{event.title}' has already started.")


async def build_quote(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    edition: ConventionEdition,
    policy: EditionPolicy,
    event_ids: list[uuid.UUID],
    persist: bool = True,
) -> EventQuote:
    """Price exactly what is left to pay for this basket.

    Already live seats (confirmed, reserved or pending) are never re-charged and
    never re-created; they show on the quote as ``already_confirmed`` so the
    attendee can see the whole plan without paying twice.
    """
    if not accepting_bookings(edition):
        raise Conflict("This convention is no longer accepting new bookings.")

    wanted = list(dict.fromkeys(event_ids))
    if len(wanted) != len(event_ids):
        raise ValidationFailed("The same event was selected twice.")

    events = (
        list(
            (
                await db.execute(
                    select(Event)
                    .where(Event.id.in_(wanted), Event.edition_id == edition.id)
                    .with_for_update()
                )
            ).scalars()
        )
        if wanted
        else []
    )
    if len(events) != len(wanted):
        raise NotFound("One or more events not found.")

    live = await _live_regs(db, user_id, edition.id)
    fresh = [e for e in events if e.id not in live]
    await _assert_bookable(db, user_id, edition, policy, fresh)

    frozen_count, frozen_value = await _frozen_allowance(db, user_id, edition.id)
    covered_ids = set(
        allowance_pack(
            [e for e in fresh if list_price(e) > 0],
            count=policy.included_event_count,
            cap_paise=policy.included_value_cap_paise,
            cap_inclusive=bool(policy.cap_inclusive),
            frozen_count=frozen_count,
            frozen_value=frozen_value,
            pack_order=int(getattr(policy, "allowance_pack_order", 0) or 0),
        )
    )

    lines: list[dict] = []
    covered_paise = 0
    for event in events:
        price = list_price(event)
        existing = live.get(event.id)
        if existing is not None:
            lines.append(
                {
                    "eventId": str(event.id),
                    "title": event.title,
                    "slug": event.slug,
                    "format": event.format,
                    "baseValuePaise": base_value(event),
                    "listPaise": price,
                    "coveredPaise": price if existing.kind == INCLUDED else 0,
                    "duePaise": 0,
                    "basis": existing.price_basis or existing.kind,
                    "action": "already_confirmed"
                    if existing.status == "confirmed"
                    else "already_held",
                    "registrationId": str(existing.id),
                }
            )
            continue
        covered = event.id in covered_ids
        kind, basis, due = _kind_for(event, price, covered)
        if covered:
            covered_paise += price
        lines.append(
            {
                "eventId": str(event.id),
                "title": event.title,
                "slug": event.slug,
                "format": event.format,
                "baseValuePaise": base_value(event),
                "listPaise": price,
                "coveredPaise": price if covered else 0,
                "duePaise": due,
                "basis": basis,
                "kind": kind,
                "action": "create",
                "teamBasis": team_basis(event, policy) if event.format == "team" else None,
            }
        )

    due = sum(int(line["duePaise"]) for line in lines)

    if not persist:
        return EventQuote(
            edition_id=edition.id,
            user_id=user_id,
            lines=lines,
            policy_version=policy.version,
            covered_paise=covered_paise,
            due_paise=due,
            status="open",
            expires_at=datetime.now(UTC) + timedelta(minutes=QUOTE_TTL_MINUTES),
        )

    # A newer basket supersedes an older draft. The old quote is expired, not
    # deleted, so a late checkout attempt is refused instead of charging a
    # basket the attendee has already changed.
    stale = list(
        (
            await db.execute(
                select(EventQuote).where(
                    EventQuote.user_id == user_id,
                    EventQuote.edition_id == edition.id,
                    EventQuote.status == "open",
                )
            )
        ).scalars()
    )
    for row in stale:
        row.status = "expired"

    quote = EventQuote(
        edition_id=edition.id,
        user_id=user_id,
        lines=lines,
        policy_version=policy.version,
        covered_paise=covered_paise,
        due_paise=due,
        status="open",
        expires_at=datetime.now(UTC) + timedelta(minutes=QUOTE_TTL_MINUTES),
    )
    db.add(quote)
    await db.flush()
    return quote


async def quotes_match_prices(db: AsyncSession, quote: EventQuote) -> None:
    """Refuse a stale basket when an admin changed a price in the meantime."""
    for line in quote.lines or []:
        if line.get("action") != "create":
            continue
        event = await db.get(Event, uuid.UUID(str(line["eventId"])))
        if event is None:
            raise Conflict("An event in this basket no longer exists.", code="QUOTE_STALE")
        if list_price(event) != int(line.get("listPaise", -1)):
            raise Conflict(
                f"The price of '{event.title}' changed. Review your basket and pay again.",
                code="QUOTE_STALE",
            )
        if base_value(event) != int(line.get("baseValuePaise", -1)):
            raise Conflict(
                f"The allowance value of '{event.title}' changed. Review your basket and pay again.",
                code="QUOTE_STALE",
            )
    policy = await current_policy(db, quote.edition_id)
    if int(policy.version) != int(quote.policy_version):
        raise Conflict(
            "The pass allowance changed. Review your basket and pay again.",
            code="QUOTE_STALE",
        )


async def consume_quote(
    db: AsyncSession, *, user_id: uuid.UUID, quote: EventQuote
) -> tuple[list[Registration], PaymentOrder | None]:
    """Turn a quote into seats and, if anything is due, one order."""
    if quote.user_id != user_id:
        raise NotFound("Quote not found.")
    if quote.status == "consumed":
        order = await db.get(PaymentOrder, quote.order_id) if quote.order_id else None
        regs = list(
            (
                await db.execute(
                    select(Registration).where(Registration.quote_id == quote.id)
                )
            ).scalars()
        )
        return regs, order
    if quote.status != "open":
        raise Conflict("This basket is no longer valid. Rebuild it.", code="QUOTE_EXPIRED")
    if aware(quote.expires_at) <= datetime.now(UTC):
        quote.status = "expired"
        raise Conflict("This basket expired. Rebuild it.", code="QUOTE_EXPIRED")

    await quotes_match_prices(db, quote)

    now = datetime.now(UTC)
    hold = timedelta(minutes=QUOTE_TTL_MINUTES)
    regs: list[Registration] = []
    for line in quote.lines or []:
        if line.get("action") != "create":
            continue
        due = int(line.get("duePaise", 0))
        seat = Registration(
            edition_id=quote.edition_id,
            user_id=user_id,
            event_id=uuid.UUID(str(line["eventId"])),
            kind=str(line.get("kind") or ADDON),
            price_basis=str(line.get("basis") or ADDON),
            quote_id=quote.id,
            fee_paise=due,
            status="reserved" if due > 0 else "confirmed",
            reservation_expires_at=now + hold if due > 0 else None,
            registration_number=(
                f"{'INC' if line.get('kind') == INCLUDED else 'REG'}-"
                f"{uuid.uuid4().hex[:8].upper()}"
            ),
        )
        db.add(seat)
        regs.append(seat)
    await db.flush()

    order = None
    seat_total = sum(int(r.fee_paise) for r in regs)
    if seat_total > 0:
        from app.services.payments import calculate_platform_fee

        policy = await current_policy(db, quote.edition_id)
        platform_fee, payable = calculate_platform_fee(seat_total, policy)
        order = PaymentOrder(
            edition_id=quote.edition_id,
            user_id=user_id,
            purpose="registration",
            amount_paise=payable,
            platform_fee_paise=platform_fee,
            status="created",
            notes={
                "quoteId": str(quote.id),
                "eventIds": [
                    line["eventId"]
                    for line in quote.lines or []
                    if line.get("action") == "create"
                ],
            },
        )
        db.add(order)
        await db.flush()
        for seat in regs:
            if seat.fee_paise > 0:
                seat.order_id = order.id
        quote.order_id = order.id
        from app.services.payments import attach_gateway_order

        await attach_gateway_order(db, order)
    else:
        for seat in regs:
            await issue_for_registration(db, seat)

    quote.status = "consumed"
    await db.flush()
    cache_delete_pattern("public:*")
    cache_delete_pattern("admin:dashboard:*")
    return regs, order


# --------------------------------------------------------------------------- #
# The basket (server state shared by the worklist and every event page)
# --------------------------------------------------------------------------- #
def basket_payload(quote: EventQuote | None) -> dict:
    if quote is None:
        return {
            "quoteId": None,
            "lines": [],
            "coveredPaise": 0,
            "duePaise": 0,
            "expiresAt": None,
        }
    return {
        "quoteId": str(quote.id),
        "lines": list(quote.lines or []),
        "coveredPaise": int(quote.covered_paise),
        "duePaise": int(quote.due_paise),
        "expiresAt": aware(quote.expires_at).isoformat() if quote.expires_at else None,
    }


async def open_basket(
    db: AsyncSession, user_id: uuid.UUID, edition_id: uuid.UUID
) -> EventQuote | None:
    quote = (
        await db.execute(
            select(EventQuote)
            .where(
                EventQuote.user_id == user_id,
                EventQuote.edition_id == edition_id,
                EventQuote.status == "open",
            )
            .order_by(EventQuote.created_at.desc())
            .limit(1)
        )
    ).scalars().first()
    if quote is None:
        return None
    if aware(quote.expires_at) <= datetime.now(UTC):
        quote.status = "expired"
        await db.flush()
        return None
    return quote


def _basket_event_ids(quote: EventQuote | None) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []
    for line in (quote.lines if quote is not None else None) or []:
        if line.get("action") != "create":
            continue
        try:
            ids.append(uuid.UUID(str(line["eventId"])))
        except (KeyError, ValueError):
            continue
    return ids


async def create_seat_now(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    edition: ConventionEdition,
    policy: EditionPolicy,
    event: Event,
) -> tuple[Registration | None, PaymentOrder | None]:
    """Create one confirmed/held seat without touching the open basket.

    Team formation uses this when the attendee has no seat yet. It prices the
    single event through the same (non-persisted) quote as everything else, but
    it must not expire the basket: losing another event because someone clicked
    "Create team" would be a silent data loss.
    """
    current = await open_basket(db, user_id, edition.id)
    for line in (current.lines if current is not None else None) or []:
        if line.get("action") == "create" and str(line.get("eventId")) == str(event.id):
            raise Conflict(
                "This seat is already in your basket. Confirm the basket first, then form the team.",
                code="SEAT_IN_BASKET",
            )

    existing = await _live_regs(db, user_id, edition.id)
    if event.id in existing:
        return existing[event.id], None

    quote = await build_quote(
        db,
        user_id=user_id,
        edition=edition,
        policy=policy,
        event_ids=[event.id],
        persist=False,
    )
    line = next(
        (item for item in quote.lines or [] if item.get("action") == "create"),
        None,
    )
    if line is None:
        return existing.get(event.id), None

    due = int(line.get("duePaise", 0))
    seat = Registration(
        edition_id=edition.id,
        user_id=user_id,
        event_id=event.id,
        kind=str(line.get("kind") or ADDON),
        price_basis=str(line.get("basis") or ADDON),
        fee_paise=due,
        status="reserved" if due > 0 else "confirmed",
        reservation_expires_at=(
            datetime.now(UTC) + timedelta(minutes=QUOTE_TTL_MINUTES) if due > 0 else None
        ),
        registration_number=(
            f"{'INC' if line.get('kind') == INCLUDED else 'REG'}-"
            f"{uuid.uuid4().hex[:8].upper()}"
        ),
    )
    db.add(seat)
    await db.flush()

    order = None
    if due > 0:
        from app.services.payments import attach_gateway_order, calculate_platform_fee

        platform_fee, total_due = calculate_platform_fee(due, policy)
        order = PaymentOrder(
            edition_id=edition.id,
            user_id=user_id,
            purpose="registration",
            amount_paise=total_due,
            platform_fee_paise=platform_fee,
            status="created",
            notes={"eventIds": [str(event.id)], "kind": "single_seat"},
        )
        db.add(order)
        await db.flush()
        seat.order_id = order.id
        await attach_gateway_order(db, order)
    else:
        await issue_for_registration(db, seat)
    await db.flush()
    return seat, order


async def basket_add(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    edition: ConventionEdition,
    policy: EditionPolicy,
    event_ids: list[uuid.UUID],
) -> EventQuote:
    """Add events to the one open basket. Idempotent for already-added ids."""
    current = await open_basket(db, user_id, edition.id)
    merged = list(dict.fromkeys([*_basket_event_ids(current), *event_ids]))
    if not merged:
        raise ValidationFailed("Choose at least one event.")
    return await build_quote(
        db,
        user_id=user_id,
        edition=edition,
        policy=policy,
        event_ids=merged,
    )


async def basket_remove(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    edition: ConventionEdition,
    policy: EditionPolicy,
    event_id: uuid.UUID,
) -> EventQuote | None:
    """Remove one draft seat. Confirmed seats are cancelled, not basket items."""
    current = await open_basket(db, user_id, edition.id)
    if current is None:
        return None
    remaining = [eid for eid in _basket_event_ids(current) if eid != event_id]
    if not remaining:
        current.status = "expired"
        await db.flush()
        cache_delete_pattern("public:*")
        return None
    return await build_quote(
        db,
        user_id=user_id,
        edition=edition,
        policy=policy,
        event_ids=remaining,
    )


# --------------------------------------------------------------------------- #
# Removing a seat (direct refund)
# --------------------------------------------------------------------------- #
async def _refund_seat(
    db: AsyncSession,
    *,
    reg: Registration,
    reason_code: str,
    reason_note: str,
) -> dict:
    """Refund one paid seat to its original payment method."""
    result = {"refundedPaise": 0, "refundPending": False}
    if reg.order_id is None or int(reg.fee_paise or 0) <= 0:
        return result
    order = await db.get(PaymentOrder, reg.order_id)
    if order is None or order.status != "paid":
        return result

    # One order can carry several seats. Refund only this seat's share, and
    # never more than the order still holds un-refunded.
    already = (
        await db.execute(
            select(Refund).where(
                Refund.order_id == order.id,
                Refund.status.in_(("pending", "processing", "processed")),
            )
        )
    ).scalars().all()
    refunded = sum(int(r.amount_paise) for r in already)
    available = max(0, int(order.amount_paise) - refunded)
    amount = min(int(reg.fee_paise), available)
    if amount <= 0:
        return result

    try:
        from app.services.payments import refund_order

        await refund_order(
            db,
            order,
            amount_paise=amount,
            reason_code=reason_code,
            reason_note=reason_note[:500],
            requested_by_id=reg.user_id,
        )
        result["refundedPaise"] = amount
    except Exception as exc:  # gateway outage must not keep the money
        db.add(
            Refund(
                order_id=order.id,
                amount_paise=amount,
                reason_code=reason_code,
                reason_note=f"{reason_note} (gateway refund failed: {str(exc)[:200]})"[:500],
                status="pending",
                requested_by_id=reg.user_id,
            )
        )
        result["refundPending"] = True
    return result


async def remove_seat(
    db: AsyncSession,
    *,
    request: Request | None,
    user_id: uuid.UUID,
    edition: ConventionEdition,
    event_id: uuid.UUID,
) -> dict:
    """Remove one live seat and settle its money.

    Uses the same refund matrix as the plan: a paid seat outside the
    cancellation window is refunded to the original method, an included/free
    seat simply returns its allowance, and a per-team rider never takes the
    team's money with them.
    """
    reg = (
        await db.execute(
            select(Registration)
            .where(
                Registration.user_id == user_id,
                Registration.edition_id == edition.id,
                Registration.event_id == event_id,
                Registration.status.in_(LIVE_SEAT_STATUSES),
            )
            .limit(1)
        )
    ).scalars().first()
    if reg is None:
        raise NotFound("You do not hold a seat for this event.")

    event = await db.get(Event, event_id)
    entry = aware(event.starts_at) if event is not None else None
    # A cancelled event is always refundable: the attendee did not change plans.
    organiser_cancelled = event is not None and event.status in ("cancelled", "closed")
    if (
        not organiser_cancelled
        and entry is not None
        and entry <= datetime.now(UTC) + timedelta(hours=24)
    ):
        raise Conflict(
            "Registrations cannot be removed within 24 hours of the event start. "
            "Contact the helpdesk if you cannot attend.",
            code="CANCELLATION_CLOSED",
        )

    team_id = reg.team_id
    was_confirmed = reg.status == "confirmed"
    reg.status = "cancelled"
    reg.cancelled_at = datetime.now(UTC)
    reg.cancelled_by = "user"
    reg.cancellation_reason = "Removed from the event worklist"
    await revoke_for_registration(db, reg.id)

    # A held (unpaid) seat closes its order so a late payment cannot revive it.
    # A shared order (multi-event or per_team) is only expired when no other
    # live seat still references it.
    from app.services.payments import expire_order_if_unshared

    await expire_order_if_unshared(
        db, reg.order_id, exclude_registration_id=reg.id
    )

    result = {
        "removed": True,
        "seatId": str(reg.id),
        "refundedPaise": 0,
        "refundPending": False,
        "teamNewLeaderId": None,
    }
    if was_confirmed:
        # A rider on a per-team payment owns no money; only their own share is
        # settled (which is zero), and the team keeps the entry it paid for.
        owed = int(reg.fee_paise or 0)
        if owed > 0:
            result.update(
                await _refund_seat(
                    db,
                    reg=reg,
                    reason_code="attendee_cancelled",
                    reason_note="Seat removed from the event worklist",
                )
            )

    if reg.kind == INCLUDED:
        from sqlalchemy import delete

        from app.models.commerce import IncludedEventSelection

        user_pass = (
            await db.execute(
                select(ConventionPass)
                .where(
                    ConventionPass.user_id == user_id,
                    ConventionPass.edition_id == edition.id,
                )
                .order_by(ConventionPass.created_at.desc())
                .limit(1)
            )
        ).scalars().first()
        if user_pass is not None:
            await db.execute(
                delete(IncludedEventSelection).where(
                    IncludedEventSelection.pass_id == user_pass.id,
                    IncludedEventSelection.event_id == event_id,
                )
            )

    if team_id is not None:
        from app.services.teams import on_team_registration_cancelled

        new_leader = await on_team_registration_cancelled(db, reg)
        result["teamNewLeaderId"] = str(new_leader) if new_leader else None

    from app.services.passes import drop_attendance

    await drop_attendance(
        db, user_id=user_id, edition_id=edition.id, event_id=event_id
    )
    await record(
        db,
        request,
        actor_id=user_id,
        action="registration.cancelled",
        resource_type="registration",
        resource_id=str(reg.id),
        after={"reason": "worklist removal", "settlement": "refund"},
    )
    await db.flush()
    cache_delete_pattern("public:*")
    cache_delete_pattern("admin:dashboard:*")
    return result


# --------------------------------------------------------------------------- #
# Worklist payload
# --------------------------------------------------------------------------- #
async def build_worklist(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    edition: ConventionEdition,
    policy: EditionPolicy,
) -> dict:
    """One payload for the one page: events, seats, teams, allowance, quote."""
    from app.models.edition import EventCategory

    events = list(
        (
            await db.execute(
                select(Event)
                .where(
                    Event.edition_id == edition.id,
                    Event.status.in_(("published", "open")),
                )
                .order_by(Event.starts_at, Event.sort_order)
            )
        ).scalars()
    )
    live = await _live_regs(db, user_id, edition.id)
    categories = {
        row.id: row
        for row in (
            await db.execute(
                select(EventCategory).where(EventCategory.edition_id == edition.id)
            )
        ).scalars()
    }
    teams = list(
        (
            await db.execute(
                select(Team).where(
                    Team.edition_id == edition.id,
                    Team.status.in_(("active", "forming", "locked")),
                    Team.id.in_(
                        select(TeamMember.team_id).where(TeamMember.user_id == user_id)
                    ),
                )
            )
        ).scalars()
    )
    team_by_event = {team.event_id: team for team in teams}
    member_counts: dict[uuid.UUID, int] = {}
    for team in teams:
        member_counts[team.id] = int(
            (
                await db.execute(
                    select(func.count(TeamMember.id)).where(
                        TeamMember.team_id == team.id
                    )
                )
            ).scalar()
            or 0
        )

    covered_ids = {
        row.event_id
        for row in live.values()
        if row.kind == INCLUDED and row.status == "confirmed"
    }
    frozen_count = len(covered_ids)
    frozen_value = 0
    for eid in covered_ids:
        covered_event = await db.get(Event, eid)
        if covered_event is not None:
            frozen_value += base_value(covered_event)

    rows = []
    for event in events:
        seat = live.get(event.id)
        team = team_by_event.get(event.id)
        price = list_price(event)
        basis = team_basis(event, policy) if event.format == "team" else ADDON
        if seat is not None:
            state = {
                "confirmed": "confirmed",
                "reserved": "addon_unpaid",
                "pending": "addon_unpaid",
            }.get(seat.status, "available")
            if seat.team_id is not None:
                state = "team_leader" if team and team.leader_id == user_id else "team_member"
            if seat.kind == FREE and seat.status == "confirmed":
                state = "confirmed"
            if seat.kind == INCLUDED and seat.status == "confirmed" and seat.team_id is not None:
                state = "team_included"
            due = (
                max(0, int(seat.fee_paise))
                if seat.status != "confirmed"
                else 0
            )
            row_price = {
                "listPaise": int(seat.fee_paise or price),
                "duePaise": due,
                "basis": seat.price_basis or seat.kind,
            }
        else:
            covered = False
            if event.id not in covered_ids and price > 0:
                trial = allowance_pack(
                    [event],
                    count=policy.included_event_count,
                    cap_paise=policy.included_value_cap_paise,
                    cap_inclusive=bool(policy.cap_inclusive),
                    frozen_count=frozen_count,
                    frozen_value=frozen_value,
                    pack_order=int(getattr(policy, "allowance_pack_order", 0) or 0),
                )
                covered = event.id in trial
            kind, price_basis, due = _kind_for(event, price, covered)
            state = (
                "free" if kind == FREE else "included_possible" if covered else "available"
            )
            row_price = {"listPaise": price, "duePaise": due, "basis": price_basis}

        team_payload = None
        if event.format == "team":
            if team is not None:
                team_payload = {
                    "id": str(team.id),
                    "name": team.name,
                    "status": team.status,
                    "isLeader": team.leader_id == user_id,
                    "memberCount": member_counts.get(team.id, 0),
                    "minSize": event.team_min_size,
                    "maxSize": event.team_max_size,
                    "inviteCode": team.invite_code if team.leader_id == user_id else None,
                    "inviteLink": (
                        f"/team/{team.invite_code}" if team.leader_id == user_id else None
                    ),
                }
                if state in ("available", "free", "included_possible"):
                    state = "team_member" if team.leader_id != user_id else "team_leader"
                elif state == "addon_unpaid":
                    state = "team_unpaid"
            else:
                team_payload = {
                    "id": None,
                    "status": "none",
                    "isLeader": False,
                    "memberCount": 0,
                    "minSize": event.team_min_size,
                    "maxSize": event.team_max_size,
                    "inviteCode": None,
                    "inviteLink": None,
                }
                if state == "confirmed":
                    state = "solo"
                elif state == "addon_unpaid":
                    state = "solo_unpaid"

        payment_payload = None
        if seat is not None and seat.order_id is not None and seat.status != "confirmed":
            order = await db.get(PaymentOrder, seat.order_id)
            if order is not None and order.status == "created":
                from app.core.config import get_settings

                settings = get_settings()
                payment_payload = {
                    "orderId": str(order.id),
                    "amountPaise": int(order.amount_paise),
                    "gatewayOrderId": order.gateway_order_id,
                    "razorpayKeyId": settings.razorpay_key_id,
                    "mock": settings.mock_payments_available,
                }
        if state == "team_unpaid" and team is not None and team.leader_id != user_id:
            # Only the leader can pay the team entry; a rider waits for them.
            actions = ["open_team"]
            payment_payload = None
        else:
            actions = _actions_for(event, state, team, seat)

        rows.append(
            {
                "eventId": str(event.id),
                "slug": event.slug,
                "title": event.title,
                "summary": event.summary,
                "format": event.format,
                "category": (
                    categories[event.category_id].name
                    if event.category_id in categories
                    else "General"
                ),
                "categorySlug": (
                    categories[event.category_id].slug
                    if event.category_id in categories
                    else None
                ),
                "startsAt": aware(event.starts_at).isoformat() if event.starts_at else None,
                "venue": event.venue_room,
                "capacity": event.capacity,
                "bannerUrl": event.banner_url,
                "iconId": str(event.icon_id) if event.icon_id else None,
                "price": row_price,
                "state": state,
                "seat": (
                    {
                        "id": str(seat.id),
                        "status": seat.status,
                        "kind": seat.kind,
                        "feePaise": int(seat.fee_paise),
                        "orderId": str(seat.order_id) if seat.order_id else None,
                        "reservationExpiresAt": (
                            aware(seat.reservation_expires_at).isoformat()
                            if seat.reservation_expires_at
                            else None
                        ),
                    }
                    if seat is not None
                    else None
                ),
                "team": team_payload,
                "payment": payment_payload,
                "actions": actions,
            }
        )

    seats_paid = sum(
        int(r.fee_paise)
        for r in live.values()
        if r.status == "confirmed" and r.kind == ADDON
    )
    cancelled_regs = list(
        (
            await db.execute(
                select(Registration, Event)
                .join(Event, Registration.event_id == Event.id)
                .where(
                    Registration.user_id == user_id,
                    Registration.edition_id == edition.id,
                    Registration.status == "cancelled",
                )
                .order_by(Registration.cancelled_at.desc())
                .limit(20)
            )
        ).all()
    )
    cancelled_events: list[dict] = []
    for c_reg, c_ev in cancelled_regs:
        refund_info = {"status": "none", "amountPaise": 0, "requestedAt": None, "processedAt": None}
        if c_reg.order_id is not None and int(c_reg.fee_paise or 0) > 0:
            rf = (
                await db.execute(
                    select(Refund)
                    .where(Refund.order_id == c_reg.order_id)
                    .order_by(Refund.created_at.desc())
                    .limit(1)
                )
            ).scalars().first()
            if rf is not None:
                refund_info = {
                    "status": rf.status,
                    "amountPaise": int(rf.amount_paise),
                    "requestedAt": aware(rf.created_at).isoformat() if rf.created_at else None,
                    "processedAt": aware(rf.processed_at).isoformat() if rf.processed_at else None,
                }
        cancelled_events.append(
            {
                "registrationId": str(c_reg.id),
                "eventId": str(c_ev.id),
                "title": c_ev.title,
                "feePaise": int(c_reg.fee_paise or 0),
                "cancelledAt": aware(c_reg.cancelled_at).isoformat() if c_reg.cancelled_at else None,
                "cancelledBy": c_reg.cancelled_by or "user",
                "cancellationReason": c_reg.cancellation_reason,
                "refund": refund_info,
            }
        )

    return {
        "edition": {
            "id": str(edition.id),
            "name": edition.name,
            "signupOpen": accepting_bookings(edition),
        },
        "allowance": {
            "count": len(covered_ids),
            "required": policy.included_event_count,
            "unlimited": int(policy.included_event_count) < 0,
            "mode": policy.included_selection_mode or "up_to",
            "packOrder": int(getattr(policy, "allowance_pack_order", 0) or 0),
            "capPaise": policy.included_value_cap_paise,
            "valuePaise": frozen_value,
            "remainingPaise": (
                max(0, int(policy.included_value_cap_paise) - frozen_value)
                if policy.included_value_cap_paise is not None
                else None
            ),
            "capInclusive": bool(policy.cap_inclusive),
            "platformFeeBps": int(getattr(policy, "platform_fee_bps", 0) or 0),
            "platformFeeExemptUnderPaise": int(
                getattr(policy, "platform_fee_exempt_under_paise", 0) or 0
            ),
            "locked": bool(
                policy.selection_change_deadline
                and aware(policy.selection_change_deadline) <= datetime.now(UTC)
            ),
        },
        "totals": {"paidSeatsPaise": seats_paid},
        "basket": basket_payload(await open_basket(db, user_id, edition.id)),
        "rows": rows,
        "cancelledEvents": cancelled_events,
    }


def _actions_for(
    event: Event, state: str, team: Team | None, seat: Registration | None
) -> list[str]:
    actions: list[str] = []
    if state in ("available", "free", "included_possible"):
        actions.append("add")
    elif state in ("addon_unpaid", "team_unpaid", "solo_unpaid"):
        actions.append("pay")
        actions.append("remove")
    elif state == "confirmed":
        actions.append("ticket")
        if seat is not None and seat.kind != FREE:
            actions.append("remove")
    elif state == "solo":
        actions.append("create_team")
        actions.append("join_team")
        actions.append("remove")
    elif state == "team_included":
        actions.append("open_team")
        actions.append("leave_team")
    elif state in ("team_leader", "team_member"):
        actions.append("open_team")
        actions.append("leave_team")
    return actions


async def release_unpaid_order(
    db: AsyncSession, *, user_id: uuid.UUID, order_id: uuid.UUID
) -> dict:
    """Release reserved seats immediately when checkout is closed or fails."""
    order = await db.get(PaymentOrder, order_id)
    if order is None or order.user_id != user_id:
        raise NotFound("Order not found.")
    if order.status == "paid":
        return {"released": 0, "orderStatus": "paid"}
    if order.status == "created":
        order.status = "expired"
    reserved = list(
        (
            await db.execute(
                select(Registration).where(
                    Registration.order_id == order.id,
                    Registration.user_id == user_id,
                    Registration.status == "reserved",
                )
            )
        ).scalars()
    )
    for seat in reserved:
        seat.status = "cancelled"
        seat.cancelled_at = datetime.now(UTC)
        seat.cancelled_by = "user"
        seat.cancellation_reason = "Payment cancelled or failed before completion"
    if reserved:
        cache_delete_pattern("public:*")
        cache_delete_pattern("admin:dashboard:*")
    await db.flush()
    return {"released": len(reserved), "orderStatus": order.status}


__all__ = [
    "ADDON",
    "FREE",
    "INCLUDED",
    "TEAM_PER_PARTICIPANT",
    "allowance_pack",
    "basket_add",
    "basket_payload",
    "basket_remove",
    "create_seat_now",
    "open_basket",
    "base_value",
    "build_quote",
    "build_worklist",
    "consume_quote",
    "list_price",
    "quotes_match_prices",
    "remove_seat",
    "team_basis",
]
