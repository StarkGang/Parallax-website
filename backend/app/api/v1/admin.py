"""Administrative operations: catalogue, pricing, policy changes, verification decisions and staff access."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_permission
from app.integrations.storage import get_storage
from app.core.errors import AppError, Forbidden
from app.core.errors import Conflict, NotFound, ValidationFailed
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
from app.models.user import ParticipantProfile, ProfileChoice, Session
from app.schemas.admin import (
    AnnouncementUpsert,
    CategoryUpsert,
    CheckinRequest,
    CheckinResponse,
    EditionUpdate,
    EventUpsert,
    MembershipGrant,
    PolicyUpdate,
    ProfileChoiceMerge,
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
    from app.services.system_settings import all_settings

    system = await all_settings(db)
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
            "registrationUnlockAt": system["registration_unlock_at"],
            "registrationPrices": {
                "isteMemberPaise": system["isteMemberPaise"],
                "nonIstePaise": system["nonIstePaise"],
                "polytechnicPaise": system["polytechnicPaise"],
            },
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
    unlock_at = data.pop("registration_unlock_at", None)
    prices = {
        "registration_price_iste_member_paise": data.pop("registration_price_iste_member_paise", None),
        "registration_price_non_iste_paise": data.pop("registration_price_non_iste_paise", None),
        "registration_price_polytechnic_paise": data.pop("registration_price_polytechnic_paise", None),
    }
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
    system_values = {}
    if unlock_at is not None:
        from zoneinfo import ZoneInfo

        if unlock_at.tzinfo is None:
            unlock_at = unlock_at.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        system_values["registration_unlock_at"] = unlock_at.astimezone(UTC).isoformat()
    price_key_map = {
        "registration_price_iste_member_paise": "isteMemberPaise",
        "registration_price_non_iste_paise": "nonIstePaise",
        "registration_price_polytechnic_paise": "polytechnicPaise",
    }
    system_values.update({price_key_map[k]: v for k, v in prices.items() if v is not None})
    if system_values:
        from app.services.system_settings import update_settings as update_system_settings

        await update_system_settings(db, system_values, ctx.user.id)
        from app.core.cache import cache_clear

        cache_clear()
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
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise AppError("Banner image must be 10 MB or smaller.", code="FILE_TOO_LARGE", status_code=413)

    ext = (file.filename or "").split(".")[-1].lower() if "." in (file.filename or "") else "jpg"
    if ext not in ("jpg", "jpeg", "png", "webp", "avif"):
        ext = "jpg"
    content_type = file.content_type or f"image/{ext}"

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


@router.get("/profile-choices")
async def profile_choices(
    edition_id: uuid.UUID,
    kind: str | None = Query(default=None, pattern="^(branch|college)$"),
    ctx: AuthContext = Depends(require_permission("users.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stmt = select(ProfileChoice).order_by(ProfileChoice.kind, ProfileChoice.name)
    if kind:
        stmt = stmt.where(ProfileChoice.kind == kind)
    rows = list((await db.scalars(stmt)).all())
    return {"data": [{"id": str(row.id), "kind": row.kind, "name": row.name} for row in rows]}


@router.post("/profile-choices/{choice_id}/merge")
async def merge_profile_choice(
    edition_id: uuid.UUID,
    choice_id: uuid.UUID,
    payload: ProfileChoiceMerge,
    request: Request,
    ctx: AuthContext = Depends(require_permission("users.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    source = await db.get(ProfileChoice, choice_id)
    target = await db.get(ProfileChoice, payload.target_id)
    if not source or not target or source.id == target.id or source.kind != target.kind:
        raise NotFound("Compatible profile choices not found.")
    attr = "branch" if source.kind == "branch" else "college_name"
    await db.execute(
        update(ParticipantProfile).where(getattr(ParticipantProfile, attr) == source.name).values({attr: target.name})
    )
    await db.delete(source)
    await db.commit()
    return {"data": {"merged": True}}


@router.delete("/profile-choices/{choice_id}")
async def delete_profile_choice(
    edition_id: uuid.UUID,
    choice_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("users.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    source = await db.get(ProfileChoice, choice_id)
    if not source:
        raise NotFound("Profile choice not found.")
    attr = "branch" if source.kind == "branch" else "college_name"
    in_use = await db.scalar(select(ParticipantProfile.user_id).where(getattr(ParticipantProfile, attr) == source.name).limit(1))
    if in_use:
        raise Conflict("This choice is in use. Merge it into another choice first.")
    await db.delete(source)
    await db.commit()
    return {"data": {"deleted": True}}


@router.get("/users/{user_id}/profile-documents/{kind}")
async def profile_document(
    edition_id: uuid.UUID,
    user_id: uuid.UUID,
    kind: str,
    ctx: AuthContext = Depends(require_permission("verification.review")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    if kind not in {"college_id", "iste_proof"}:
        raise NotFound("Profile document not found.")
    verified_scope = await db.scalar(
        select(EligibilityVerification.id).where(
            EligibilityVerification.edition_id == edition_id,
            EligibilityVerification.user_id == user_id,
        )
    )
    profile = await db.scalar(
        select(ParticipantProfile).where(ParticipantProfile.user_id == user_id)
    )
    key = getattr(profile, f"{kind}_document_key", None) if profile else None
    if not verified_scope or not key:
        raise NotFound("Profile document not found.")
    data = await get_storage().get(key)
    mime_type = "application/pdf" if data.startswith(b"%PDF-") else "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        mime_type = "image/png"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        mime_type = "image/webp"
    return Response(
        data,
        media_type=mime_type,
        headers={"Content-Disposition": "inline", "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/users/{user_id}/fulfill-deletion")
async def fulfill_deletion_request(
    edition_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(require_permission("users.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await db.get(User, user_id)
    if user is None or user.status != "deletion_requested":
        raise NotFound("Deletion request not found.")
    in_edition = await db.scalar(
        select(EditionMembership.id).where(
            EditionMembership.edition_id == edition_id,
            EditionMembership.user_id == user_id,
        )
    )
    if not in_edition:
        raise NotFound("Deletion request not found.")
    profile = await db.scalar(select(ParticipantProfile).where(ParticipantProfile.user_id == user_id))
    storage = get_storage()
    if profile:
        for attr in ("college_id_document_key", "iste_proof_document_key"):
            key = getattr(profile, attr)
            if key:
                await storage.delete(key)
                setattr(profile, attr, None)
        await db.delete(profile)
    verifications = list((await db.scalars(
        select(EligibilityVerification).where(EligibilityVerification.user_id == user_id)
    )).all())
    for verification in verifications:
        if verification.document_key:
            await storage.delete(verification.document_key)
            verification.document_key = None
    sessions = list((await db.scalars(select(Session).where(Session.user_id == user_id))).all())
    for session in sessions:
        session.revoked_at = datetime.now(UTC)
        session.revoked_reason = "account_deleted"
    user.google_sub = None
    user.email = f"deleted+{user.id}@invalid.parallax"
    user.email_normalized = user.email.casefold()
    user.full_name = "Deleted participant"
    user.picture_url = None
    user.phone_e164 = None
    user.status = "deleted"
    from app.services.audit import record as audit_record

    audit_record(
        db,
        request,
        actor_id=ctx.user.id,
        actor_role=_role(ctx, edition_id),
        action="user.deletion_fulfilled",
        resource_type="user",
        resource_id=user_id,
        after={"status": "deleted", "documentsRemoved": True},
    )
    await db.flush()
    await db.commit()
    return {"data": {"deleted": True}}


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
    if order.edition_id != edition_id:
        raise NotFound("Payment order not found.")
    refund = await payment_service.refund_order(
        db,
        order,
        amount_paise=payload.amount_paise,
        reason_code=payload.reason_code,
        reason_note=payload.reason_note,
        requested_by_id=ctx.user.id,
        idempotency_key=payload.idempotency_key,
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
    from app.core.config import get_settings

    if get_settings().verification_mode == "api":
        raise Forbidden("Manual review is disabled in API verification mode.")
    v = await db.get(EligibilityVerification, verification_id)
    if v is None or v.edition_id != edition_id:
        raise NotFound("Verification not found.")
    await verif_service.review(
        db,
        request,
        v,
        decision=payload.decision,
        reason=payload.reason,
        fake_or_invalid=payload.fake_or_invalid,
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
        ],
        "total": total,
        "page": page,
        "pageSize": page_size,
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

    event_id = payload.event_id
    if ticket.registration_id:
        registration = await db.get(Registration, ticket.registration_id)
        if registration is None or registration.status not in ("confirmed", "reserved"):
            raise Conflict("This registration is no longer valid.")
        if event_id and event_id != registration.event_id:
            raise Conflict("This ticket belongs to a different event.")
        event_id = registration.event_id
    elif event_id:
        linked = (
            await db.execute(
                select(Registration.id).where(
                    Registration.user_id == ticket.user_id,
                    Registration.edition_id == edition_id,
                    Registration.event_id == event_id,
                    Registration.status.in_(["confirmed", "reserved"]),
                )
            )
        ).scalar_one_or_none()
        if linked is None:
            raise Conflict("This participant is not registered for that event.")

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
