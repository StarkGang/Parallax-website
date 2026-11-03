"""Administrative operations: catalogue, pricing, policy changes, verification decisions and staff access."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_permission
from app.core.errors import NotFound, ValidationFailed
from app.core.permissions import permissions_for
from app.db.session import get_db
from app.models.commerce import (
    AttendanceRecord,
    AuditLog,
    PaymentOrder,
    Refund,
    Registration,
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
from app.models.user import EditionMembership, User
from app.schemas.admin import (
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
    data = await file.read()
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
    page: int = 1,
    page_size: int = 50,
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


@router.post("/memberships")
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


@router.post("/staff-invites")
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
    page: int = 1,
    page_size: int = 50,
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


@router.post("/refunds")
async def create_refund(
    edition_id: uuid.UUID,
    payload: RefundCreate,
    request: Request,
    ctx: AuthContext = Depends(require_permission("finance.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    order = await payment_service.order_for(db, payload.order_id)
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


@router.post("/verifications/{verification_id}/decide")
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
) -> dict:
    stmt = (
        select(Registration, User, Event)
        .join(User, Registration.user_id == User.id)
        .join(Event, Registration.event_id == Event.id)
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
    rows = list((await db.execute(stmt.order_by(Registration.created_at.desc()).limit(100))).all())
    return {
        "data": [
            {
                "id": str(r.id),
                "registrationNumber": r.registration_number,
                "userName": u.full_name,
                "userEmail": u.email,
                "eventTitle": e.title,
                "kind": r.kind,
                "feePaise": r.fee_paise,
                "status": r.status,
                "createdAt": edition_service.aware(r.created_at).isoformat() if r.created_at else None,
            }
            for r, u, e in rows
        ]
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
    page: int = 1,
    page_size: int = 50,
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
) -> dict:
    stmt = (
        select(AttendanceRecord, User)
        .join(User, AttendanceRecord.user_id == User.id)
        .where(AttendanceRecord.edition_id == edition_id)
    )
    if day:
        stmt = stmt.where(AttendanceRecord.day == day)
    rows = list((await db.execute(stmt.order_by(AttendanceRecord.checked_in_at.desc()).limit(100))).all())
    return {
        "data": [
            {
                "id": str(a.id),
                "participantName": u.full_name,
                "day": a.day,
                "result": a.result,
                "checkedInAt": edition_service.aware(a.checked_in_at).isoformat() if a.checked_in_at else None,
            }
            for a, u in rows
        ]
    }


@router.post("/checkin")
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
    existing = (
        await db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.user_id == ticket.user_id,
                AttendanceRecord.event_id == payload.event_id,
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
            }
        }
    rec = AttendanceRecord(
        edition_id=edition_id,
        user_id=ticket.user_id,
        ticket_id=ticket.id,
        event_id=payload.event_id,
        day=day,
        result="admitted",
        checked_in_by=ctx.user.id,
        device_label=payload.device_label,
    )
    db.add(rec)
    await db.flush()
    await db.commit()
    return {
        "data": {
            "result": "admitted",
            "participantName": user.full_name if user else "Participant",
            "checkedInAt": datetime.now(UTC).isoformat(),
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
