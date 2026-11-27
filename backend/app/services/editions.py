"""Edition lifecycle, active policy enforcement and admin dashboard rollup."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_delete_pattern, cache_get, cache_set
from app.core.errors import NotFound, ValidationFailed
from app.models.commerce import (
    AttendanceRecord,
    ConventionPass,
    PaymentOrder,
    Refund,
    Registration,
)
from app.models.edition import (
    ConventionEdition,
    EditionPolicy,
    Event,
    EventCategory,
)
from app.models.registration import CollegeRegistration
from app.models.user import User
from app.schemas.admin import DashboardStats, PolicyCheck
from app.schemas.public import EditionPublic, PolicyPublic
from app.services.audit import record


def aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def current_edition(db: AsyncSession) -> ConventionEdition:
    """Resolve the edition the site and console operate on.

    An active (published/open) edition always wins. If every edition is a
    draft or archived, the most recently updated one is returned instead of a
    dead-end 404: staff must still be able to open the console and publish it.
    """
    row = (
        await db.execute(
            select(ConventionEdition)
            .where(ConventionEdition.status.in_(["published", "open"]))
            # Total ordering: two editions can share a start date, and an
            # ambiguous order made the site and console resolve different rows
            # on different requests. created_at/id break the tie deterministically.
            .order_by(
                ConventionEdition.starts_at.desc(),
                ConventionEdition.created_at.desc(),
                ConventionEdition.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is not None:
        return row

    latest = (
        await db.execute(
            select(ConventionEdition)
            .order_by(
                ConventionEdition.updated_at.desc(),
                ConventionEdition.created_at.desc(),
                ConventionEdition.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest is None:
        raise NotFound("No convention edition has been created yet.")
    return latest


async def edition_by_slug(db: AsyncSession, slug: str) -> ConventionEdition:
    row = (
        await db.execute(
            select(ConventionEdition).where(ConventionEdition.slug == slug.strip().lower())
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFound(f"Convention edition '{slug}' not found.")
    return row


async def edition_by_id(db: AsyncSession, edition_id: uuid.UUID) -> ConventionEdition:
    """Resolve an edition strictly by id.

    This used to fall back to "whatever edition is current", which silently
    pointed reads *and writes* at another convention whenever a stale or
    invented id reached the API. An unknown id is a client problem (or a row
    that was deleted) and must surface as a 404 the caller can recover from.
    """
    row = await db.get(ConventionEdition, edition_id)
    if row is None:
        raise NotFound("Convention edition not found. Reload the page to refresh it.")
    return row


async def current_policy(db: AsyncSession, edition_id: uuid.UUID) -> EditionPolicy:
    row = (
        await db.execute(
            select(EditionPolicy).where(
                EditionPolicy.edition_id == edition_id,
                EditionPolicy.is_current.is_(True),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFound("No active policy found for this edition.")
    return row


def policy_public(policy: EditionPolicy) -> PolicyPublic:
    return PolicyPublic(
        pass_price_paise=policy.pass_price_paise,
        lunch_included_days=getattr(policy, "lunch_included_days", None) or [],
        included_event_count=policy.included_event_count,
        included_selection_mode=getattr(policy, "included_selection_mode", "exact"),
        included_value_cap_paise=getattr(policy, "included_value_cap_paise", None),
        cap_inclusive=getattr(policy, "cap_inclusive", True),
        addon_requires_pass=getattr(policy, "addon_requires_pass", True),
        team_members_require_pass=getattr(policy, "team_members_require_pass", True),
        team_fee_basis_default=getattr(policy, "team_fee_basis_default", "per_participant"),
        hold_minutes=policy.hold_minutes,
        selection_change_deadline=aware(policy.selection_change_deadline),
        policy_version=policy.version,
        gst_note=policy.gst_note,
        platform_fee_bps=int(getattr(policy, "platform_fee_bps", 0) or 0),
        platform_fee_exempt_under_paise=int(
            getattr(policy, "platform_fee_exempt_under_paise", 0) or 0
        ),
    )


def registration_open(edition: ConventionEdition) -> bool:
    if edition.status not in ("published", "open"):
        return False
    now = datetime.now(UTC)
    opens = aware(edition.registration_opens_at)
    closes = aware(edition.registration_closes_at)
    if opens and now < opens:
        return False
    if closes and now > closes:
        return False
    return True


#: Edition states that mean "no new bookings", in order of severity.
CLOSED_EDITION_STATUSES = ("closed", "archived", "cancelled")


def accepting_bookings(edition: ConventionEdition) -> bool:
    """Whether new seats, teams or selections may be created on this edition.

    Only the registration window used to look at the edition, so archiving or
    closing a convention left add-on bookings and team invitations open.
    """
    return edition.status not in CLOSED_EDITION_STATUSES and registration_open(edition)


async def cancel_edition(
    db: AsyncSession,
    request: Request | None,
    edition: ConventionEdition,
    *,
    reason: str,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
) -> dict[str, Any]:
    """Cancel a whole convention: no live seat, ticket or payment is left behind.

    The event-level cascade already existed; the edition had none, so setting an
    edition to "cancelled" changed a label and nothing else. Every event is
    closed through the same cascade (seats cancelled, tickets revoked, one
    pending refund per paid event order), passes are cancelled, their seats and
    team memberships released, and one pending refund is queued per paid
    registration order. Refunds stay pending on purpose: cancelling an edition
    can affect hundreds of orders and the finance desk settles them.
    """
    from app.services.events import close_event
    from app.services.passes import release_event_entitlements
    from app.services.tickets import revoke_for_pass

    events = list(
        (
            await db.execute(
                select(Event).where(
                    Event.edition_id == edition.id,
                    Event.status.not_in(["cancelled", "closed"]),
                )
            )
        ).scalars()
    )
    for event in events:
        event.status = "cancelled"
        await close_event(
            db,
            request,
            event,
            reason=f"Edition cancelled: {reason}",
            actor_id=actor_id,
            actor_role=actor_role,
        )
    await db.flush()

    passes = list(
        (
            await db.execute(
                select(ConventionPass).where(
                    ConventionPass.edition_id == edition.id,
                    ConventionPass.status != "refunded",
                )
            )
        ).scalars()
    )
    for user_pass in passes:
        user_pass.status = "cancelled"
        await revoke_for_pass(db, user_pass.id)
        # Seats and add-on money were already handled per event above.
        await release_event_entitlements(
            db,
            user_id=user_pass.user_id,
            edition_id=edition.id,
            reason=f"Edition cancelled: {reason}",
            refund_paid_events=False,
            actor_id=actor_id,
        )

    # One refund request per paid registration order, capped by what is left.
    from app.models.registration import CollegeRegistration

    registrations = list(
        (
            await db.execute(
                select(CollegeRegistration).where(
                    CollegeRegistration.edition_id == edition.id,
                    CollegeRegistration.payment_status == "paid",
                )
            )
        ).scalars()
    )
    queued = 0
    for row in registrations:
        if row.order_id is None:
            continue
        order = await db.get(PaymentOrder, row.order_id)
        if order is None or order.status != "paid":
            continue
        already_committed = (
            (
                await db.execute(
                    select(func.coalesce(func.sum(Refund.amount_paise), 0)).where(
                        Refund.order_id == order.id,
                        Refund.status.in_(["pending", "processing", "processed"]),
                    )
                )
            )
            .scalars()
            .one()
        ) or 0
        remaining = int(order.amount_paise) - int(already_committed)
        if remaining <= 0:
            continue
        db.add(
            Refund(
                order_id=order.id,
                amount_paise=remaining,
                reason_code="edition_cancelled",
                reason_note=f"Edition cancelled: {reason}"[:500],
                status="pending",
                requested_by=actor_id,
            )
        )
        row.refund_status = "initiated"
        queued += 1

    # Nothing unpaid may stay payable into a cancelled convention.
    open_orders = list(
        (
            await db.execute(
                select(PaymentOrder).where(
                    PaymentOrder.edition_id == edition.id,
                    PaymentOrder.status == "created",
                )
            )
        ).scalars()
    )
    for order in open_orders:
        order.status = "expired"

    await db.flush()
    if request is not None:
        await record(
            db,
            request,
            actor_id=actor_id,
            actor_role=actor_role,
            action="edition.cancelled_cascade",
            resource_type="convention_edition",
            resource_id=str(edition.id),
            after={
                "reason": reason,
                "eventsClosed": len(events),
                "passesCancelled": len(passes),
                "refundRequestsQueued": queued,
                "ordersExpired": len(open_orders),
            },
        )
    cache_delete_pattern("public:*")
    cache_delete_pattern("admin:dashboard:*")
    return {
        "eventsClosed": len(events),
        "passesCancelled": len(passes),
        "refundRequestsQueued": queued,
        "ordersExpired": len(open_orders),
    }


def serialize_edition(
    edition: ConventionEdition,
    policy: EditionPolicy | None = None,
    *,
    helpdesk_phone: str | None = None,
) -> EditionPublic:
    return EditionPublic(
        id=edition.id,
        slug=edition.slug,
        name=edition.name,
        tagline=getattr(edition, "hero_subtitle", None) or getattr(edition, "hero_headline", None),
        organizer=edition.organizer,
        host=edition.host,
        venue=edition.venue,
        city=edition.city,
        timezone="Asia/Kolkata",
        starts_at=aware(edition.starts_at),
        ends_at=aware(edition.ends_at),
        registration_opens_at=aware(edition.registration_opens_at),
        registration_closes_at=aware(edition.registration_closes_at),
        status=edition.status,
        contact_email=edition.contact_email,
        helpdesk_phone=helpdesk_phone,
        branding={"theme": edition.theme} if getattr(edition, "theme", None) else {},
        logo_icon_id=edition.logo_icon_id,
        policy=policy_public(policy) if policy else None,
        registration_open=registration_open(edition),
    )


async def check_policy(
    db: AsyncSession, edition_id: uuid.UUID, payload: dict[str, Any]
) -> PolicyCheck:
    blocking: list[str] = []
    warnings: list[str] = []
    current = None
    try:
        current = await current_policy(db, edition_id)
    except NotFound:
        pass

    paid_passes = (
        (
            await db.execute(
                select(func.count(ConventionPass.id)).where(
                    ConventionPass.edition_id == edition_id,
                    ConventionPass.status == "active",
                )
            )
        ).scalar()
        or 0
    )

    next_price = payload.get("pass_price_paise")
    if current and next_price is not None and current.pass_price_paise != next_price:
        if paid_passes > 0 and not payload.get("override_price_lock"):
            blocking.append(
                "Cannot change the pass price after active passes exist without an override."
            )

    if next_price is not None and next_price < 0:
        blocking.append("The pass price cannot be negative.")

    count = payload.get("included_event_count")
    if count is not None and count < -1:
        blocking.append("The included event count must be -1 (unlimited) or at least 0.")
    cap = payload.get("included_value_cap_paise")
    if cap is not None and cap < 0:
        blocking.append("The included value cap cannot be negative.")
    if (payload.get("hold_minutes") or 0) < 1:
        blocking.append("Payment hold time must be at least one minute.")

    eligible = list(
        (
            await db.execute(
                select(Event.base_value_paise).where(
                    Event.edition_id == edition_id,
                    Event.included_eligible.is_(True),
                    Event.status.in_(["published", "open"]),
                )
            )
        ).scalars()
    )
    if count is not None and count >= 0 and eligible and count > len(eligible):
        blocking.append(
            f"Only {len(eligible)} included-eligible events exist, so {count} cannot be selected."
        )
    if cap is not None and eligible:
        cheapest = min(eligible)
        if cheapest > cap:
            warnings.append(
                "The value cap is below the cheapest eligible event, so no included selection can be saved."
            )

    deadline = aware(payload.get("selection_change_deadline"))
    if deadline is not None and deadline <= datetime.now(UTC):
        warnings.append(
            "The selection change deadline is in the past, so participants cannot change included events."
        )

    return PolicyCheck(
        ok=len(blocking) == 0,
        blocking=blocking,
        warnings=warnings,
        impact={"activePasses": paid_passes, "eligibleEvents": len(eligible)},
    )


async def apply_policy(
    db: AsyncSession,
    request: Request,
    edition_id: uuid.UUID,
    payload: dict[str, Any],
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
) -> EditionPolicy:
    check = await check_policy(db, edition_id, payload)
    if not check.ok:
        raise ValidationFailed("; ".join(check.blocking))

    current = None
    try:
        current = await current_policy(db, edition_id)
        current.is_current = False
    except NotFound:
        pass

    next_version = (current.version + 1) if current else 1

    new_p = EditionPolicy(
        edition_id=edition_id,
        version=next_version,
        is_current=True,
        pass_price_paise=payload["pass_price_paise"],
        included_event_count=payload.get("included_event_count", 0),
        lunch_included_days=payload.get("lunch_included_days", []),
        included_selection_mode=payload.get("included_selection_mode", "exact"),
        included_value_cap_paise=payload.get("included_value_cap_paise"),
        cap_inclusive=payload.get("cap_inclusive", True),
        allowance_pack_order=int(payload.get("allowance_pack_order", 0) or 0),
        addon_requires_pass=payload.get("addon_requires_pass", True),
        team_members_require_pass=payload.get("team_members_require_pass", True),
        selection_change_deadline=payload.get("selection_change_deadline"),
        team_fee_basis_default=payload.get("team_fee_basis_default", "per_participant"),
        hold_minutes=payload.get("hold_minutes", 15),
        refund_rules=payload.get("refund_rules", {}),
        gst_note=payload.get("gst_note"),
        platform_fee_bps=int(payload.get("platform_fee_bps", 0) or 0),
        platform_fee_exempt_under_paise=int(
            payload.get("platform_fee_exempt_under_paise", 0) or 0
        ),
        reason=payload.get("reason"),
    )
    db.add(new_p)
    await record(
        db,
        request,
        actor_id=actor_id,
        actor_role=actor_role,
        action="policy.created",
        resource_type="edition_policy",
        resource_id=str(new_p.id),
        after={"version": next_version, "pass_price_paise": new_p.pass_price_paise},
    )
    await db.flush()
    cache_delete_pattern("public:*")
    cache_delete_pattern("admin:dashboard:*")
    return new_p


async def dashboard(db: AsyncSession, edition_id: uuid.UUID) -> DashboardStats:
    cache_key = f"admin:dashboard:{edition_id}"
    cached_val = cache_get(cache_key)
    if cached_val is not None:
        return cached_val

    edition = await edition_by_id(db, edition_id)

    passes_sold = (
        await db.execute(
            select(func.count(ConventionPass.id)).where(
                ConventionPass.edition_id == edition_id,
                ConventionPass.status == "active",
            )
        )
    ).scalar() or 0

    revenue = (
        await db.execute(
            select(func.sum(PaymentOrder.amount_paise)).where(
                PaymentOrder.edition_id == edition_id,
                PaymentOrder.status.in_(["paid", "refunded"]),
            )
        )
    ).scalar() or 0

    refunded = (
        await db.execute(
            select(func.sum(Refund.amount_paise)).join(PaymentOrder, PaymentOrder.id == Refund.order_id).where(
                PaymentOrder.edition_id == edition_id,
                Refund.status == "processed",
            )
        )
    ).scalar() or 0

    pending_refunds_row = (
        await db.execute(
            select(
                func.coalesce(func.sum(Refund.amount_paise), 0),
                func.count(Refund.id),
            )
            .join(PaymentOrder, PaymentOrder.id == Refund.order_id)
            .where(
                PaymentOrder.edition_id == edition_id,
                Refund.status.in_(["pending", "processing"]),
            )
        )
    ).first()
    pending_refunds_paise = int(pending_refunds_row[0] or 0) if pending_refunds_row else 0
    pending_refunds_count = int(pending_refunds_row[1] or 0) if pending_refunds_row else 0

    recent_refund_rows = (
        await db.execute(
            select(Refund)
            .join(PaymentOrder, PaymentOrder.id == Refund.order_id)
            .where(PaymentOrder.edition_id == edition_id)
            .order_by(Refund.created_at.desc())
            .limit(6)
        )
    ).scalars().all()
    recent_refunds = [
        {
            "id": str(rf.id),
            "orderId": str(rf.order_id),
            "amountPaise": int(rf.amount_paise or 0),
            "reasonCode": rf.reason_code,
            "reasonNote": rf.reason_note,
            "status": rf.status,
            "createdAt": aware(rf.created_at).isoformat() if rf.created_at else None,
            "processedAt": aware(rf.processed_at).isoformat() if rf.processed_at else None,
        }
        for rf in recent_refund_rows
    ]

    reg_confirmed = (
        await db.execute(
            select(func.count(Registration.id)).where(
                Registration.edition_id == edition_id,
                Registration.status == "confirmed",
            )
        )
    ).scalar() or 0

    reg_pending = (
        await db.execute(
            select(func.count(Registration.id)).where(
                Registration.edition_id == edition_id,
                Registration.status.in_(["pending", "reserved"]),
            )
        )
    ).scalar() or 0

    reg_cancelled = (
        await db.execute(
            select(func.count(Registration.id)).where(
                Registration.edition_id == edition_id,
                Registration.status == "cancelled",
            )
        )
    ).scalar() or 0

    # One person who attends three events was counted three times, so the
    # attendance card reported more people than the convention holds.
    checked_in = (
        await db.execute(
            select(func.count(func.distinct(AttendanceRecord.user_id))).where(
                AttendanceRecord.edition_id == edition_id,
                AttendanceRecord.result == "admitted",
            )
        )
    ).scalar() or 0

    events_total = (
        await db.execute(
            select(func.count(Event.id)).where(Event.edition_id == edition_id)
        )
    ).scalar() or 0

    events_pub = (
        await db.execute(
            select(func.count(Event.id)).where(
                Event.edition_id == edition_id,
                Event.status.in_(["published", "open"]),
            )
        )
    ).scalar() or 0

    # Capacity is stored per event in the event's own unit ("participants" or
    # "entries"), so a plain SUM added people and teams into one meaningless
    # number. Report each unit separately; ``seats_taken`` uses the same units.
    capacity_rows = (
        await db.execute(
            select(
                Event.capacity_unit,
                func.coalesce(func.sum(Event.capacity), 0),
            )
            .where(Event.edition_id == edition_id)
            .group_by(Event.capacity_unit)
        )
    ).all()
    capacity_by_unit = {
        str(unit or "participants"): int(total or 0) for unit, total in capacity_rows
    }
    capacity = sum(capacity_by_unit.values())

    recent_rows = (
        await db.execute(
            select(
                Registration,
                User.full_name,
                User.email,
                Event.title,
            )
            .join(User, User.id == Registration.user_id)
            .outerjoin(Event, Event.id == Registration.event_id)
            .where(Registration.edition_id == edition_id)
            .order_by(Registration.created_at.desc())
            .limit(8)
        )
    ).all()
    recent_registrations = [
        {
            "id": str(row.id),
            "userName": full_name,
            "userEmail": email,
            "eventTitle": title or "Convention pass",
            "kind": row.kind,
            "status": row.status,
            "registrationNumber": row.registration_number,
            "createdAt": aware(row.created_at).isoformat() if row.created_at else None,
        }
        for row, full_name, email, title in recent_rows
    ]

    # ── Attendee logistics ────────────────────────────────────────────────
    # Gender, meal preference and hostel stay are captured on the college
    # registration row. A rejected row never becomes an attendee, so every
    # tally below leaves those out.
    attendee_scope = (
        CollegeRegistration.edition_id == edition_id,
        CollegeRegistration.verification_status.notin_(("rejected", "payment_pending")),
    )
    gender_rows = (
        await db.execute(
            select(CollegeRegistration.gender, func.count(CollegeRegistration.id))
            .where(*attendee_scope)
            .group_by(CollegeRegistration.gender)
        )
    ).all()
    gender_counts = {code: int(count or 0) for code, count in gender_rows}
    gender_split = [
        {"key": "male", "label": "Male", "count": gender_counts.get(0, 0)},
        {"key": "female", "label": "Female", "count": gender_counts.get(1, 0)},
        {"key": "unspecified", "label": "Unspecified", "count": gender_counts.get(None, 0)},
    ]

    food_rows = (
        await db.execute(
            select(CollegeRegistration.food_preference, func.count(CollegeRegistration.id))
            .where(*attendee_scope)
            .group_by(CollegeRegistration.food_preference)
        )
    ).all()
    food_counts = {code: int(count or 0) for code, count in food_rows}
    food_split = [
        {"key": "veg", "label": "Vegetarian", "count": food_counts.get(0, 0)},
        {"key": "non_veg", "label": "Non-vegetarian", "count": food_counts.get(1, 0)},
        {"key": "unspecified", "label": "Not answered", "count": food_counts.get(None, 0)},
    ]

    stay_rows = (
        await db.execute(
            select(
                CollegeRegistration.needs_accommodation,
                func.count(CollegeRegistration.id),
            )
            .where(*attendee_scope)
            .group_by(CollegeRegistration.needs_accommodation)
        )
    ).all()
    stay_counts = {bool(flag): int(count or 0) for flag, count in stay_rows}
    accommodation = {
        "needed": stay_counts.get(True, 0),
        "notNeeded": stay_counts.get(False, 0),
        "total": sum(stay_counts.values()),
    }

    pass_category_rows = (
        await db.execute(
            select(
                CollegeRegistration.category_code,
                CollegeRegistration.category_name,
                func.count(CollegeRegistration.id),
            )
            .where(*attendee_scope)
            .group_by(CollegeRegistration.category_code, CollegeRegistration.category_name)
            .order_by(func.count(CollegeRegistration.id).desc())
        )
    ).all()
    pass_categories = [
        {"code": code, "name": name or code, "count": int(count or 0)}
        for code, name, count in pass_category_rows
    ]

    event_registration_rows = (
        await db.execute(
            select(
                Event.id,
                Event.title,
                Event.status,
                Event.capacity,
                Event.capacity_unit,
                func.count(Registration.id),
            )
            .outerjoin(
                Registration,
                and_(
                    Registration.event_id == Event.id,
                    Registration.status.in_(["confirmed", "pending"]),
                ),
            )
            .where(Event.edition_id == edition_id)
            .group_by(Event.id, Event.title, Event.status, Event.capacity, Event.capacity_unit)
            .order_by(func.count(Registration.id).desc(), Event.title)
        )
    ).all()
    event_registrations = [
        {
            "id": str(event_id),
            "title": title,
            "status": status,
            "count": int(count or 0),
            "capacity": int(capacity or 0),
            "capacityUnit": unit or "participants",
        }
        for event_id, title, status, capacity, unit, count in event_registration_rows
    ]

    sales_rows = (
        await db.execute(
            select(
                func.date(func.coalesce(PaymentOrder.paid_at, PaymentOrder.created_at)),
                func.sum(PaymentOrder.amount_paise),
                func.count(PaymentOrder.id),
            )
            .where(
                PaymentOrder.edition_id == edition_id,
                PaymentOrder.status.in_(["paid", "refunded"]),
            )
            .group_by(func.date(func.coalesce(PaymentOrder.paid_at, PaymentOrder.created_at)))
            .order_by(func.date(func.coalesce(PaymentOrder.paid_at, PaymentOrder.created_at)))
        )
    ).all()
    sales_by_day = [
        {"date": str(day), "amountPaise": int(amount or 0), "count": int(count or 0)}
        for day, amount, count in sales_rows
    ]

    category_rows = (
        await db.execute(
            select(EventCategory.name, func.count(Registration.id))
            .join(Event, Event.category_id == EventCategory.id)
            .join(Registration, Registration.event_id == Event.id)
            .where(
                Event.edition_id == edition_id,
                Registration.status == "confirmed",
            )
            .group_by(EventCategory.name)
            .order_by(func.count(Registration.id).desc())
        )
    ).all()
    category_split = [
        {"category": name, "count": int(count or 0)} for name, count in category_rows
    ]

    seats_taken_by_unit = await capacity_usage_by_unit(db, edition_id)
    stats = DashboardStats(
        edition_id=edition.id,
        edition_name=edition.name,
        passes_sold=passes_sold,
        revenue_paise=revenue,
        refunded_paise=refunded,
        net_revenue_paise=int(revenue or 0) - int(refunded or 0),
        pending_refunds_paise=pending_refunds_paise,
        pending_refunds_count=pending_refunds_count,
        recent_refunds=recent_refunds,
        registrations_confirmed=reg_confirmed,
        registrations_pending=reg_pending,
        registrations_cancelled=reg_cancelled,
        checked_in=checked_in,
        events_published=events_pub,
        events_total=events_total,
        seats_capacity=capacity,
        seats_taken=reg_confirmed,
        capacity_by_unit=capacity_by_unit,
        seats_taken_by_unit=seats_taken_by_unit,
        recent_registrations=recent_registrations,
        sales_by_day=sales_by_day,
        category_split=category_split,
        gender_split=gender_split,
        food_split=food_split,
        accommodation=accommodation,
        pass_categories=pass_categories,
        event_registrations=event_registrations,
    )
    cache_set(cache_key, stats, ttl_seconds=15.0)
    return stats


async def capacity_usage_by_unit(
    db: AsyncSession, edition_id: uuid.UUID
) -> dict[str, int]:
    """Live seats per capacity unit, computed the same way the event list does.

    The dashboard used to report ``registrations_confirmed`` as "seats taken"
    while the event page counted teams for entries-unit events; the two never
    matched. This reuses ``events.capacity_usage`` so there is one definition.
    """
    from app.services.events import capacity_usage

    events = list(
        (
            await db.execute(select(Event).where(Event.edition_id == edition_id))
        ).scalars()
    )
    usage = await capacity_usage(db, events)
    totals: dict[str, int] = {}
    for event in events:
        unit = str(event.capacity_unit or "participants")
        totals[unit] = totals.get(unit, 0) + int(usage.get(event.id, 0))
    return totals


__all__ = [
    "aware",
    "capacity_usage_by_unit",
    "accepting_bookings",
    "cancel_edition",
    "current_edition",
    "edition_by_slug",
    "edition_by_id",
    "current_policy",
    "policy_public",
    "registration_open",
    "serialize_edition",
    "check_policy",
    "apply_policy",
    "dashboard",
]
