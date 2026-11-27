"""Administrative operations: catalogue, pricing, policy changes, verification decisions and staff access."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_permission, require_any_permission, require_min_role
from app.integrations.storage import get_storage
from app.core.attendee import decode_food, decode_gender
from app.core.cache import cache_delete_pattern
from app.core.errors import AppError
from app.core.errors import Conflict, NotFound, StepUpRequired, ValidationFailed
from app.core.permissions import permissions_for
from app.core.rate_limit import limiter
from app.core.uploads import read_upload_limited
from app.db.session import get_db
from app.models.commerce import (
    AttendanceRecord,
    AuditLog,
    ConventionPass,
    IncludedEventSelection,
    PaymentOrder,
    Refund,
    Registration,
    Team,
    TeamMember,
)
from app.models.edition import (
    ConventionEdition,
    EditionPolicy,
    Event,
    EventCategory,
    Icon,
)
from app.models.registration import CollegeRegistration
from app.models.user import User
from app.schemas.admin import (
    AdminForceCancelPayload,
    CustomCredentialRevoke,
    CustomCredentialUpsert,
    AdminManualAttendancePayload,
    AdminProcessRefundPayload,
    DbPlaygroundSeedPayload,
    AnnouncementUpsert,
    CategoryUpsert,
    CheckinRequest,
    EditionUpdate,
    EventUpsert,
    MembershipGrant,
    PolicyUpdate,
    RefundCreate,
    UserStatusUpdate,
)
from app.services.audit import record
from app.services.tickets import revoke_for_registration
from app.services import (
    announcements as announcement_service,
    credentials as credential_service,
    college_registrations as registration_service,
    editions as edition_service,
    events as event_service,
    icons as icon_service,
    payments as payment_service,
    tickets as ticket_service,
    users as user_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/editions/{edition_id}/admin", tags=["admin"])


async def _attendance_for(
    db: AsyncSession,
    edition_id: uuid.UUID,
    user_id: uuid.UUID,
    event_id: uuid.UUID | None,
    day: str,
) -> AttendanceRecord | None:
    """The attendance row a scan of this user/day/scope would duplicate.

    A pass-level scan has ``event_id = NULL``, and SQL treats NULLs as distinct
    inside a unique constraint, so the row has to be found explicitly instead of
    relying on the constraint for that case.
    """
    stmt = select(AttendanceRecord).where(
        AttendanceRecord.edition_id == edition_id,
        AttendanceRecord.user_id == user_id,
        AttendanceRecord.day == day,
    )
    if event_id is None:
        stmt = stmt.where(AttendanceRecord.event_id.is_(None))
    else:
        stmt = stmt.where(AttendanceRecord.event_id == event_id)
    return (
        await db.execute(
            stmt.order_by(AttendanceRecord.checked_in_at.desc()).limit(1)
        )
    ).scalars().first()


def _role(ctx: AuthContext, edition_id: uuid.UUID) -> str:
    return ctx.role_for(edition_id) or (ctx.roles[0] if ctx.roles else "super_admin")


@router.get("/overview")
async def overview(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("stats.read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Dashboard counts must not include expired 24-hour holds.
    await registration_service.lazy_enforce_for_read(db, edition_id=edition_id)
    stats = await edition_service.dashboard(db, edition_id)
    return {"data": stats.model_dump(by_alias=True)}


@router.post("/sync")
async def sync_data(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("stats.read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.core.cache import cache_clear

    expired = await payment_service.expire_unpaid(db)
    await db.commit()
    cache_clear()
    return {
        "data": {
            "synced": True,
            "expiredOrdersAndReservations": expired,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    }


@router.get("/email-outbox")
async def email_outbox_summary(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delivery state of transactional email, plus whether a provider exists."""
    from app.core.config import get_settings
    from app.integrations.email import ACTIVE_STATUSES, MAX_ATTEMPTS
    from app.models.commerce import EmailOutbox

    rows = (
        await db.execute(
            select(EmailOutbox.status, func.count()).group_by(EmailOutbox.status)
        )
    ).all()
    return {
        "data": {
            "available": get_settings().email_available,
            "dryRun": get_settings().email_dry_run,
            "maxAttempts": MAX_ATTEMPTS,
            "activeStatuses": list(ACTIVE_STATUSES),
            "counts": {status: count for status, count in rows},
        }
    }


@router.post(
    "/email-outbox/dispatch",
    dependencies=[Depends(limiter("admin_email_dispatch", 10, 60))],
)
async def dispatch_email_outbox(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.core.config import get_settings
    from app.integrations.email import send_batch

    if not get_settings().email_available:
        return {
            "data": {
                "sent": 0,
                "available": False,
                "message": "No email provider is configured, so nothing was sent.",
            }
        }
    sent = await send_batch(db)
    return {"data": {"sent": sent, "available": True}}


@router.post(
    "/maintenance/expire-orders",
    dependencies=[Depends(limiter("admin_expire_orders", 10, 60))],
)
async def expire_orders(
    edition_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Cron-friendly sweep: expire abandoned checkouts and release holds."""
    expired = await payment_service.expire_unpaid(db)
    await db.commit()
    return {"data": {"expired": expired}}


@router.post(
    "/maintenance/enforce-compliance",
    dependencies=[Depends(limiter("admin_enforce_compliance", 10, 60))],
)
async def enforce_compliance_deadlines(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Cron-friendly sweep for expired 24-hour desk requests.

    Releases event seats, refunds paid event seats and repairs team rosters for
    attendees who did not answer a document re-upload or category top-up
    request. Each registration is enforced once.
    """
    result = await registration_service.enforce_lapsed_compliance(
        db, edition_id=edition_id, limit=200
    )
    await db.commit()
    return {"data": result}


@router.get("/my-permissions")
async def my_permissions(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("stats.read")),
) -> dict:
    role = _role(ctx, edition_id)
    perms = permissions_for(role)
    return {"data": {"role": role, "permissions": sorted(perms)}}


@router.get("/settings")
async def get_settings_route(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    edition = await edition_service.edition_by_id(db, edition_id)
    return {
        "data": {
            "id": str(edition.id),
            "slug": edition.slug,
            "name": edition.name,
            "tagline": getattr(edition, "hero_subtitle", None) or getattr(edition, "hero_headline", None),
            "venue": edition.venue,
            "city": edition.city,
            "startsAt": edition_service.aware(edition.starts_at).isoformat() if edition.starts_at else None,
            "endsAt": edition_service.aware(edition.ends_at).isoformat() if edition.ends_at else None,
            "registrationOpensAt": edition_service.aware(edition.registration_opens_at).isoformat() if edition.registration_opens_at else None,
            "registrationClosesAt": edition_service.aware(edition.registration_closes_at).isoformat() if edition.registration_closes_at else None,
            "status": edition.status,
            "contactEmail": edition.contact_email,
            "branding": {"theme": edition.theme} if getattr(edition, "theme", None) else {},
        }
    }


@router.patch("/settings")
async def update_settings(
    edition_id: uuid.UUID,
    payload: EditionUpdate,
    request: Request,
    ctx: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    edition = await edition_service.edition_by_id(db, edition_id)
    data = payload.model_dump(exclude_unset=True)
    if "tagline" in data:
        edition.hero_subtitle = data.pop("tagline")
    data.pop("branding", None)

    from app.core.errors import ValidationFailed

    # These columns are NOT NULL. A cleared input in the console must come back
    # as a readable 422 instead of a database integrity error (500) that leaves
    # the operator with no idea which field broke the save.
    required_fields = {
        "name": "Edition name",
        "venue": "Venue",
        "city": "City",
        "starts_at": "Starts at",
        "ends_at": "Ends at",
    }
    for field, label in required_fields.items():
        if field not in data:
            continue
        value = data[field]
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValidationFailed(f"{label} is required and cannot be empty.")
        if isinstance(value, str):
            data[field] = value.strip()

    starts = data.get("starts_at", edition.starts_at)
    ends = data.get("ends_at", edition.ends_at)
    if starts and ends:
        left, right = starts, ends
        if left.tzinfo is None and right.tzinfo is not None:
            right = right.replace(tzinfo=None)
        elif right.tzinfo is None and left.tzinfo is not None:
            left = left.replace(tzinfo=None)
        if right <= left:
            raise ValidationFailed("The convention must end after it starts.")

    # A window that closes before it opens silently disables registration for
    # the entire convention, so reject it before anything is written.
    opens = data.get("registration_opens_at", edition.registration_opens_at)
    closes = data.get("registration_closes_at", edition.registration_closes_at)
    if opens and closes:
        left, right = opens, closes
        if left.tzinfo is None and right.tzinfo is not None:
            right = right.replace(tzinfo=None)
        elif right.tzinfo is None and left.tzinfo is not None:
            left = left.replace(tzinfo=None)
        if right <= left:
            raise ValidationFailed("Registration must close after it opens.")

    new_status = data.get("status")
    cancelling = new_status == "cancelled" and edition.status != "cancelled"

    for k, v in data.items():
        if hasattr(edition, k):
            setattr(edition, k, v)
    await db.flush()

    cascade = None
    if cancelling:
        # Cancelling a convention used to change a label and nothing else: seats,
        # tickets, passes and money all stayed live. The cascade closes every
        # event, cancels the passes and queues one refund per paid order.
        cascade = await edition_service.cancel_edition(
            db,
            request,
            edition,
            reason=(payload.model_dump(exclude_unset=True).get("tagline") or "Edition cancelled"),
            actor_id=ctx.user.id,
            actor_role=_role(ctx, edition_id),
        )
    await db.commit()
    # The public edition page is cached; a settings patch changed the name, the
    # dates and the status it renders.
    cache_delete_pattern("public:*")
    cache_delete_pattern("admin:dashboard:*")
    return {"data": {"updated": True, "cascade": cascade}}


@router.get("/policies")
async def policies(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("policy.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = list(
        (
            await db.execute(
                select(EditionPolicy)
                .where(EditionPolicy.edition_id == edition_id)
                .order_by(EditionPolicy.version.desc())
            )
        ).scalars()
    )
    return {
        "data": [
            {
                "id": str(p.id),
                "version": p.version,
                "isCurrent": p.is_current,
                "passPricePaise": p.pass_price_paise,
                "lunchIncludedDays": p.lunch_included_days or [],
                "includedEventCount": p.included_event_count,
                "includedSelectionMode": getattr(p, "included_selection_mode", "exact"),
                "includedValueCapPaise": p.included_value_cap_paise,
                "capInclusive": p.cap_inclusive,
                "holdMinutes": p.hold_minutes,
                "addonRequiresPass": p.addon_requires_pass,
                "teamMembersRequirePass": p.team_members_require_pass,
                "teamFeeBasisDefault": p.team_fee_basis_default,
                "selectionChangeDeadline": edition_service.aware(p.selection_change_deadline).isoformat() if p.selection_change_deadline else None,
                "reason": p.reason,
                "createdAt": edition_service.aware(p.created_at).isoformat() if p.created_at else None,
            }
            for p in rows
        ]
    }


@router.post("/policies/check")
async def policy_check(
    edition_id: uuid.UUID,
    payload: PolicyUpdate,
    ctx: AuthContext = Depends(require_permission("policy.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    check = await edition_service.check_policy(db, edition_id, payload.model_dump())
    return {"data": check.model_dump(by_alias=True)}


@router.post("/policies")
async def create_policy(
    edition_id: uuid.UUID,
    payload: PolicyUpdate,
    request: Request,
    ctx: AuthContext = Depends(require_permission("policy.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    new_p = await edition_service.apply_policy(
        db,
        request,
        edition_id,
        payload.model_dump(),
        actor_id=ctx.user.id,
        actor_role=_role(ctx, edition_id),
    )
    await db.commit()
    return {"data": {"id": str(new_p.id), "version": new_p.version}}


@router.get("/categories")
async def categories(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("events.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = list(
        (
            await db.execute(
                select(EventCategory)
                .where(EventCategory.edition_id == edition_id)
                .order_by(EventCategory.display_order)
            )
        ).scalars()
    )
    return {
        "data": [
            {
                "id": str(r.id),
                "name": r.name,
                "slug": r.slug,
                "displayOrder": r.display_order,
                "accent": r.accent,
                "iconId": str(r.icon_id) if r.icon_id else None,
            }
            for r in rows
        ]
    }


@router.post("/categories")
async def create_category(
    edition_id: uuid.UUID,
    payload: CategoryUpsert,
    request: Request,
    ctx: AuthContext = Depends(require_permission("events.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    cat = EventCategory(
        edition_id=edition_id,
        name=payload.name.strip(),
        slug=payload.slug.strip().lower(),
        display_order=payload.display_order,
        accent=payload.accent,
        icon_id=payload.icon_id,
    )
    db.add(cat)
    await db.flush()
    await db.commit()
    return {"data": {"id": str(cat.id), "name": cat.name, "slug": cat.slug}}


@router.patch("/categories/{category_id}")
async def update_category(
    edition_id: uuid.UUID,
    category_id: uuid.UUID,
    payload: CategoryUpsert,
    request: Request,
    ctx: AuthContext = Depends(require_permission("events.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    cat = await db.get(EventCategory, category_id)
    if cat is None or cat.edition_id != edition_id:
        raise NotFound("Category not found.")
    cat.name = payload.name.strip()
    cat.slug = payload.slug.strip().lower()
    cat.display_order = payload.display_order
    cat.accent = payload.accent
    cat.icon_id = payload.icon_id
    await db.flush()
    await db.commit()
    return {"data": {"id": str(cat.id), "updated": True}}


@router.get("/events")
async def admin_events(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("events.read")),
    db: AsyncSession = Depends(get_db),
    status: str | None = None,
    q: str | None = None,
) -> dict:
    await registration_service.lazy_enforce_for_read(db, edition_id=edition_id)
    events = await event_service.admin_list_events(db, edition_id, status=status, q=q)
    return {"data": events}


@router.get("/events/{event_id}")
async def admin_event(
    edition_id: uuid.UUID,
    event_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("events.read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    event = await event_service.event_by_id(db, event_id)
    if event.edition_id != edition_id:
        raise NotFound("Event not found.")
    await registration_service.lazy_enforce_for_read(db, edition_id=edition_id)
    payload = await event_service.event_admin_payload(db, event)
    return {"data": payload}


@router.post("/events")
async def create_event(
    edition_id: uuid.UUID,
    payload: EventUpsert,
    request: Request,
    ctx: AuthContext = Depends(require_permission("events.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    event = await event_service.upsert_event(
        db,
        request,
        edition_id,
        payload.model_dump(),
        actor_id=ctx.user.id,
        actor_role=_role(ctx, edition_id),
    )
    await db.commit()
    return {"data": {"id": str(event.id), "slug": event.slug}}


@router.patch("/events/{event_id}")
async def update_event(
    edition_id: uuid.UUID,
    event_id: uuid.UUID,
    payload: EventUpsert,
    request: Request,
    ctx: AuthContext = Depends(require_permission("events.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    event = await event_service.upsert_event(
        db,
        request,
        edition_id,
        payload.model_dump(),
        event_id=event_id,
        actor_id=ctx.user.id,
        actor_role=_role(ctx, edition_id),
    )
    await db.commit()
    return {"data": {"id": str(event.id), "updated": True}}


@router.get("/icons")
async def icons(
    edition_id: uuid.UUID,
    # Icon curation is its own permission ("icon.write"); borrowing events.write
    # meant the catalogue entry was dead and event editors could not manage art.
    ctx: AuthContext = Depends(require_permission("icon.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    icons_list = await icon_service.listed(db, edition_id)
    return {"data": icons_list}


@router.post("/banner-upload")
async def upload_banner(
    edition_id: uuid.UUID,
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_permission("events.write")),
) -> dict:
    data = await read_upload_limited(file, 10 * 1024 * 1024, label="Banner image")

    # Trust the bytes, not the filename or the declared content type.
    if data.startswith(bytes.fromhex("ffd8ff")):
        ext, content_type = "jpg", "image/jpeg"
    elif data.startswith(bytes.fromhex("89504e470d0a1a0a")):
        ext, content_type = "png", "image/png"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        ext, content_type = "webp", "image/webp"
    elif data[4:12] in (b"ftypavif", b"ftypavis"):
        ext, content_type = "avif", "image/avif"
    else:
        raise AppError(
            "Upload a JPG, PNG, WebP or AVIF image.",
            code="FILE_TYPE_NOT_ALLOWED",
            status_code=415,
        )

    key = f"banners/{edition_id}/{uuid.uuid4().hex}.{ext}"
    storage = get_storage()
    clean_key = await storage.put(key, data, content_type)
    url = storage.public_url(clean_key)
    return {"data": {"url": url, "key": clean_key}}


@router.post("/icons")
async def upload_icon(
    edition_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    name: Annotated[str, Form()] = "",
    recolorable: Annotated[bool, Form()] = False,
    ctx: AuthContext = Depends(require_permission("icon.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    data = await read_upload_limited(file, 300 * 1024, label="Icon")
    icon = await icon_service.create_icon(
        db,
        request,
        edition_id=edition_id,
        data=data,
        name=name or file.filename or "icon",
        recolorable=recolorable,
        actor_id=ctx.user.id,
        actor_role=_role(ctx, edition_id),
    )
    await db.commit()
    return {"data": icon_service.icon_payload(icon)}


@router.delete("/icons/{icon_id}")
async def archive_icon(
    edition_id: uuid.UUID,
    icon_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(require_permission("icon.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    icon = await db.get(Icon, icon_id)
    if icon is None or icon.edition_id != edition_id:
        raise NotFound("Icon not found.")
    await icon_service.archive(
        db,
        request,
        icon,
        actor_id=ctx.user.id,
        actor_role=_role(ctx, edition_id),
    )
    await db.commit()
    return {"data": {"archived": True}}


@router.get("/users")
async def users(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("users.read")),
    db: AsyncSession = Depends(get_db),
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict:
    rows, total = await user_service.list_users(
        db,
        edition_id,
        q=q,
        page=page,
        page_size=page_size,
        include_pii=ctx.has("user.read_pii", edition_id),
    )
    return {"data": rows, "total": total, "page": page, "pageSize": page_size}


@router.patch("/users/{user_id}/status")
async def user_status(
    edition_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: UserStatusUpdate,
    request: Request,
    ctx: AuthContext = Depends(require_permission("users.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await user_service.set_status(
        db,
        request,
        user_id,
        status=payload.status,
        reason=payload.reason,
        actor_id=ctx.user.id,
        actor_role=_role(ctx, edition_id),
    )
    await db.commit()
    return {"data": {"updated": True}}


@router.get("/memberships")
async def memberships(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("staff.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = await user_service.memberships_for(db, edition_id)
    return {"data": rows}


@router.post("/memberships", dependencies=[Depends(limiter("admin_membership", 30, 60))])
async def grant_membership(
    edition_id: uuid.UUID,
    payload: MembershipGrant,
    request: Request,
    ctx: AuthContext = Depends(require_permission("staff.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    m, replaced = await user_service.grant_membership(
        db,
        request,
        email=payload.email,
        role=payload.role,
        edition_id=edition_id,
        actor_id=ctx.user.id,
        actor_role=_role(ctx, edition_id),
    )
    await db.commit()
    return {"data": {"granted": True, "role": m.role, "replacedRoles": replaced}}


@router.post("/staff-invites", dependencies=[Depends(limiter("admin_staff_invite", 30, 60))])
async def invite_staff(
    edition_id: uuid.UUID,
    payload: MembershipGrant,
    request: Request,
    ctx: AuthContext = Depends(require_permission("staff.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    inv, token = await user_service.invite_staff(
        db,
        request,
        email=payload.email,
        role=payload.role,
        edition_id=edition_id,
        actor_id=ctx.user.id,
        actor_role=_role(ctx, edition_id),
    )
    await db.commit()
    from app.core.config import get_settings

    base = (get_settings().app_base_url or get_settings().frontend_origin).rstrip("/")
    return {
        "data": {
            "invited": True,
            "email": inv.email_normalized,
            "role": payload.role,
            "inviteToken": token,
            "inviteUrl": f"{base}/login?invite={token}",
            "expiresAt": inv.expires_at.isoformat() if inv.expires_at else None,
        }
    }


@router.get("/payments")
async def payments_list(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("finance.read")),
    db: AsyncSession = Depends(get_db),
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict:
    stmt = (
        select(PaymentOrder, User)
        .join(User, PaymentOrder.user_id == User.id)
        .where(PaymentOrder.edition_id == edition_id)
    )
    if status:
        stmt = stmt.where(PaymentOrder.status == status)
    rows = list(
        (
            await db.execute(
                stmt.order_by(PaymentOrder.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return {
        "data": [
            {
                "id": str(o.id),
                "userName": u.full_name,
                "userEmail": u.email,
                "purpose": o.purpose,
                "amountPaise": o.amount_paise,
                "status": o.status,
                "gatewayOrderId": o.gateway_order_id,
                "createdAt": edition_service.aware(o.created_at).isoformat() if o.created_at else None,
                "paidAt": edition_service.aware(o.paid_at).isoformat() if o.paid_at else None,
            }
            for o, u in rows
        ]
    }


@router.post("/refunds", dependencies=[Depends(limiter("admin_refund", 30, 60))])
async def create_refund(
    edition_id: uuid.UUID,
    payload: RefundCreate,
    request: Request,
    ctx: AuthContext = Depends(require_permission("finance.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    order = await payment_service.order_for(db, payload.order_id)
    if order.edition_id != edition_id:
        raise NotFound("Payment order not found.")
    refund = await payment_service.refund_order(
        db,
        order,
        amount_paise=payload.amount_paise,
        reason_code=payload.reason_code,
        reason_note=payload.reason_note,
        requested_by_id=ctx.user.id,
    )
    await db.commit()
    return {"data": {"refundId": str(refund.id), "status": refund.status}}


@router.get("/refunds")
async def refunds(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("finance.read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = list(
        (
            await db.execute(
                select(Refund).join(PaymentOrder, PaymentOrder.id == Refund.order_id).where(PaymentOrder.edition_id == edition_id)
                .order_by(Refund.created_at.desc())
            )
        ).scalars()
    )
    return {
        "data": [
            {
                "id": str(r.id),
                "orderId": str(r.order_id),
                "amountPaise": r.amount_paise,
                "reasonCode": r.reason_code,
                "reasonNote": r.reason_note,
                "status": r.status,
                "createdAt": edition_service.aware(r.created_at).isoformat() if r.created_at else None,
                "processedAt": edition_service.aware(r.processed_at).isoformat() if r.processed_at else None,
            }
            for r in rows
        ]
    }


@router.get("/registrations")
async def registrations(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(require_any_permission("registration.read", "events.read")),
    db: AsyncSession = Depends(get_db),
    event_id: uuid.UUID | None = None,
    status: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
) -> dict:
    await registration_service.lazy_enforce_for_read(db, edition_id=edition_id)
    stmt = (
        select(Registration, User, Event, PaymentOrder, CollegeRegistration)
        .join(User, Registration.user_id == User.id)
        .join(Event, Registration.event_id == Event.id)
        .outerjoin(PaymentOrder, Registration.order_id == PaymentOrder.id)
        .outerjoin(
            CollegeRegistration,
            and_(
                CollegeRegistration.user_id == User.id,
                CollegeRegistration.edition_id == edition_id,
            ),
        )
        .where(Registration.edition_id == edition_id)
    )
    if event_id:
        stmt = stmt.where(Registration.event_id == event_id)
    if status:
        stmt = stmt.where(Registration.status == status)
    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(User.full_name).like(term),
                func.lower(User.email).like(term),
                func.lower(Registration.registration_number).like(term),
                func.lower(Event.title).like(term),
            )
        )
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0
    rows = list(
        (
            await db.execute(
                stmt.order_by(Registration.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )

    # Collect order IDs to look up any processed or pending refunds
    order_ids = [o.id for _, _, _, o, _ in rows if o is not None]
    refund_map = {}
    if order_ids:
        r_rows = (
            await db.execute(
                select(Refund.order_id, func.coalesce(func.sum(Refund.amount_paise), 0))
                .where(Refund.order_id.in_(order_ids), Refund.status.in_(["processed", "pending"]))
                .group_by(Refund.order_id)
            )
        ).all()
        refund_map = {oid: int(amt or 0) for oid, amt in r_rows}

    show_pii = ctx.has("user.read_pii", edition_id)

    data = []
    for r, u, e, o, col in rows:
        is_included = r.kind == "included" or r.fee_paise == 0
        refunded_paise = refund_map.get(o.id, 0) if o else 0
        order_remaining = max(0, (o.amount_paise - refunded_paise)) if o else 0
        max_refundable = 0 if is_included else min(r.fee_paise, order_remaining)
        is_refundable = bool(o and o.status == "paid" and not is_included and max_refundable > 0)

        data.append(
            {
                "id": str(r.id),
                "registrationNumber": r.registration_number,
                "userName": u.full_name,
                "userEmail": u.email if show_pii else user_service.mask_email(u.email),
                "userPhone": (col.phone if col else None) if show_pii else None,
                "userCollege": (col.college_name if col else None) if show_pii else None,
                "eventId": str(e.id),
                "eventTitle": e.title,
                "venueRoom": e.venue_room,
                "kind": r.kind,
                "feePaise": r.fee_paise,
                "isIncluded": is_included,
                "status": r.status,
                "createdAt": edition_service.aware(r.created_at).isoformat() if r.created_at else None,
                "cancelledAt": edition_service.aware(r.cancelled_at).isoformat() if r.cancelled_at else None,
                "cancelledBy": r.cancelled_by,
                "cancellationReason": r.cancellation_reason,
                "orderId": str(o.id) if o else None,
                "orderStatus": o.status if o else None,
                "orderAmountPaise": o.amount_paise if o else 0,
                "refundedAmountPaise": refunded_paise,
                "isRefundable": is_refundable,
                "refundableAmountPaise": max_refundable,
                "canCancel": r.status in ("confirmed", "reserved", "pending"),
                "canApprove": r.status == "pending",
            }
        )

    return {
        "data": data,
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


@router.post("/registrations/{registration_id}/approve")
async def approve_event_registration(
    edition_id: uuid.UUID,
    registration_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(require_any_permission("events.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Approve a pending event registration (for requires_approval events) and issue its ticket."""
    from app.models.registration import Registration
    from app.services.tickets import issue_for_registration
    from app.core.cache import cache_delete_pattern
    from app.services.audit import record

    reg = await db.get(Registration, registration_id)
    if reg is None or reg.edition_id != edition_id:
        raise NotFound("Registration not found.")
    if reg.status != "pending":
        raise ValidationFailed("Only pending registrations can be approved.")

    reg.status = "confirmed"
    await db.flush()
    await issue_for_registration(db, reg)

    await record(
        db,
        request,
        actor_id=ctx.user.id,
        actor_role=ctx.roles[0] if ctx.roles else None,
        action="registration.approved",
        resource_type="registration",
        resource_id=str(reg.id),
        after={"status": "confirmed"},
    )
    await db.commit()
    cache_delete_pattern("public:*")
    cache_delete_pattern("admin:dashboard:*")
    return {"data": {"id": str(reg.id), "status": reg.status}}


@router.post("/registrations/{registration_id}/force-cancel")
async def force_cancel_registration(
    edition_id: uuid.UUID,
    registration_id: uuid.UUID,
    payload: AdminForceCancelPayload,
    request: Request,
    ctx: AuthContext = Depends(require_any_permission("events.write", "finance.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    reg = await db.get(Registration, registration_id)
    if reg is None or reg.edition_id != edition_id:
        raise NotFound("Registration not found.")
    if reg.status == "cancelled":
        raise Conflict("Registration is already cancelled.")

    event = await db.get(Event, reg.event_id)
    # The attendee-facing path refuses cancellations inside the cutoff window so
    # a paid seat is not pulled minutes before the event. An admin cancel is not
    # exempt unless the operator says so.
    if event is not None and event.starts_at is not None and not payload.force:
        from app.services.registrations import CANCELLATION_CUTOFF_HOURS

        starts = edition_service.aware(event.starts_at)
        if starts is not None and starts <= datetime.now(UTC) + timedelta(
            hours=CANCELLATION_CUTOFF_HOURS
        ):
            raise Conflict(
                f"This event starts within {CANCELLATION_CUTOFF_HOURS} hours. "
                "Send force=true to cancel it anyway.",
                code="CANCELLATION_CLOSED",
            )
    reg.status = "cancelled"
    reg.cancelled_at = datetime.now(UTC)
    reg.cancelled_by = "admin"
    reg.cancellation_reason = payload.reason or "Removed from event by administration"
    await revoke_for_registration(db, reg.id)
    if reg.team_id is not None:
        from app.services.teams import on_team_registration_cancelled
        await on_team_registration_cancelled(db, reg)

    # Free up included event selection so attendee's quota is restored
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

    refund_data = None
    if payload.issue_refund:
        if reg.kind == "included" or reg.fee_paise == 0:
            raise ValidationFailed("Included free events have no paid fee and are not eligible for refunds.")
        if not reg.order_id:
            raise ValidationFailed("Cannot refund this registration because there is no associated payment order.")
        order = await db.get(PaymentOrder, reg.order_id)
        if order is None or order.status != "paid":
            raise Conflict("Associated payment order is not paid or cannot be refunded.")

        already_refunded = (
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
        order_remaining = max(0, order.amount_paise - int(already_refunded))
        max_refundable = min(reg.fee_paise, order_remaining)

        amount_paise = (
            payload.refund_amount_paise
            if payload.refund_amount_paise is not None
            else max_refundable
        )
        if amount_paise > reg.fee_paise:
            raise ValidationFailed(
                f"Refund amount (INR {amount_paise/100:.2f}) cannot exceed the paid fee of INR {reg.fee_paise/100:.2f}."
            )
        if amount_paise > order_remaining:
            raise ValidationFailed(
                f"Only INR {order_remaining/100:.2f} remains refundable on this order."
            )
        if amount_paise <= 0:
            raise ValidationFailed("Refund amount must be greater than zero.")

        rf = await payment_service.refund_order(
            db,
            order,
            amount_paise,
            reason_code="admin_force_cancel",
            reason_note=payload.refund_reason_note or payload.reason,
            requested_by_id=ctx.user.id,
        )
        refund_data = {"refundId": str(rf.id), "amountPaise": rf.amount_paise}
    elif reg.kind != "included" and reg.fee_paise > 0 and reg.order_id is not None:
        # The seat was taken away without a refund instruction. The money is
        # still the attendee's, so it is parked in the finance ledger instead of
        # disappearing from every screen.
        order = await db.get(PaymentOrder, reg.order_id)
        if order is not None and order.status == "paid":
            already = (
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
            outstanding = max(0, int(order.amount_paise) - int(already))
            if outstanding > 0:
                db.add(
                    Refund(
                        order_id=order.id,
                        amount_paise=min(int(reg.fee_paise), outstanding),
                        reason_code="admin_force_cancel",
                        reason_note=(payload.reason or "Removed from event by administration")[:300],
                        status="pending",
                        requested_by=ctx.user.id,
                    )
                )
                await db.flush()

    cache_delete_pattern("public:*")
    cache_delete_pattern("admin:dashboard:*")
    await record(
        db,
        request,
        action="registration.force_cancelled",
        resource_type="registration",
        resource_id=reg.id,
        actor_id=ctx.user.id,
        actor_role=_role(ctx, edition_id),
        after={
            "status": "cancelled",
            "cancelled_by": "admin",
            "reason": reg.cancellation_reason,
            "event_title": event.title if event else None,
            "refund": refund_data,
        },
    )
    await db.commit()
    return {
        "data": {
            "id": str(reg.id),
            "status": reg.status,
            "cancelledBy": reg.cancelled_by,
            "cancellationReason": reg.cancellation_reason,
            "refund": refund_data,
        }
    }


@router.post("/registrations/{registration_id}/refund")
async def refund_registration(
    edition_id: uuid.UUID,
    registration_id: uuid.UUID,
    payload: AdminProcessRefundPayload,
    request: Request,
    ctx: AuthContext = Depends(require_any_permission("finance.write", "events.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    reg = await db.get(Registration, registration_id)
    if reg is None or reg.edition_id != edition_id:
        raise NotFound("Registration not found.")
    if reg.kind == "included" or reg.fee_paise == 0:
        raise ValidationFailed("Included free events have no paid fee and are not eligible for refunds.")
    if not reg.order_id:
        raise ValidationFailed("No payment order found for this registration.")

    order = await db.get(PaymentOrder, reg.order_id)
    if order is None or order.status != "paid":
        raise ValidationFailed("Only paid registrations can be refunded.")

    already_refunded = (
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
    order_remaining = max(0, order.amount_paise - int(already_refunded))
    max_refundable = min(reg.fee_paise, order_remaining)
    if max_refundable <= 0:
        raise ValidationFailed("This registration has already been fully refunded.")

    amount_paise = (
        payload.amount_paise
        if payload.amount_paise is not None
        else max_refundable
    )
    if amount_paise > reg.fee_paise:
        raise ValidationFailed(
            f"Refund amount (INR {amount_paise/100:.2f}) cannot exceed the paid fee of INR {reg.fee_paise/100:.2f}."
        )
    if amount_paise > order_remaining:
        raise ValidationFailed(
            f"Only INR {order_remaining/100:.2f} remains refundable on this order."
        )
    if amount_paise <= 0:
        raise ValidationFailed("Refund amount must be greater than zero.")

    rf = await payment_service.refund_order(
        db,
        order,
        amount_paise,
        reason_code="admin_event_refund",
        reason_note=payload.reason_note or "Registration refund issued by admin",
        requested_by_id=ctx.user.id,
    )
    await record(
        db,
        request,
        action="registration.refunded",
        resource_type="registration",
        resource_id=reg.id,
        actor_id=ctx.user.id,
        actor_role=_role(ctx, edition_id),
        after={
            "refund_id": str(rf.id),
            "amount_paise": rf.amount_paise,
            "order_id": str(order.id),
        },
    )
    await db.commit()
    return {
        "data": {
            "refundId": str(rf.id),
            "amountPaise": rf.amount_paise,
            "status": rf.status,
            "remainingRefundablePaise": max(0, order_remaining - amount_paise),
        }
    }


@router.get("/announcements")
async def announcements(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("announcements.read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = await announcement_service.list_admin(db, edition_id)
    return {"data": rows}


@router.post("/announcements")
async def create_announcement(
    edition_id: uuid.UUID,
    payload: AnnouncementUpsert,
    request: Request,
    ctx: AuthContext = Depends(require_permission("announcements.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    a = await announcement_service.upsert(
        db,
        request,
        edition_id,
        payload.model_dump(),
        actor_id=ctx.user.id,
        actor_role=_role(ctx, edition_id),
    )
    await db.commit()
    return {"data": {"id": str(a.id)}}


@router.get("/custom-credentials")
async def list_custom_credentials(
    edition_id: uuid.UUID,
    request: Request,
    include_revoked: bool = Query(default=True),
    ctx: AuthContext = Depends(require_permission("credential.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = await credential_service.list_for_edition(
        db, edition_id, include_revoked=include_revoked
    )
    base_url = ticket_service.entry_base_url(str(request.base_url).rstrip("/"))
    return {
        "data": [
            await credential_service.payload_with_entry(db, row, base_url=base_url)
            for row in rows
        ]
    }


@router.post("/custom-credentials/photo")
async def upload_credential_photo(
    edition_id: uuid.UUID,
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_permission("credential.write")),
) -> dict:
    """Store a card photo and return its durable URL.

    The studio used to embed a browser blob URL in the saved card, which dies
    with the tab: a card reprinted the next day came back with no face. Upload
    the bytes here and store the returned URL instead.
    """
    data = await read_upload_limited(file, 5 * 1024 * 1024, label="Card photo")
    # Trust the bytes, not the filename or the declared content type.
    if data.startswith(bytes.fromhex("ffd8ff")):
        ext, content_type = "jpg", "image/jpeg"
    elif data.startswith(bytes.fromhex("89504e470d0a1a0a")):
        ext, content_type = "png", "image/png"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        ext, content_type = "webp", "image/webp"
    else:
        raise AppError(
            "Upload a JPG, PNG or WebP photo.",
            code="FILE_TYPE_NOT_ALLOWED",
            status_code=415,
        )
    key = f"credentials/{edition_id}/{uuid.uuid4().hex}.{ext}"
    storage = get_storage()
    clean_key = await storage.put(key, data, content_type)
    return {"data": {"url": storage.public_url(clean_key), "key": clean_key}}


@router.post("/custom-credentials")
async def create_custom_credential(
    edition_id: uuid.UUID,
    payload: CustomCredentialUpsert,
    request: Request,
    ctx: AuthContext = Depends(require_permission("credential.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # A registered attendee already owns exactly one studio card. Saving their
    # card again reopens that row (with its signed QR) instead of failing on a
    # duplicate ID, which is what the operator expects when they "load" them.
    reused = None
    if payload.registration_id:
        reused = await credential_service.for_registration(
            db, edition_id, payload.registration_id
        )
    credential = await credential_service.create(
        db, edition_id, payload.model_dump(), actor_id=ctx.user.id
    )
    await record(
        db,
        request,
        actor_id=ctx.user.id,
        actor_role=_role(ctx, edition_id),
        action="custom_credential.create",
        resource_type="custom_credential",
        resource_id=str(credential.id),
        after=credential_service.payload(credential),
    )
    view = await credential_service.payload_with_entry(
        db, credential, base_url=ticket_service.entry_base_url(str(request.base_url).rstrip("/"))
    )
    await db.commit()
    return {"data": view, "reused": reused is not None}


@router.patch("/custom-credentials/{credential_id}")
async def update_custom_credential(
    edition_id: uuid.UUID,
    credential_id: uuid.UUID,
    payload: CustomCredentialUpsert,
    request: Request,
    ctx: AuthContext = Depends(require_permission("credential.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    credential = await credential_service.get_for_edition(db, edition_id, credential_id)
    if credential.status != "active":
        raise Conflict("A revoked credential cannot be edited. Create a new card instead.")
    before = credential_service.payload(credential)
    await credential_service.update(
        db, credential, payload.model_dump(exclude_unset=True), actor_id=ctx.user.id
    )
    await record(
        db,
        request,
        actor_id=ctx.user.id,
        actor_role=_role(ctx, edition_id),
        action="custom_credential.update",
        resource_type="custom_credential",
        resource_id=str(credential.id),
        before=before,
        after=credential_service.payload(credential),
    )
    view = await credential_service.payload_with_entry(
        db, credential, base_url=ticket_service.entry_base_url(str(request.base_url).rstrip("/"))
    )
    await db.commit()
    return {"data": view}


@router.post("/custom-credentials/{credential_id}/revoke")
async def revoke_custom_credential(
    edition_id: uuid.UUID,
    credential_id: uuid.UUID,
    payload: CustomCredentialRevoke,
    request: Request,
    ctx: AuthContext = Depends(require_permission("credential.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    credential = await credential_service.get_for_edition(db, edition_id, credential_id)
    before = credential_service.payload(credential)
    await credential_service.revoke(
        db, credential, actor_id=ctx.user.id, reason=payload.reason
    )
    await record(
        db,
        request,
        actor_id=ctx.user.id,
        actor_role=_role(ctx, edition_id),
        action="custom_credential.revoke",
        resource_type="custom_credential",
        resource_id=str(credential.id),
        before=before,
        after=credential_service.payload(credential),
    )
    await db.commit()
    return {"data": credential_service.payload(credential)}


@router.patch("/announcements/{announcement_id}")
async def update_announcement(
    edition_id: uuid.UUID,
    announcement_id: uuid.UUID,
    payload: AnnouncementUpsert,
    request: Request,
    ctx: AuthContext = Depends(require_permission("announcements.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    a = await announcement_service.upsert(
        db,
        request,
        edition_id,
        payload.model_dump(),
        announcement_id=announcement_id,
        actor_id=ctx.user.id,
        actor_role=_role(ctx, edition_id),
    )
    await db.commit()
    return {"data": {"id": str(a.id), "updated": True}}


@router.delete("/announcements/{announcement_id}")
async def delete_announcement(
    edition_id: uuid.UUID,
    announcement_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(require_permission("announcements.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await announcement_service.delete(
        db,
        request,
        edition_id,
        announcement_id,
        actor_id=ctx.user.id,
        actor_role=_role(ctx, edition_id),
    )
    await db.commit()
    return {"data": {"deleted": True}}


@router.get("/audit")
async def audit(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("audit.read")),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict:
    rows = list(
        (
            await db.execute(
                select(AuditLog, User.full_name)
                .outerjoin(User, User.id == AuditLog.actor_id)
                .order_by(AuditLog.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return {
        "data": [
            {
                "id": str(r.id),
                "actorId": str(r.actor_id) if r.actor_id else None,
                "actorName": actor_name,
                "actorRole": r.actor_role,
                "action": r.action,
                "resourceType": r.resource_type,
                "resourceId": r.resource_id,
                "before": r.before,
                "after": r.after,
                "createdAt": edition_service.aware(r.created_at).isoformat() if r.created_at else None,
            }
            for r, actor_name in rows
        ]
    }


@router.get("/attendance")
async def attendance(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("checkin.read")),
    db: AsyncSession = Depends(get_db),
    day: str | None = None,
    event_id: uuid.UUID | None = None,
    q: str | None = None,
) -> dict:
    from sqlalchemy.orm import aliased
    StaffUser = aliased(User)

    stmt = (
        select(AttendanceRecord, User, Event, StaffUser)
        .join(User, AttendanceRecord.user_id == User.id)
        .outerjoin(Event, AttendanceRecord.event_id == Event.id)
        .outerjoin(StaffUser, AttendanceRecord.checked_in_by == StaffUser.id)
        .where(AttendanceRecord.edition_id == edition_id)
    )
    if day:
        stmt = stmt.where(AttendanceRecord.day == day)
    if event_id:
        stmt = stmt.where(AttendanceRecord.event_id == event_id)
    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(User.full_name).like(term),
                func.lower(User.email).like(term),
                func.lower(Event.title).like(term),
            )
        )

    rows = list((await db.execute(stmt.order_by(AttendanceRecord.checked_in_at.desc()).limit(200))).all())
    return {
        "data": [
            {
                "id": str(a.id),
                "participantId": str(u.id),
                "participantName": u.full_name,
                "participantEmail": u.email,
                "eventId": str(e.id) if e else None,
                "eventTitle": e.title if e else "Convention Pass Gate",
                "venueRoom": e.venue_room if e else "Main Entrance",
                "day": a.day,
                "result": a.result,
                "checkedInAt": edition_service.aware(a.checked_in_at).isoformat() if a.checked_in_at else None,
                "checkedInByName": staff.full_name if staff else None,
                "deviceLabel": a.device_label,
            }
            for a, u, e, staff in rows
        ]
    }


@router.get("/events/{event_id}/roster")
async def event_roster(
    edition_id: uuid.UUID,
    event_id: uuid.UUID,
    ctx: AuthContext = Depends(require_any_permission("attendance.read", "checkin.read", "events.read")),
    db: AsyncSession = Depends(get_db),
    status: str | None = None,
    q: str | None = None,
    day: str | None = None,
) -> dict:
    event = await db.get(Event, event_id)
    if event is None or event.edition_id != edition_id:
        raise NotFound("Event not found.")
    await registration_service.lazy_enforce_for_read(db, edition_id=edition_id)

    check_day = day or datetime.now(UTC).strftime("%Y-%m-%d")

    stmt = (
        select(Registration, User)
        .join(User, Registration.user_id == User.id)
        .where(
            Registration.edition_id == edition_id,
            Registration.event_id == event_id,
        )
    )
    if status:
        stmt = stmt.where(Registration.status == status)
    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(User.full_name).like(term),
                func.lower(User.email).like(term),
                func.lower(Registration.registration_number).like(term),
            )
        )

    rows = list((await db.execute(stmt.order_by(Registration.created_at.asc()))).all())

    # Get attendance for this event and day
    att_stmt = select(AttendanceRecord).where(
        AttendanceRecord.edition_id == edition_id,
        AttendanceRecord.event_id == event_id,
        AttendanceRecord.day == check_day,
    )
    att_records = {a.user_id: a for a in (await db.execute(att_stmt)).scalars()}

    # Resolve staff who marked attendance
    staff_ids = {a.checked_in_by for a in att_records.values() if a.checked_in_by}
    staff_map = {}
    if staff_ids:
        staff_users = (
            await db.execute(select(User).where(User.id.in_(staff_ids)))
        ).scalars()
        staff_map = {u.id: u.full_name for u in staff_users}

    # Resolve colleges
    user_ids = [u.id for _, u in rows]
    colleges = {}
    if user_ids:
        college_regs = (
            await db.execute(
                select(CollegeRegistration).where(
                    CollegeRegistration.user_id.in_(user_ids),
                    CollegeRegistration.edition_id == edition_id,
                )
            )
        ).scalars()
        colleges = {c.user_id: (c.college_name, c.phone) for c in college_regs}

    # Resolve teams if team event
    teams = {}
    team_ids = [r.team_id for r, _ in rows if r.team_id]
    if team_ids:
        t_rows = (await db.execute(select(Team).where(Team.id.in_(team_ids)))).scalars()
        teams = {t.id: t for t in t_rows}

    data = []
    for r, u in rows:
        att = att_records.get(u.id)
        col_name, phone = colleges.get(u.id, (None, None))
        team = teams.get(r.team_id) if r.team_id else None
        data.append(
            {
                "registrationId": str(r.id),
                "registrationNumber": r.registration_number,
                "userId": str(u.id),
                "userName": u.full_name,
                "userEmail": u.email,
                "userPhone": phone,
                "userCollege": col_name,
                "teamId": str(r.team_id) if r.team_id else None,
                "teamName": team.name if team else None,
                "isTeamLeader": team.leader_id == u.id if team else False,
                "kind": r.kind,
                "feePaise": r.fee_paise,
                "isIncluded": r.kind == "included" or r.fee_paise == 0,
                "status": r.status,
                "cancelledAt": edition_service.aware(r.cancelled_at).isoformat() if r.cancelled_at else None,
                "cancelledBy": r.cancelled_by,
                "cancellationReason": r.cancellation_reason,
                "attended": att is not None and att.result == "admitted",
                "attendanceId": str(att.id) if att else None,
                "checkedInAt": edition_service.aware(att.checked_in_at).isoformat() if att and att.checked_in_at else None,
                "checkedInByName": staff_map.get(att.checked_in_by) if att and att.checked_in_by else None,
            }
        )

    return {
        "data": {
            "event": {
                "id": str(event.id),
                "title": event.title,
                "format": event.format,
                "venueRoom": event.venue_room,
                "capacity": event.capacity,
                "startsAt": edition_service.aware(event.starts_at).isoformat() if event.starts_at else None,
            },
            "day": check_day,
            "totalRegistered": len(rows),
            "totalAttended": sum(1 for d in data if d["attended"]),
            "roster": data,
        }
    }


@router.post("/attendance/mark")
async def mark_manual_attendance(
    edition_id: uuid.UUID,
    payload: AdminManualAttendancePayload,
    request: Request,
    ctx: AuthContext = Depends(require_any_permission("attendance.write", "checkin.write", "events.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await db.get(User, payload.user_id)
    if user is None:
        raise NotFound("User not found.")

    day = payload.day or datetime.now(UTC).strftime("%Y-%m-%d")

    # If event_id is specified, verify active registration (either direct or team)
    if payload.event_id:
        event = await db.get(Event, payload.event_id)
        if event is None or event.edition_id != edition_id:
            raise NotFound("Event not found.")
        reg = (
            await db.execute(
                select(Registration).where(
                    Registration.user_id == payload.user_id,
                    Registration.edition_id == edition_id,
                    Registration.event_id == payload.event_id,
                    Registration.status.in_(["confirmed", "reserved"]),
                )
            )
        ).scalar_one_or_none()
        if reg is None:
            team_reg = (
                await db.execute(
                    select(Registration)
                    .join(TeamMember, Registration.team_id == TeamMember.team_id)
                    .where(
                        TeamMember.user_id == payload.user_id,
                        TeamMember.status == "active",
                        Registration.edition_id == edition_id,
                        Registration.event_id == payload.event_id,
                        Registration.status.in_(["confirmed", "reserved"]),
                    )
                )
            ).scalar_one_or_none()
            if team_reg is None:
                raise Conflict("User does not have an active confirmed registration for this event.")

    existing = (
        await db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.user_id == payload.user_id,
                AttendanceRecord.edition_id == edition_id,
                AttendanceRecord.day == day,
                (
                    AttendanceRecord.event_id == payload.event_id
                    if payload.event_id is not None
                    else AttendanceRecord.event_id.is_(None)
                ),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {
            "data": {
                "id": str(existing.id),
                "result": "duplicate",
                "participantName": user.full_name,
                "checkedInAt": edition_service.aware(existing.checked_in_at).isoformat(),
                "message": "Already marked present for this day.",
            }
        }

    rec = AttendanceRecord(
        edition_id=edition_id,
        user_id=payload.user_id,
        ticket_id=None,
        event_id=payload.event_id,
        day=day,
        result="admitted",
        checked_in_by=ctx.user.id,
        device_label=payload.note or "admin_manual_roster",
    )
    # Two staff marking the same person at the same moment both miss the check
    # above; the unique constraint then raised a 500 instead of "duplicate".
    # The savepoint keeps the surrounding transaction usable.
    try:
        async with db.begin_nested():
            db.add(rec)
            await db.flush()
    except IntegrityError:
        db.expunge(rec)
        existing = await _attendance_for(
            db, edition_id, payload.user_id, payload.event_id, day
        )
        if existing is None:
            raise
        return {
            "data": {
                "id": str(existing.id),
                "result": "duplicate",
                "participantName": user.full_name,
                "checkedInAt": edition_service.aware(existing.checked_in_at).isoformat(),
                "message": "Already marked present for this day.",
            }
        }
    await record(
        db,
        request,
        action="attendance.marked_manual",
        resource_type="attendance_record",
        resource_id=rec.id,
        actor_id=ctx.user.id,
        actor_role=_role(ctx, edition_id),
        after={
            "user_id": str(user.id),
            "user_name": user.full_name,
            "event_id": str(payload.event_id) if payload.event_id else None,
            "day": day,
        },
    )
    await db.commit()
    return {
        "data": {
            "id": str(rec.id),
            "result": "admitted",
            "participantName": user.full_name,
            "checkedInAt": edition_service.aware(rec.checked_in_at).isoformat(),
        }
    }


@router.delete("/attendance/{attendance_id}")
async def delete_attendance_record(
    edition_id: uuid.UUID,
    attendance_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(require_any_permission("attendance.write", "checkin.write", "events.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rec = await db.get(AttendanceRecord, attendance_id)
    if rec is None or rec.edition_id != edition_id:
        raise NotFound("Attendance record not found.")

    await record(
        db,
        request,
        action="attendance.revoked",
        resource_type="attendance_record",
        resource_id=rec.id,
        actor_id=ctx.user.id,
        actor_role=_role(ctx, edition_id),
        before={
            "user_id": str(rec.user_id),
            "event_id": str(rec.event_id) if rec.event_id else None,
            # Hard-deleting the row loses who admitted the attendee; the audit
            # entry is the only remaining record of it.
            "checked_in_by": str(rec.checked_in_by) if rec.checked_in_by else None,
            "checked_in_at": rec.checked_in_at.isoformat() if rec.checked_in_at else None,
            "day": rec.day,
        },
    )
    await db.delete(rec)
    await db.commit()
    return {"data": {"revoked": True, "id": str(attendance_id)}}


def _attendee_logistics(registration) -> dict:
    """Gender / meal / bed, the three things the door and kitchen ask for."""
    if registration is None:
        return {"gender": None, "foodPreference": None, "needsAccommodation": False}
    return {
        "gender": decode_gender(registration.gender),
        "foodPreference": decode_food(registration.food_preference),
        "needsAccommodation": bool(registration.needs_accommodation),
    }


async def _admit_custom_credential(
    db: AsyncSession,
    request: Request,
    ctx: AuthContext,
    edition_id: uuid.UUID,
    credential,
    day: str | None,
) -> dict:
    """Admit a studio-issued card and hand the desk the holder's logistics."""
    if credential.registration_id is not None:
        from app.models.registration import CollegeRegistration

        reg = await db.get(CollegeRegistration, credential.registration_id)
        if reg is None or reg.edition_id != edition_id:
            raise NotFound("Linked registration was not found in this edition.")
        if reg.payment_status not in ("paid", "completed") or reg.verification_status == "cancelled":
            raise Conflict(
                "This registration has not been paid or has been cancelled. Entry denied.",
                code="PASS_NOT_ACTIVE",
            )
        user = await db.get(User, reg.user_id)
        if user is not None and user.status == "suspended":
            raise Conflict(
                "This participant's account is suspended by the organisers. "
                "Entry denied - please escalate to the convention lead.",
                code="USER_SUSPENDED",
            )

    await record(
        db,
        request,
        actor_id=ctx.user.id,
        actor_role=_role(ctx, edition_id),
        action="custom_credential.checkin",
        resource_type="custom_credential",
        resource_id=str(credential.id),
        after={"code": credential.code, "day": day},
    )
    await db.commit()
    return {
        "data": {
            "result": "admitted",
            "participantName": credential.name,
            "credential": credential_service.public_payload(credential),
            "gender": decode_gender(credential.gender),
            "foodPreference": decode_food(credential.food_preference),
            "needsAccommodation": credential.needs_accommodation,
            "checkedInAt": datetime.now(UTC).isoformat(),
            "message": f"{credential.role} · {credential.code} admitted",
            "team": None,
        }
    }


@router.post("/checkin", dependencies=[Depends(limiter("admin_checkin", 300, 60))])
async def checkin(
    edition_id: uuid.UUID,
    payload: CheckinRequest,
    request: Request,
    ctx: AuthContext = Depends(require_permission("checkin.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.services import tickets as ticket_service

    # Studio cards carry a distinguishable token shape, so a scan of one skips
    # the ticket lookup entirely. Anything else is tried as a ticket first: a
    # hand-typed credential ID has no required prefix, so the fallback stays.
    if credential_service.looks_like_token(payload.token):
        credential = await credential_service.resolve(db, payload.token, edition_id)
        return await _admit_custom_credential(
            db, request, ctx, edition_id, credential, payload.day
        )
    try:
        ticket = await ticket_service.resolve(db, payload.token, edition_id)
    except NotFound:
        # A studio-issued card is not a registration and has no user account.
        # Resolve it separately so scanning one admits the holder instead of
        # failing with "invalid ticket token".
        credential = await credential_service.resolve(db, payload.token, edition_id)
        return await _admit_custom_credential(
            db, request, ctx, edition_id, credential, payload.day
        )
    user = await db.get(User, ticket.user_id)
    # A suspended account must not scan green anywhere: the desk needs to know
    # the suspension (not a ticket problem) is why entry is denied.
    if user is not None and user.status == "suspended":
        raise Conflict(
            "This participant's account is suspended by the organisers. "
            "Entry denied - please escalate to the convention lead.",
            code="USER_SUSPENDED",
        )
    if ticket.pass_id:
        from app.models.commerce import ConventionPass
        pass_obj = await db.get(ConventionPass, ticket.pass_id)
        if pass_obj is not None and pass_obj.status == "suspended":
            raise Conflict(
                "This participant's convention pass has been suspended by the organisers. Entry denied.",
                code="PASS_BLOCKED",
            )
    from app.models.registration import CollegeRegistration
    col_reg = (
        await db.execute(
            select(CollegeRegistration).where(
                CollegeRegistration.user_id == ticket.user_id,
                CollegeRegistration.edition_id == edition_id,
            )
        )
    ).scalar_one_or_none()
    if col_reg is not None and col_reg.category_change_status == "awaiting_payment":
        raise Conflict(
            "This participant has an unpaid category upgrade balance. "
            "Please clear the differential payment at the registration desk before entry.",
            code="PAYMENT_DUE",
        )
    day = payload.day or datetime.now(UTC).strftime("%Y-%m-%d")

    event_id = payload.event_id
    team_info = None
    if ticket.registration_id:
        registration = await db.get(Registration, ticket.registration_id)
        if registration is None or registration.status not in ("confirmed", "reserved"):
            raise Conflict("This registration is no longer valid.")
        if event_id and event_id != registration.event_id:
            raise Conflict("This ticket belongs to a different event.")
        event_id = registration.event_id
        if registration.team_id:
            team_obj = await db.get(Team, registration.team_id)
            if team_obj:
                team_info = {
                    "teamId": str(team_obj.id),
                    "teamName": team_obj.name,
                    "isLeader": team_obj.leader_id == ticket.user_id,
                }
    elif event_id:
        linked_reg = (
            await db.execute(
                select(Registration).where(
                    Registration.user_id == ticket.user_id,
                    Registration.edition_id == edition_id,
                    Registration.event_id == event_id,
                    Registration.status.in_(["confirmed", "reserved"]),
                )
            )
        ).scalar_one_or_none()
        if linked_reg is None:
            # Check team registration
            team_reg_row = (
                await db.execute(
                    select(Registration, Team, TeamMember)
                    .join(Team, Registration.team_id == Team.id)
                    .join(TeamMember, Team.id == TeamMember.team_id)
                    .where(
                        TeamMember.user_id == ticket.user_id,
                        TeamMember.status == "active",
                        Registration.edition_id == edition_id,
                        Registration.event_id == event_id,
                        Registration.status.in_(["confirmed", "reserved"]),
                    )
                )
            ).first()
            if team_reg_row is None:
                raise Conflict("This participant is not registered for that event.")
            _, t_obj, tm_obj = team_reg_row
            team_info = {
                "teamId": str(t_obj.id),
                "teamName": t_obj.name,
                "isLeader": tm_obj.is_leader,
            }
        elif linked_reg.team_id:
            t_obj = await db.get(Team, linked_reg.team_id)
            if t_obj:
                team_info = {
                    "teamId": str(t_obj.id),
                    "teamName": t_obj.name,
                    "isLeader": t_obj.leader_id == ticket.user_id,
                }

    existing_row = await _attendance_for(db, edition_id, ticket.user_id, event_id, day)
    if existing_row is not None:
        repeat_logistics = _attendee_logistics(col_reg)
        return {
            "data": {
                "result": "duplicate",
                "participantName": user.full_name if user else "Participant",
                "checkedInAt": edition_service.aware(existing_row.checked_in_at).isoformat(),
                "message": "Already checked in for this day.",
                "gender": repeat_logistics["gender"],
                "foodPreference": repeat_logistics["foodPreference"],
                "needsAccommodation": repeat_logistics["needsAccommodation"],
                "team": team_info,
            }
        }
    rec = AttendanceRecord(
        edition_id=edition_id,
        user_id=ticket.user_id,
        ticket_id=ticket.id,
        event_id=event_id,
        day=day,
        result="admitted",
        checked_in_by=ctx.user.id,
        device_label=payload.device_label,
    )
    # Two scanners on the same ticket used to race between the SELECT above and
    # this INSERT: the loser raised a unique violation and the desk saw a 500.
    # The savepoint turns that race into the "already checked in" answer.
    try:
        async with db.begin_nested():
            db.add(rec)
            await db.flush()
    except IntegrityError:
        db.expunge(rec)
        existing_row = await _attendance_for(db, edition_id, ticket.user_id, event_id, day)
        if existing_row is None:
            raise
        return {
            "data": {
                "result": "duplicate",
                "participantName": user.full_name if user else "Participant",
                "checkedInAt": edition_service.aware(existing_row.checked_in_at).isoformat(),
                "message": "Already checked in for this day.",
                "team": team_info,
            }
        }
    await db.commit()

    college_reg = (
        await db.execute(
            select(CollegeRegistration).where(
                CollegeRegistration.user_id == ticket.user_id,
                CollegeRegistration.edition_id == edition_id,
            )
        )
    ).scalars().first()
    is_verified = college_reg.verification_status == "approved" if college_reg else True
    logistics = _attendee_logistics(college_reg)
    warning = (
        "UNVERIFIED ATTENDEE: Check physical college ID on the spot."
        if (college_reg and college_reg.verification_status != "approved")
        else None
    )

    return {
        "data": {
            "result": "admitted",
            "participantName": user.full_name if user else "Participant",
            "checkedInAt": datetime.now(UTC).isoformat(),
            "isVerified": is_verified,
            "verificationStatus": college_reg.verification_status if college_reg else "approved",
            "warning": warning,
            "gender": logistics["gender"],
            "foodPreference": logistics["foodPreference"],
            "needsAccommodation": logistics["needsAccommodation"],
            "team": team_info,
            "eventId": str(event_id) if event_id else None,
        }
    }


@router.get("/recent-checkins")
async def recent_checkins(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("checkin.read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = list(
        (
            await db.execute(
                select(AttendanceRecord, User)
                .join(User, AttendanceRecord.user_id == User.id)
                .where(AttendanceRecord.edition_id == edition_id)
                .order_by(AttendanceRecord.checked_in_at.desc())
                .limit(20)
            )
        ).all()
    )
    return {
        "data": [
            {
                "id": str(a.id),
                "participantName": u.full_name,
                "result": a.result,
                "checkedInAt": edition_service.aware(a.checked_in_at).isoformat() if a.checked_in_at else None,
            }
            for a, u in rows
        ]
    }


@router.post("/db-playground/seed")
async def db_playground_seed(
    edition_id: uuid.UUID,
    payload: DbPlaygroundSeedPayload,
    request: Request,
    ctx: AuthContext = Depends(require_min_role("super_admin", "edition_admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """DB Playground: Emergency verified override and manual seed for stuck attendee payments/registrations.

    Restricted strictly to super_admin and edition_admin. All actions are logged to
    the immutable audit table and immediately broadcast to the organizer Telegram channel.

    This is a development escape hatch: it does not exist in production, and when
    MFA is enforced it is a step-up action.
    """
    from app.core.config import get_settings

    settings = get_settings()
    # The gate is about "no real money can be taken here", not about the name of
    # the environment: a staging deploy that runs with live gateway keys must
    # not let an edition_admin hand out paid passes for free.
    if not settings.is_development or settings.payments_enabled:
        raise NotFound("Not found.")
    if settings.mfa_enforced and ctx.is_staff and not ctx.step_up_fresh:
        raise StepUpRequired("Confirm your authenticator code to continue.")

    from app.services.telegram import send_telegram_alert
    from app.services.passes import activate_pass_for_registration
    from app.services.tickets import issue_for_registration, issue_for_pass
    from app.services.college_registrations import _unique_registration_number

    # 1. Resolve user by ID or email
    user_query = payload.user_email_or_id.strip()
    target_user: User | None = None
    try:
        potential_uuid = uuid.UUID(user_query)
        target_user = await db.get(User, potential_uuid)
    except ValueError:
        pass

    if target_user is None:
        target_user = (
            await db.execute(select(User).where(User.email.ilike(user_query)))
        ).scalars().first()

    if target_user is None:
        raise NotFound(f"User not found matching '{user_query}'")

    edition = await db.get(ConventionEdition, edition_id)
    if edition is None:
        raise NotFound("Convention edition not found.")

    policy = (
        await db.execute(
            select(EditionPolicy).where(EditionPolicy.edition_id == edition_id)
        )
    ).scalars().first()
    if policy is None:
        raise NotFound("Edition policy not configured.")

    results: dict[str, object] = {
        "userId": str(target_user.id),
        "userEmail": target_user.email,
        "userName": target_user.full_name,
        "actions": [],
    }

    audit_details: dict[str, object] = {
        "reason": payload.reason,
        "operator": ctx.user.email,
        "targetUser": target_user.email,
        "target": payload.target,
        "paymentReference": payload.payment_reference,
    }

    # 2. Update CollegeRegistration if exists and requested
    college_reg = (
        await db.execute(
            select(CollegeRegistration)
            .where(
                CollegeRegistration.user_id == target_user.id,
                CollegeRegistration.edition_id == edition_id,
            )
            .order_by(CollegeRegistration.created_at.desc())
        )
    ).scalars().first()

    if college_reg:
        if payload.mark_college_reg_approved:
            # An approval through this override left a pending category change
            # claiming a different category, so the desk saw two answers for the
            # same registration.
            from app.services.college_registrations import (
                _cancel_outstanding_category_change,
            )

            await _cancel_outstanding_category_change(
                db,
                college_reg,
                reason="Cancelled by the DB playground approval override.",
            )
            college_reg.payment_status = "paid"
            college_reg.verification_status = "approved"
            college_reg.paid_at = college_reg.paid_at or datetime.now(UTC)
            college_reg.decided_at = datetime.now(UTC)
            college_reg.decided_by = ctx.user.id
            if payload.payment_reference and not college_reg.transaction_id:
                college_reg.transaction_id = payload.payment_reference
            results["collegeRegistration"] = {
                "id": str(college_reg.id),
                "paymentStatus": college_reg.payment_status,
                "verificationStatus": college_reg.verification_status,
            }
            results["actions"].append("Updated CollegeRegistration to paid/approved")

    # 3. Seed convention pass if requested
    if payload.target in ("pass", "both"):
        pass_obj = await activate_pass_for_registration(
            db,
            user_id=target_user.id,
            edition_id=edition_id,
            policy=policy,
            price_paise=policy.pass_price_paise,
        )
        pass_ticket = await issue_for_pass(db, pass_obj)
        results["pass"] = {
            "id": str(pass_obj.id),
            "status": pass_obj.status,
            "ticketId": str(pass_ticket.id) if pass_ticket else None,
        }
        results["actions"].append("Seeded & Activated Convention Pass + Entry Ticket")

    # 4. Seed event registrations if requested
    if payload.target in ("event", "both") and payload.event_ids:
        seeded_events = []
        for eid in payload.event_ids:
            event = await db.get(Event, eid)
            if not event or event.edition_id != edition_id:
                continue

            existing_reg = (
                await db.execute(
                    select(Registration).where(
                        Registration.user_id == target_user.id,
                        Registration.event_id == eid,
                    )
                )
            ).scalars().first()

            if existing_reg is None:
                # This path used to write a seat with no capacity check and a
                # synthetic number, so an override could overbook an event and
                # leave a registration the desk could not look up.
                from app.services.registrations import _assert_capacity

                if event.status in ("cancelled", "closed", "draft"):
                    seeded_events.append(
                        {"eventId": str(eid), "title": event.title, "action": "skipped_closed_event"}
                    )
                    continue
                try:
                    await _assert_capacity(db, event)
                except Exception as exc:  # noqa: BLE001 - reported per event
                    seeded_events.append(
                        {
                            "eventId": str(eid),
                            "title": event.title,
                            "action": "skipped_capacity",
                            "detail": getattr(exc, "message", str(exc))[:120],
                        }
                    )
                    continue
                new_reg = Registration(
                    edition_id=edition_id,
                    event_id=eid,
                    user_id=target_user.id,
                    fee_paise=0,
                    status="confirmed",
                    registration_number=await _unique_registration_number(db),
                )
                db.add(new_reg)
                await db.flush()
                await issue_for_registration(db, new_reg)
                seeded_events.append({"eventId": str(eid), "title": event.title, "action": "created"})
            else:
                if event.status in ("cancelled", "closed", "draft"):
                    seeded_events.append(
                        {"eventId": str(eid), "title": event.title, "action": "skipped_closed_event"}
                    )
                    continue
                existing_reg.status = "confirmed"
                existing_reg.cancelled_at = None
                existing_reg.cancelled_by = None
                existing_reg.cancellation_reason = None
                await issue_for_registration(db, existing_reg)
                seeded_events.append({"eventId": str(eid), "title": event.title, "action": "confirmed"})

        results["events"] = seeded_events
        results["actions"].append(f"Seeded {len(seeded_events)} Event Registration(s)")

    await record(
        db,
        request,
        actor_id=ctx.user.id,
        actor_role=ctx.role_for(edition_id),
        action="db_playground_seed",
        resource_type="attendee_recovery",
        resource_id=str(target_user.id),
        before=None,
        after=audit_details,
    )

    await db.commit()

    # 5. Broadcast to Telegram immediately with error handling
    try:
        from app.services.telegram import track_telegram_task

        track_telegram_task(
            send_telegram_alert(
                title="🛠️ DB Playground Manual Recovery",
                fields={
                    "Operator": f"{ctx.user.email} ({ctx.role_for(edition_id)})",
                    "Target Attendee": f"{target_user.full_name} ({target_user.email})",
                    "Actions": ", ".join(results["actions"]),
                    "Reason": payload.reason,
                    "Payment Ref": payload.payment_reference or "N/A",
                },
                severity="warning",
                footer="Audit logged in DB Playground",
            ),
            name="parallax-db-playground-alert",
        )
    except Exception as exc:
        logger.error("db_playground_telegram_alert_failed", error=str(exc), exc_info=True)

    return {"data": results}


@router.get("/teams")
async def list_teams(
    edition_id: uuid.UUID,
    status: str | None = None,
    ctx: AuthContext = Depends(require_permission("team.read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.models.user import ParticipantProfile
    stmt = (
        select(Team, Event, User)
        .join(Event, Team.event_id == Event.id)
        .join(User, Team.leader_id == User.id)
        .where(Team.edition_id == edition_id)
        .order_by(Team.created_at.desc())
    )
    if status:
        stmt = stmt.where(Team.status == status)
    rows = list((await db.execute(stmt)).all())
    team_ids = [t.id for t, _, _ in rows]
    members_by_team: dict[uuid.UUID, list[dict]] = {}
    seats_by_team: dict[uuid.UUID, list[dict]] = {}
    order_status: dict[uuid.UUID, str] = {}
    if team_ids:
        mem_rows = list(
            (
                await db.execute(
                    select(TeamMember, User, ParticipantProfile)
                    .join(User, TeamMember.user_id == User.id)
                    .outerjoin(ParticipantProfile, ParticipantProfile.user_id == User.id)
                    .where(TeamMember.team_id.in_(team_ids))
                    .order_by(TeamMember.is_leader.desc(), TeamMember.joined_at.asc())
                )
            ).all()
        )
        for mem, u, prof in mem_rows:
            members_by_team.setdefault(mem.team_id, []).append(
                {
                    "userId": str(u.id),
                    "fullName": u.full_name,
                    "email": u.email,
                    "collegeName": prof.college_name if prof else None,
                    "isLeader": mem.is_leader,
                }
            )
        seat_rows = list(
            (
                await db.execute(
                    select(
                        Registration.team_id,
                        Registration.user_id,
                        Registration.status,
                        Registration.fee_paise,
                        Registration.order_id,
                    ).where(Registration.team_id.in_(team_ids))
                )
            ).all()
        )
        order_ids = [row.order_id for row in seat_rows if row.order_id is not None]
        team_order_ids = [t.order_id for t, _, _ in rows if t.order_id is not None]
        if order_ids or team_order_ids:
            for order in (
                await db.execute(
                    select(PaymentOrder).where(
                        PaymentOrder.id.in_(order_ids + team_order_ids)
                    )
                )
            ).scalars():
                order_status[order.id] = order.status
        for seat in seat_rows:
            seats_by_team.setdefault(seat.team_id, []).append(
                {
                    "userId": str(seat.user_id),
                    "status": seat.status,
                    "feePaise": int(seat.fee_paise or 0),
                    "orderStatus": order_status.get(seat.order_id)
                    if seat.order_id
                    else None,
                }
            )
        seat_status = {
            (team_id, seat["userId"]): seat["status"]
            for team_id, seats in seats_by_team.items()
            for seat in seats
        }
        for team_id, members in members_by_team.items():
            for member in members:
                member["seatStatus"] = seat_status.get((team_id, member["userId"]))

    from app.services.teams import team_fee_basis, team_seat_price

    policy = await edition_service.current_policy(db, edition_id)

    def _payment_status(team: Team) -> str:
        if team.order_id is not None:
            return "paid" if order_status.get(team.order_id) == "paid" else "pending"
        seats = seats_by_team.get(team.id, [])
        if not seats:
            return "none"
        if any(s["status"] == "reserved" for s in seats):
            return "pending"
        if any((s["feePaise"] or 0) > 0 or s["orderStatus"] == "paid" for s in seats):
            return "paid"
        return "free"

    return {
        "data": [
            {
                "id": str(t.id),
                "name": t.name,
                "eventId": str(e.id),
                "eventTitle": e.title,
                "status": t.status,
                "formationState": t.formation_state,
                "inviteCode": t.invite_code,
                "maxSize": e.team_max_size,
                "minSize": e.team_min_size,
                "feeBasis": team_fee_basis(e, policy),
                "feePaise": team_seat_price(e, policy),
                "paymentStatus": _payment_status(t),
                "seats": seats_by_team.get(t.id, []),
                "leaderId": str(leader.id),
                "leaderName": leader.full_name,
                "leaderEmail": leader.email,
                "members": members_by_team.get(t.id, []),
                "createdAt": t.created_at.isoformat() if t.created_at else None,
            }
            for t, e, leader in rows
        ]
    }


@router.post("/teams/{team_id}/lock")
async def admin_toggle_team_lock(
    edition_id: uuid.UUID,
    team_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(require_permission("team.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    team = await db.get(Team, team_id)
    if team is None or team.edition_id != edition_id:
        raise NotFound("Team not found.")
    if team.status == "disbanded":
        raise Conflict("A disbanded team cannot be locked or unlocked.")
    prev = team.status
    team.status = "active" if team.status == "locked" else "locked"
    await record(
        db,
        request,
        actor_id=ctx.user.id,
        actor_role=ctx.role_for(edition_id),
        action="team.admin_lock_toggle",
        resource_type="team",
        resource_id=str(team.id),
        before={"status": prev},
        after={"status": team.status},
    )
    await db.commit()
    return {"data": {"id": str(team.id), "status": team.status}}


@router.delete("/teams/{team_id}")
async def admin_disband_team(
    edition_id: uuid.UUID,
    team_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(require_permission("team.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.services.teams import disband_team

    team = await db.get(Team, team_id)
    if team is None or team.edition_id != edition_id:
        raise NotFound("Team not found.")
    if team.status == "disbanded":
        return {"data": {"id": str(team.id), "status": "disbanded", "cancelledSeats": 0}}
    cancelled = await disband_team(db, team, reason="Team disbanded by administration")
    await record(
        db,
        request,
        actor_id=ctx.user.id,
        actor_role=ctx.role_for(edition_id),
        action="team.admin_disband",
        resource_type="team",
        resource_id=str(team.id),
        before={"status": "active"},
        after={"status": "disbanded", "cancelledSeats": cancelled},
    )
    await db.commit()
    return {"data": {"id": str(team.id), "status": "disbanded", "cancelledSeats": cancelled}}


__all__ = ["router"]
