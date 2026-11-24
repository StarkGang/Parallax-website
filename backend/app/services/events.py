"""Event management, pricing history, scheduling and public catalogue projection."""

import uuid
from datetime import UTC, datetime, timezone, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import Request
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_delete_pattern
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.text import render_markdown
from app.models.commerce import (
    IncludedEventSelection,
    PaymentOrder,
    Refund,
    Registration,
    Team,
    TeamMember,
)
from app.models.edition import (
    ConventionEdition,
    Event,
    EventCategory,
    EventPriceHistory,
)
from app.schemas.public import EventDetail, EventListItem, ScheduleDay, ScheduleItem
from app.services.audit import record


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def seats_taken(db: AsyncSession, event_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not event_ids:
        return {}
    counts = dict.fromkeys(event_ids, 0)
    rows = list(
        (
            await db.execute(
                select(Registration.event_id, func.count(Registration.id))
                .where(
                    Registration.event_id.in_(event_ids),
                    Registration.status.in_(["confirmed", "reserved"]),
                )
                .group_by(Registration.event_id)
            )
        ).all()
    )
    for eid, count in rows:
        counts[eid] = count
    return counts


#: Statuses that make a team occupy a place in an event.
LIVE_TEAM_STATUSES = ("active", "forming", "locked")


async def capacity_usage(
    db: AsyncSession, events: list[Event]
) -> dict[uuid.UUID, int]:
    """How much of each event's capacity is used, in that event's own unit.

    ``capacity_unit`` is configurable as ``participants`` or ``entries`` (teams),
    but every capacity check counted registration rows, so a team event with a
    capacity of ten entries sold out after two or three teams and the "seats
    left" shown to attendees was wrong. This is the one place that knows the
    unit; callers compare its result with ``event.capacity``.
    """
    if not events:
        return {}
    people_ids = [e.id for e in events if (e.capacity_unit or "participants") != "entries"]
    entry_ids = [e.id for e in events if (e.capacity_unit or "participants") == "entries"]
    usage: dict[uuid.UUID, int] = {e.id: 0 for e in events}
    if people_ids:
        usage.update(await seats_taken(db, people_ids))
    if entry_ids:
        rows = list(
            (
                await db.execute(
                    select(Team.event_id, func.count(Team.id))
                    .where(
                        Team.event_id.in_(entry_ids),
                        Team.status.in_(LIVE_TEAM_STATUSES),
                    )
                    .group_by(Team.event_id)
                )
            ).all()
        )
        for eid, count in rows:
            usage[eid] = count
        # A solo entry has no Team row, so counting teams alone made solo
        # entrants invisible to an "entries" capacity and let a team event
        # oversell. Both live teams and live unteamed seats are one entry each.
        solo_rows = list(
            (
                await db.execute(
                    select(Registration.event_id, func.count(Registration.id))
                    .where(
                        Registration.event_id.in_(entry_ids),
                        Registration.status.in_(("confirmed", "reserved", "pending")),
                        Registration.team_id.is_(None),
                    )
                    .group_by(Registration.event_id)
                )
            ).all()
        )
        for eid, count in solo_rows:
            usage[eid] = usage.get(eid, 0) + count
    return usage


def seats_left_for(event: Event, used: int) -> int | None:
    if not event.capacity:
        return None
    return max(0, event.capacity - used)


def event_open(event: Event, now: datetime | None = None) -> bool:
    if event.status not in ("published", "open"):
        return False
    current = now or datetime.now(UTC)
    opens = _aware(event.registration_opens_at)
    closes = _aware(event.registration_closes_at)
    if opens and current < opens:
        return False
    if closes and current > closes:
        return False
    return True


async def serialize_events(
    db: AsyncSession, events: list[Event], categories_by_id: dict[uuid.UUID, EventCategory]
) -> list[EventListItem]:
    if not events:
        return []
    taken = await capacity_usage(db, events)
    now = datetime.now(UTC)
    items = []
    for e in events:
        cat = categories_by_id.get(e.category_id)
        seats = taken.get(e.id, 0)
        seats_left = seats_left_for(e, seats)
        items.append(
            EventListItem(
                id=e.id,
                slug=e.slug,
                title=e.title,
                summary=e.summary,
                category_id=e.category_id,
                category_name=cat.name if cat else "General",
                category_slug=cat.slug if cat else "general",
                format=e.format,
                team_min_size=e.team_min_size,
                team_max_size=e.team_max_size,
                starts_at=_aware(e.starts_at),
                ends_at=_aware(e.ends_at),
                venue_room=e.venue_room,
                icon_id=e.icon_id or (cat.icon_id if cat else None),
                banner_url=e.banner_url or (cat.banner_url if cat else None),
                accent=e.accent or (cat.accent if cat else None),
                base_value_paise=e.base_value_paise,
                included_eligible=e.included_eligible,
                addon_price_paise=e.addon_price_paise,
                addon_charge_basis=e.addon_charge_basis,
                capacity=e.capacity,
                seats_left=seats_left,
                status=e.status,
                is_featured=e.is_featured,
                registration_open=event_open(e, now),
                requires_approval=e.requires_approval,
            )
        )
    return items


async def list_public_events(
    db: AsyncSession,
    edition: ConventionEdition,
    category: str | None = None,
    format: str | None = None,
    q: str | None = None,
    featured: bool | None = None,
    sort: str | None = None,
    page: int = 1,
    page_size: int = 24,
) -> tuple[list[EventListItem], int]:
    stmt = select(Event).where(
        Event.edition_id == edition.id,
        Event.status.in_(["published", "open"]),
    )
    if category:
        cat = (
            await db.execute(
                select(EventCategory).where(
                    EventCategory.edition_id == edition.id,
                    EventCategory.slug == category.strip().lower(),
                )
            )
        ).scalar_one_or_none()
        if cat:
            stmt = stmt.where(Event.category_id == cat.id)
        else:
            return [], 0

    if format:
        stmt = stmt.where(Event.format == format)
    if featured is not None:
        stmt = stmt.where(Event.is_featured.is_(featured))
    if q:
        needle = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Event.title).like(needle),
                func.lower(Event.summary).like(needle),
            )
        )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    # "date" gives a programme-chronological catalogue; the default keeps the
    # organiser-defined running order.
    if sort == "date":
        ordering = (Event.starts_at, Event.sort_order, Event.title)
    else:
        ordering = (Event.sort_order, Event.starts_at)

    events = list(
        (
            await db.execute(
                stmt.order_by(*ordering)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars()
    )

    cat_rows = list(
        (
            await db.execute(
                select(EventCategory).where(EventCategory.edition_id == edition.id)
            )
        ).scalars()
    )
    cats_by_id = {c.id: c for c in cat_rows}

    items = await serialize_events(db, events, cats_by_id)
    return items, total


async def public_event(
    db: AsyncSession, edition: ConventionEdition, slug: str
) -> EventDetail:
    row = (
        await db.execute(
            select(Event).where(
                Event.edition_id == edition.id,
                Event.slug == slug.strip().lower(),
                Event.status.in_(["published", "open"]),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFound(f"Event '{slug}' not found.")

    cat = await db.get(EventCategory, row.category_id)
    cats_by_id = {cat.id: cat} if cat else {}
    base_item = (await serialize_events(db, [row], cats_by_id))[0]

    return EventDetail(
        **base_item.model_dump(),
        description_html=render_markdown(row.description_md) if row.description_md else None,
        rules_html=render_markdown(row.rules_md) if row.rules_md else None,
        prizes_html=render_markdown(row.prizes_md) if row.prizes_md else None,
        solo_guide_html=(
            render_markdown(row.solo_guide_md) if getattr(row, "solo_guide_md", "") else None
        ),
        team_guide_html=(
            render_markdown(row.team_guide_md) if getattr(row, "team_guide_md", "") else None
        ),
        registration_opens_at=_aware(row.registration_opens_at),
        registration_closes_at=_aware(row.registration_closes_at),
        team_fee_basis=row.team_fee_basis,
    )


async def schedule(db: AsyncSession, edition: ConventionEdition) -> list[ScheduleDay]:
    events = list(
        (
            await db.execute(
                select(Event)
                .where(
                    Event.edition_id == edition.id,
                    Event.status.in_(["published", "open"]),
                )
                .order_by(Event.starts_at, Event.sort_order)
            )
        ).scalars()
    )

    cats = {
        c.id: c
        for c in (
            await db.execute(
                select(EventCategory).where(EventCategory.edition_id == edition.id)
            )
        ).scalars()
    }

    days_map: dict[str, list[ScheduleItem]] = {}
    try:
        tz = ZoneInfo(getattr(edition, "timezone", None) or "Asia/Kolkata")
    except Exception:
        tz = timezone(timedelta(hours=5, minutes=30))

    for e in events:
        starts = _aware(e.starts_at).astimezone(tz)
        ends = _aware(e.ends_at).astimezone(tz)
        day_key = starts.date().isoformat()
        cat = cats.get(e.category_id)
        item = ScheduleItem(
            id=e.id,
            title=e.title,
            slug=e.slug,
            room=e.venue_room,
            starts_at=starts,
            ends_at=ends,
            accent=e.accent or (cat.accent if cat else None),
            icon_id=e.icon_id or (cat.icon_id if cat else None),
            category=cat.name if cat else None,
        )
        days_map.setdefault(day_key, []).append(item)

    days = []
    for d_str in sorted(days_map.keys()):
        d_date = datetime.fromisoformat(d_str).date()
        label = d_date.strftime("%A, %B %d")
        days.append(ScheduleDay(date=d_date, label=label, items=days_map[d_str]))
    return days


async def admin_list_events(
    db: AsyncSession, edition_id: uuid.UUID, status: str | None = None, q: str | None = None
) -> list[dict[str, Any]]:
    stmt = select(Event).where(Event.edition_id == edition_id)
    if status:
        stmt = stmt.where(Event.status == status)
    if q:
        needle = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Event.title).like(needle),
                func.lower(Event.slug).like(needle),
            )
        )
    events = list((await db.execute(stmt.order_by(Event.sort_order, Event.starts_at))).scalars())
    cats = {
        c.id: c
        for c in (
            await db.execute(
                select(EventCategory).where(EventCategory.edition_id == edition_id)
            )
        ).scalars()
    }
    return [
        {
            "id": str(e.id),
            "slug": e.slug,
            "title": e.title,
            "summary": e.summary,
            "categoryId": str(e.category_id),
            "categoryName": cats[e.category_id].name if e.category_id in cats else "General",
            "format": e.format,
            "teamMinSize": e.team_min_size,
            "teamMaxSize": e.team_max_size,
            "baseValuePaise": e.base_value_paise,
            "addonPricePaise": e.addon_price_paise,
            "capacity": e.capacity,
            "status": e.status,
            "isFeatured": e.is_featured,
            "startsAt": _aware(e.starts_at).isoformat() if e.starts_at else None,
            "endsAt": _aware(e.ends_at).isoformat() if e.ends_at else None,
            "venueRoom": e.venue_room,
            "bannerUrl": e.banner_url,
            "capacityUnit": e.capacity_unit,
            "createdAt": _aware(e.created_at).isoformat() if e.created_at else None,
        }
        for e in events
    ]


def publish_problems(event: Event) -> list[str]:
    problems = []
    if not event.title:
        problems.append("Title is required.")
    if not event.summary:
        problems.append("Summary is required.")
    starts = _aware(event.starts_at)
    ends = _aware(event.ends_at)
    if not starts or not ends:
        problems.append("Start and end times are required.")
    elif ends <= starts:
        problems.append("End time must be after start time.")
    opens = _aware(event.registration_opens_at)
    closes = _aware(event.registration_closes_at)
    if opens and closes and closes <= opens:
        problems.append("Registration must close after it opens.")
    if event.format == "team" and (
        event.team_min_size < 1 or event.team_max_size < event.team_min_size
    ):
        problems.append("Team size range is invalid.")
    if event.capacity < 0:
        problems.append("Capacity cannot be negative.")
    return problems


async def _validate_event(
    db: AsyncSession, edition_id: uuid.UUID, event: Event, payload: dict[str, Any]
) -> None:
    """Reject event states the participant workflow cannot honour."""
    category = await db.get(EventCategory, event.category_id)
    if category is None or category.edition_id != edition_id:
        raise ValidationFailed("Choose a category that belongs to this edition.")

    starts = _aware(event.starts_at)
    ends = _aware(event.ends_at)
    if starts and ends and ends <= starts:
        raise ValidationFailed("The event must end after it starts.")

    opens = _aware(event.registration_opens_at)
    closes = _aware(event.registration_closes_at)
    if opens and closes and closes <= opens:
        raise ValidationFailed("Event registration must close after it opens.")
    if opens and ends and opens >= ends:
        raise ValidationFailed("Event registration must open before the event ends.")

    if event.team_min_size < 1 or event.team_max_size < event.team_min_size:
        raise ValidationFailed(
            "Team size must start at 1 and the maximum cannot be below the minimum."
        )
    if event.capacity < 0:
        raise ValidationFailed("Capacity cannot be negative.")
    if (event.base_value_paise or 0) < 0 or (event.addon_price_paise or 0) < 0:
        raise ValidationFailed("Event prices cannot be negative.")

    if event.id is not None and event.capacity:
        stored = await db.get(Event, event.id)
        taken = (await capacity_usage(db, [stored or event])).get(event.id, 0)
        if event.capacity < taken:
            raise Conflict(
                f"Capacity cannot be lower than the {taken} seats already booked for this event."
            )

    if event.status in ("published", "open"):
        problems = publish_problems(event)
        if problems:
            raise ValidationFailed(" ".join(problems))

    # Closing an event must not silently strand attendees who already hold
    # confirmed registrations and tickets for it: seats, tickets and money are
    # released by the close_event cascade that upsert_event runs once the new
    # status has been stored.


async def close_event(
    db: AsyncSession,
    request: Request | None,
    event: Event,
    *,
    reason: str,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
) -> dict[str, Any]:
    """Cancel every live booking on an event that is no longer running.

    Closing/cancelling an event used to change only ``Event.status``: attendees
    kept confirmed seats, working QR codes and their money. This is the single
    cascade for that transition - it cancels the seats, revokes the tickets and
    queues one refund request per paid order, which the finance desk settles from
    the payments screen. Attendees are kept informed in the portal, and the
    cancelled event stays visible to them with a cancelled badge.
    """
    from app.services.tickets import revoke_for_registration

    with_reason = f"Event closed: {(reason or event.title)[:200]}"
    regs = list(
        (
            await db.execute(
                select(Registration).where(
                    Registration.event_id == event.id,
                    Registration.status.in_(["confirmed", "reserved"]),
                )
            )
        ).scalars()
    )

    order_ids: list[uuid.UUID] = []
    for reg in regs:
        reg.status = "cancelled"
        reg.cancelled_at = datetime.now(UTC)
        reg.cancelled_by = "admin"
        reg.cancellation_reason = with_reason
        # A shared ``per_team`` order can ride on a seat whose own fee is 0 (a
        # member covered by the leader's payment), so the order is collected by
        # id and the paid/unpaid check happens below.
        if reg.order_id is not None:
            order_ids.append(reg.order_id)
        await revoke_for_registration(db, reg.id)

    # A team whose event is gone must not stay open for invitations and roster
    # edits (including locked teams). Its shared ``per_team`` order is collected
    # here because the seat that originally carried it may already be gone
    # (the payer's pass lapsed and the team carried on under a new leader).
    event_teams = list(
        (
            await db.execute(
                select(Team).where(
                    Team.event_id == event.id,
                    Team.status != "disbanded",
                )
            )
        ).scalars()
    )
    for team in event_teams:
        if team.order_id is not None:
            order_ids.append(team.order_id)
        team.status = "disbanded"
        team.formation_state = "disbanded"
        await db.execute(delete(TeamMember).where(TeamMember.team_id == team.id))

    refunds_queued = 0
    for order_id in dict.fromkeys(order_ids):
        order = await db.get(PaymentOrder, order_id)
        if order is None or order.status != "paid":
            continue
        already = (
            (
                await db.execute(
                    select(func.coalesce(func.sum(Refund.amount_paise), 0)).where(
                        Refund.order_id == order.id,
                        Refund.status == "processed",
                    )
                )
            )
            .scalars()
            .one()
        ) or 0
        remaining = int(order.amount_paise) - int(already)
        if remaining <= 0:
            continue
        existing = (
            await db.execute(
                select(Refund).where(
                    Refund.order_id == order.id, Refund.status == "pending"
                )
            )
        ).scalars().first()
        if existing is None:
            db.add(
                Refund(
                    order_id=order.id,
                    amount_paise=remaining,
                    reason_code="event_cancelled",
                    reason_note=with_reason,
                    status="pending",
                    requested_by=actor_id,
                )
            )
            refunds_queued += 1

    await _notify_closed_event(db, event, regs, reason=with_reason)

    # Give the included-seat slot back. A cancelled event that stayed selected
    # kept consuming the attendee's free-selection quota.
    await db.execute(
        delete(IncludedEventSelection).where(IncludedEventSelection.event_id == event.id)
    )

    if request is not None:
        await record(
            db,
            request,
            actor_id=actor_id,
            actor_role=actor_role,
            action="event.closed_cascade",
            resource_type="event",
            resource_id=str(event.id),
            after={
                "status": event.status,
                "cancelledRegistrations": len(regs),
                "refundRequestsQueued": refunds_queued,
                "reason": reason,
            },
        )
    return {
        "cancelledRegistrations": len(regs),
        "refundRequestsQueued": refunds_queued,
    }


async def _notify_closed_event(
    db: AsyncSession, event: Event, regs: list[Registration], *, reason: str
) -> None:
    """Tell each affected attendee in the portal that their seat was cancelled."""
    from app.models.registration import CollegeRegistration
    from app.services.college_registrations import notify

    for user_id in dict.fromkeys(r.user_id for r in regs):
        row = (
            await db.execute(
                select(CollegeRegistration).where(
                    CollegeRegistration.user_id == user_id,
                    CollegeRegistration.edition_id == event.edition_id,
                )
            )
        ).scalars().first()
        if row is None:
            continue
        await notify(
            db,
            row,
            "event_cancelled",
            title=f"{event.title} was cancelled",
            values={
                "event": event.title,
                "reason": reason,
                "refund": "Any amount you paid is refunded to the payment method used.",
            },
        )


async def upsert_event(
    db: AsyncSession,
    request: Request,
    edition_id: uuid.UUID,
    payload: dict[str, Any],
    event_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
) -> Event:
    event = None
    if event_id:
        event = await db.get(Event, event_id)
        if event is None or event.edition_id != edition_id:
            raise NotFound("Event not found.")
        new_slug = payload.get("slug", "").strip().lower()
        if new_slug and new_slug != event.slug:
            existing = (
                await db.execute(
                    select(Event).where(
                        Event.edition_id == edition_id,
                        Event.slug == new_slug,
                        Event.id != event.id,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                raise Conflict("An event with that slug already exists.")
            event.slug = new_slug
    else:
        # Check slug uniqueness
        existing = (
            await db.execute(
                select(Event).where(
                    Event.edition_id == edition_id,
                    Event.slug == payload["slug"].strip().lower(),
                )
            )
        ).scalar_one_or_none()
        if existing:
            raise Conflict("An event with that slug already exists.")
        event = Event(edition_id=edition_id, slug=payload["slug"].strip().lower())
        db.add(event)

    old_base_value = event.base_value_paise
    old_addon_price = event.addon_price_paise

    for field in [
        "category_id",
        "title",
        "summary",
        "description_md",
        "rules_md",
        "prizes_md",
        "solo_guide_md",
        "team_guide_md",
        "format",
        "team_min_size",
        "team_max_size",
        "base_value_paise",
        "included_eligible",
        "addon_price_paise",
        "addon_charge_basis",
        "team_fee_basis",
        "capacity",
        "capacity_unit",
        "starts_at",
        "ends_at",
        "venue_room",
        "registration_opens_at",
        "registration_closes_at",
        "requires_approval",
        "icon_id",
        "banner_url",
        "accent",
        "is_featured",
        "sort_order",
        "status",
    ]:
        if field in payload:
            val = payload[field]
            if field == "venue_room" and val is None:
                val = ""
            elif field == "team_fee_basis" and not val:
                val = "per_participant"
            setattr(event, field, val)

    event.description_html = render_markdown(event.description_md or "")
    event.rules_html = render_markdown(event.rules_md or "")
    event.prizes_html = render_markdown(event.prizes_md or "")

    # These columns are NOT NULL, so an omitted window must be filled, not left empty.
    now = datetime.now(UTC)
    if event.registration_opens_at is None:
        event.registration_opens_at = now
    if event.registration_closes_at is None:
        starts = _aware(event.starts_at)
        event.registration_closes_at = (
            starts if starts and starts > now else now + timedelta(hours=24)
        )

    await _validate_event(db, edition_id, event, payload)

    if event_id and event.status not in ("published", "open"):
        await close_event(
            db,
            request,
            event,
            reason=payload.get("change_reason") or f"Event {event.status} by the organisers",
            actor_id=actor_id,
            actor_role=actor_role,
        )

    if event_id and (
        old_base_value != event.base_value_paise
        or old_addon_price != event.addon_price_paise
    ):
        db.add(
            EventPriceHistory(
                event_id=event.id,
                old_base_value_paise=old_base_value or 0,
                new_base_value_paise=event.base_value_paise or 0,
                old_addon_price_paise=old_addon_price or 0,
                new_addon_price_paise=event.addon_price_paise or 0,
                changed_by=actor_id,
                reason=payload.get("change_reason"),
            )
        )

    await record(
        db,
        request,
        actor_id=actor_id,
        actor_role=actor_role,
        action="event.upserted",
        resource_type="event",
        resource_id=str(event.id),
        after={"slug": event.slug, "title": event.title, "status": event.status},
    )
    await db.flush()
    cache_delete_pattern('public:*')
    cache_delete_pattern('admin:dashboard:*')
    return event


async def event_admin_payload(db: AsyncSession, event: Event) -> dict[str, Any]:
    cat = await db.get(EventCategory, event.category_id)
    history = await price_history(db, event.id)
    return {
        "id": str(event.id),
        "slug": event.slug,
        "title": event.title,
        "summary": event.summary,
        "descriptionMd": event.description_md,
        "rulesMd": event.rules_md,
        "prizesMd": event.prizes_md,
        "soloGuideMd": event.solo_guide_md,
        "teamGuideMd": event.team_guide_md,
        "categoryId": str(event.category_id),
        "categoryName": cat.name if cat else "General",
        "format": event.format,
        "teamMinSize": event.team_min_size,
        "teamMaxSize": event.team_max_size,
        "baseValuePaise": event.base_value_paise,
        "includedEligible": event.included_eligible,
        "addonPricePaise": event.addon_price_paise,
        "addonChargeBasis": event.addon_charge_basis,
        "teamFeeBasis": event.team_fee_basis,
        "capacity": event.capacity,
        "capacityUnit": event.capacity_unit,
        "status": event.status,
        "isFeatured": event.is_featured,
        "sortOrder": event.sort_order,
        "startsAt": _aware(event.starts_at).isoformat() if event.starts_at else None,
        "endsAt": _aware(event.ends_at).isoformat() if event.ends_at else None,
        "venueRoom": event.venue_room,
        "registrationOpensAt": _aware(event.registration_opens_at).isoformat() if event.registration_opens_at else None,
        "registrationClosesAt": _aware(event.registration_closes_at).isoformat() if event.registration_closes_at else None,
        "requiresApproval": event.requires_approval,
        "iconId": str(event.icon_id) if event.icon_id else None,
        "bannerUrl": event.banner_url,
        "accent": event.accent,
        "priceHistory": history,
        "createdAt": _aware(event.created_at).isoformat() if event.created_at else None,
    }


async def price_history(db: AsyncSession, event_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = list(
        (
            await db.execute(
                select(EventPriceHistory)
                .where(EventPriceHistory.event_id == event_id)
                .order_by(EventPriceHistory.created_at.desc())
            )
        ).scalars()
    )
    return [
        {
            "changedAt": _aware(h.created_at).isoformat() if h.created_at else None,
            "oldBaseValuePaise": h.old_base_value_paise,
            "newBaseValuePaise": h.new_base_value_paise,
            "oldAddonPricePaise": h.old_addon_price_paise,
            "newAddonPricePaise": h.new_addon_price_paise,
            "reason": h.reason,
        }
        for h in rows
    ]


async def event_by_id(db: AsyncSession, event_id: uuid.UUID) -> Event:
    row = await db.get(Event, event_id)
    if row is None:
        raise NotFound("Event not found.")
    return row


__all__ = [
    "_aware",
    "seats_taken",
    "event_open",
    "serialize_events",
    "list_public_events",
    "public_event",
    "schedule",
    "admin_list_events",
    "publish_problems",
    "upsert_event",
    "event_admin_payload",
    "price_history",
    "event_by_id",
]

