"""Administrative operations: catalogue, pricing, policy changes, verification decisions and staff access."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_permission, require_any_permission
from app.integrations.storage import get_storage
from app.core.cache import cache_delete_pattern
from app.core.errors import AppError
from app.core.errors import Conflict, NotFound, ValidationFailed
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
    Ticket,
)
from app.models.edition import (
    ConventionEdition,
    EditionPolicy,
    EligibilityVerification,
    Event,
    EventCategory,
    Icon,
)
from app.models.registration import CollegeRegistration
from app.models.user import EditionMembership, User
from app.schemas.admin import (
    AdminForceCancelPayload,
    AdminManualAttendancePayload,
    AdminProcessRefundPayload,
    AnnouncementUpsert,
    CategoryUpsert,
    CheckinRequest,
    CheckinResponse,
    EditionUpdate,
    EventUpsert,
    MembershipGrant,
    PolicyUpdate,
    RefundCreate,
    UserStatusUpdate,
    VerificationDecision,
)
from app.services.audit import record
from app.services.tickets import revoke_for_registration
from app.services import (
    announcements as announcement_service,
    editions as edition_service,
    events as event_service,
    icons as icon_service,
    payments as payment_service,
    users as user_service,
    verification as verif_service,
)

router = APIRouter(prefix="/editions/{edition_id}/admin", tags=["admin"])


def _role(ctx: AuthContext, edition_id: uuid.UUID) -> str:
    return ctx.role_for(edition_id) or (ctx.roles[0] if ctx.roles else "super_admin")


@router.get("/overview")
async def overview(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("stats.read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stats = await edition_service.dashboard(db, edition_id)
    return {"data": stats.model_dump(by_alias=True)}


@router.post("/sync")
async def sync_data(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("stats.read")),
) -> dict:
    from app.core.cache import cache_clear
    cache_clear()
    return {"data": {"synced": True, "timestamp": datetime.now(UTC).isoformat()}}


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
            "allowedEmailDomains": edition.allowed_email_domains or [],
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

    for k, v in data.items():
        if hasattr(edition, k):
            setattr(edition, k, v)
    await db.flush()
    await db.commit()
    return {"data": {"updated": True}}


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
    ctx: AuthContext = Depends(require_permission("events.write")),
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

    # Trust the bytes, not the filename or the client-declared Content-Type: this
    # lands in a public bucket and must never hold arbitrary content.
    if data.startswith(b"\xff\xd8\xff"):
        ext, content_type = "jpg", "image/jpeg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
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
    ctx: AuthContext = Depends(require_permission("events.write")),
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
    ctx: AuthContext = Depends(require_permission("events.write")),
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
        db, edition_id, q=q, page=page, page_size=page_size
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


@router.post("/users/{user_id}/reset-mfa")
async def reset_mfa(
    edition_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(require_permission("users.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # MFA is optional / disabled, reset confirms cleanly
    await db.commit()
    return {"data": {"reset": True}}


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
    m = await user_service.grant_membership(
        db,
        request,
        email=payload.email,
        role=payload.role,
        edition_id=edition_id,
        actor_id=ctx.user.id,
        actor_role=_role(ctx, edition_id),
    )
    await db.commit()
    return {"data": {"granted": True, "role": m.role}}


@router.post("/staff-invites", dependencies=[Depends(limiter("admin_staff_invite", 30, 60))])
async def invite_staff(
    edition_id: uuid.UUID,
    payload: MembershipGrant,
    request: Request,
    ctx: AuthContext = Depends(require_permission("staff.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    inv = await user_service.invite_staff(
        db,
        request,
        email=payload.email,
        role=payload.role,
        edition_id=edition_id,
        actor_id=ctx.user.id,
        actor_role=_role(ctx, edition_id),
    )
    await db.commit()
    return {"data": {"invited": True, "email": inv.email}}


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


@router.get("/verifications")
async def verifications(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("verification.review")),
    db: AsyncSession = Depends(get_db),
    status: str | None = None,
) -> dict:
    stmt = (
        select(EligibilityVerification, User)
        .join(User, EligibilityVerification.user_id == User.id)
        .where(EligibilityVerification.edition_id == edition_id)
    )
    if status:
        stmt = stmt.where(EligibilityVerification.status == status)
    rows = list((await db.execute(stmt.order_by(EligibilityVerification.created_at.desc()))).all())
    return {
        "data": [
            {
                "id": str(v.id),
                "userId": str(u.id),
                "fullName": u.full_name,
                "email": u.email,
                "method": v.method,
                "status": v.status,
                "documentName": v.document_name,
                "submittedAt": edition_service.aware(v.created_at).isoformat() if v.created_at else None,
                "reviewedAt": edition_service.aware(v.reviewed_at).isoformat() if v.reviewed_at else None,
                "rejectionReason": v.rejection_reason,
            }
            for v, u in rows
        ]
    }


@router.get("/verifications/{verification_id}/document")
async def verification_document(
    edition_id: uuid.UUID,
    verification_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("verification.review")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    v = await db.get(EligibilityVerification, verification_id)
    if v is None or v.edition_id != edition_id:
        raise NotFound("Verification not found.")
    url = await verif_service.signed_document_url(v)
    return {"data": {"url": url}}


@router.post(
    "/verifications/{verification_id}/decide",
    dependencies=[Depends(limiter("admin_verification_decision", 120, 60))],
)
async def decide_verification(
    edition_id: uuid.UUID,
    verification_id: uuid.UUID,
    payload: VerificationDecision,
    request: Request,
    ctx: AuthContext = Depends(require_permission("verification.review")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    v = await db.get(EligibilityVerification, verification_id)
    if v is None or v.edition_id != edition_id:
        raise NotFound("Verification not found.")
    await verif_service.review(
        db,
        request,
        v,
        decision=payload.decision,
        reason=payload.reason,
        actor_id=ctx.user.id,
        actor_role=_role(ctx, edition_id),
    )
    await db.commit()
    return {"data": {"status": v.status}}


@router.get("/registrations")
async def registrations(
    edition_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("events.read")),
    db: AsyncSession = Depends(get_db),
    event_id: uuid.UUID | None = None,
    status: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
) -> dict:
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
                "userEmail": u.email,
                "userPhone": col.phone if col else None,
                "userCollege": col.college_name if col else None,
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
                "canCancel": r.status in ("confirmed", "reserved"),
            }
        )

    return {
        "data": data,
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


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
    reg.status = "cancelled"
    reg.cancelled_at = datetime.now(UTC)
    reg.cancelled_by = "admin"
    reg.cancellation_reason = payload.reason or "Removed from event by administration"
    await revoke_for_registration(db, reg.id)

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
                select(AuditLog)
                .order_by(AuditLog.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars()
    )
    return {
        "data": [
            {
                "id": str(r.id),
                "actorId": str(r.actor_id) if r.actor_id else None,
                "actorRole": r.actor_role,
                "action": r.action,
                "resourceType": r.resource_type,
                "resourceId": r.resource_id,
                "before": r.before,
                "after": r.after,
                "createdAt": edition_service.aware(r.created_at).isoformat() if r.created_at else None,
            }
            for r in rows
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
                AttendanceRecord.event_id == payload.event_id,
                AttendanceRecord.day == day,
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
    db.add(rec)
    await db.flush()
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
        before={"user_id": str(rec.user_id), "event_id": str(rec.event_id) if rec.event_id else None},
    )
    await db.delete(rec)
    await db.commit()
    return {"data": {"revoked": True, "id": str(attendance_id)}}


@router.post("/checkin", dependencies=[Depends(limiter("admin_checkin", 300, 60))])
async def checkin(
    edition_id: uuid.UUID,
    payload: CheckinRequest,
    request: Request,
    ctx: AuthContext = Depends(require_permission("checkin.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.services import tickets as ticket_service

    ticket = await ticket_service.resolve(db, payload.token, edition_id)
    user = await db.get(User, ticket.user_id)
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

    existing = (
        await db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.user_id == ticket.user_id,
                AttendanceRecord.event_id == event_id,
                AttendanceRecord.day == day,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {
            "data": {
                "result": "duplicate",
                "participantName": user.full_name if user else "Participant",
                "checkedInAt": edition_service.aware(existing.checked_in_at).isoformat(),
                "message": "Already checked in for this day.",
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
    db.add(rec)
    await db.flush()
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


__all__ = ["router"]
