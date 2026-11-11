"""Edition lifecycle, active policy enforcement and admin dashboard rollup."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_delete, cache_delete_pattern, cache_get, cache_set
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
    EligibilityVerification,
    Event,
    EventCategory,
)
from app.models.user import User
from app.schemas.admin import DashboardStats, PolicyCheck
from app.schemas.public import EditionPublic, PolicyPublic
from app.services.audit import record


def aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def current_edition(db: AsyncSession) -> ConventionEdition:
    row = (
        await db.execute(
            select(ConventionEdition)
            .where(ConventionEdition.status.in_(["published", "open"]))
            .order_by(ConventionEdition.starts_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFound("No active convention edition found.")
    return row


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
    row = await db.get(ConventionEdition, edition_id)
    if row is None:
        raise NotFound("Convention edition not found.")
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


def serialize_edition(
    edition: ConventionEdition, policy: EditionPolicy | None = None
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
    if count is not None and count < 0:
        blocking.append("The included event count cannot be negative.")
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
    if count is not None and eligible and count > len(eligible):
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
        addon_requires_pass=payload.get("addon_requires_pass", True),
        team_members_require_pass=payload.get("team_members_require_pass", True),
        selection_change_deadline=payload.get("selection_change_deadline"),
        team_fee_basis_default=payload.get("team_fee_basis_default", "per_participant"),
        hold_minutes=payload.get("hold_minutes", 15),
        refund_rules=payload.get("refund_rules", {}),
        gst_note=payload.get("gst_note"),
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

    passes_pending = (
        await db.execute(
            select(func.count(ConventionPass.id)).where(
                ConventionPass.edition_id == edition_id,
                ConventionPass.status == "pending",
            )
        )
    ).scalar() or 0

    revenue = (
        await db.execute(
            select(func.sum(PaymentOrder.amount_paise)).where(
                PaymentOrder.edition_id == edition_id,
                PaymentOrder.status == "paid",
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
                Registration.status.in_(["pending", "reserved", "pending_verification"]),
            )
        )
    ).scalar() or 0

    verif_pending = (
        await db.execute(
            select(func.count(EligibilityVerification.id)).where(
                EligibilityVerification.edition_id == edition_id,
                EligibilityVerification.status == "pending",
            )
        )
    ).scalar() or 0

    checked_in = (
        await db.execute(
            select(func.count(AttendanceRecord.id)).where(
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

    capacity = (
        await db.execute(
            select(func.sum(Event.capacity)).where(Event.edition_id == edition_id)
        )
    ).scalar() or 0

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

    sales_rows = (
        await db.execute(
            select(
                func.date(func.coalesce(PaymentOrder.paid_at, PaymentOrder.created_at)),
                func.sum(PaymentOrder.amount_paise),
                func.count(PaymentOrder.id),
            )
            .where(
                PaymentOrder.edition_id == edition_id,
                PaymentOrder.status == "paid",
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

    stats = DashboardStats(
        edition_id=edition.id,
        edition_name=edition.name,
        passes_sold=passes_sold,
        passes_pending=passes_pending,
        revenue_paise=revenue,
        refunded_paise=refunded,
        registrations_confirmed=reg_confirmed,
        registrations_pending=reg_pending,
        verifications_pending=verif_pending,
        checked_in=checked_in,
        events_published=events_pub,
        events_total=events_total,
        seats_capacity=capacity,
        seats_taken=reg_confirmed,
        recent_registrations=recent_registrations,
        sales_by_day=sales_by_day,
        category_split=category_split,
    )
    cache_set(cache_key, stats, ttl_seconds=15.0)
    return stats


__all__ = [
    "aware",
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
