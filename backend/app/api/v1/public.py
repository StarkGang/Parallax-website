"""Public, cacheable catalogue. No cookies are read and no PII is returned."""

import html
import json
import logging
import re
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_get, cache_set
from app.core.config import get_settings
from app.core.errors import Forbidden, NotFound, ValidationFailed
from app.core.rate_limit import limiter
from app.integrations.storage import LocalStorage, get_storage, verify_local_signature
from app.schemas.common import paged
from app.schemas.public import PublicConfig
from app.services import announcements as announcement_service
from app.services import college_registrations as registration_service
from app.services import events as event_service
from app.services import teams as team_service
from app.services.telegram import send_telegram_inquiry
from pydantic import BaseModel, Field
from app.services.editions import (
    aware,
    current_edition,
    current_policy,
    edition_by_slug,
    policy_public,
    registration_open,
    serialize_edition,
)
from app.db.session import get_db
from app.models.edition import EventCategory, Icon
from app.models.user import User
from sqlalchemy import select

router = APIRouter(prefix="/public", tags=["public"])

logger = logging.getLogger(__name__)

CACHE_EDGE = {"Cache-Control": "public, max-age=60, s-maxage=300, stale-while-revalidate=600"}
CACHE_60 = CACHE_EDGE

# Last known-good edition payload. If the database briefly refuses a connection
# (a cold pooler is a normal serverless event) this keeps the site rendering
# instead of turning a retryable hiccup into a hard 404. Cache entries are
# per-process, so it is a safety net, not the primary cache.
EDITION_STALE_KEY = "public:edition:current:last-good"
EDITION_STALE_TTL = 60 * 60 * 24


@router.get("/config", response_model=PublicConfig)
async def config(db: AsyncSession = Depends(get_db)) -> PublicConfig:
    cached_val = cache_get("public:config")
    if cached_val is not None:
        return cached_val
    settings = get_settings()
    try:
        edition = await current_edition(db)
    except Exception:
        # Never cache a half-resolved config: the client would keep booting
        # without an edition for a whole TTL. Let it retry instead.
        logger.warning("public_config_edition_unresolved", exc_info=True)
        raise
    result = PublicConfig(
        environment=settings.app_env,
        dev_login=settings.dev_login_available,
        google_login=settings.google_configured,
        payments_enabled=settings.payments_enabled,
        razorpay_key_id=settings.razorpay_key_id if settings.payments_enabled else None,
        edition_slug=edition.slug,
        support_email=edition.contact_email,
        email_available=settings.email_available,
    )
    cache_set("public:config", result, ttl_seconds=60)
    return result


@router.get("/editions/current")
async def edition_current(response: Response, db: AsyncSession = Depends(get_db)) -> dict:
    response.headers.update(CACHE_EDGE)
    cached_val = cache_get("public:edition:current")
    if cached_val is not None:
        return cached_val

    try:
        edition = await current_edition(db)
        policy = None
        try:
            policy = await current_policy(db, edition.id)
        except NotFound:
            # An edition without a current policy is still a valid edition; the
            # policy section is simply omitted until one is published.
            logger.warning("edition_without_policy", extra={"edition": edition.slug})
        from app.models.registration import RegistrationSettings

        reg_settings_phone = (
            await db.scalar(
                select(RegistrationSettings.helpdesk_phone).where(
                    RegistrationSettings.edition_id == edition.id
                )
            )
        )
        data = {
            "data": serialize_edition(
                edition, policy, helpdesk_phone=reg_settings_phone
            ).model_dump(by_alias=True)
        }
    except NotFound:
        raise
    except Exception as exc:
        # Database timeouts and dropped pooler connections are transient. Serve
        # the last good payload when this process has one, otherwise let the
        # error middleware answer 503 so the client knows to retry. Never report
        # a retryable failure as a permanent 404.
        stale = cache_get(EDITION_STALE_KEY)
        logger.warning(
            "edition_current_unavailable error=%s stale=%s",
            type(exc).__name__,
            bool(stale),
        )
        if stale is not None:
            response.headers["X-Parallax-Stale"] = "1"
            return stale
        raise

    cache_set("public:edition:current", data, ttl_seconds=60)
    cache_set(EDITION_STALE_KEY, data, ttl_seconds=EDITION_STALE_TTL)
    return data


@router.get("/editions/{slug}")
async def edition_detail(slug: str, response: Response, db: AsyncSession = Depends(get_db)) -> dict:
    response.headers.update(CACHE_EDGE)
    cached_val = cache_get(f"public:edition:{slug}")
    if cached_val is not None:
        return cached_val
    edition = await edition_by_slug(db, slug)
    if edition.status == "draft":
        raise NotFound("Edition not found.")
    policy = None
    try:
        policy = await current_policy(db, edition.id)
    except NotFound:
        pass
    from app.models.registration import RegistrationSettings

    reg_settings_phone = (
        await db.scalar(
            select(RegistrationSettings.helpdesk_phone).where(
                RegistrationSettings.edition_id == edition.id
            )
        )
    )
    data = {
        "data": serialize_edition(
            edition, policy, helpdesk_phone=reg_settings_phone
        ).model_dump(by_alias=True)
    }
    cache_set(f"public:edition:{slug}", data, ttl_seconds=60)
    return data


@router.get("/editions/{slug}/categories")
async def categories(slug: str, response: Response, db: AsyncSession = Depends(get_db)) -> dict:
    response.headers.update(CACHE_EDGE)
    cached_val = cache_get(f"public:categories:{slug}")
    if cached_val is not None:
        return cached_val
    edition = await edition_by_slug(db, slug)
    rows = list(
        (
            await db.execute(
                select(EventCategory)
                .where(EventCategory.edition_id == edition.id)
                .order_by(EventCategory.display_order)
            )
        ).scalars()
    )
    data = {
        "data": [
            {
                "id": str(row.id),
                "name": row.name,
                "slug": row.slug,
                "accent": row.accent,
                "iconId": str(row.icon_id) if row.icon_id else None,
                "displayOrder": row.display_order,
            }
            for row in rows
        ]
    }
    cache_set(f"public:categories:{slug}", data, ttl_seconds=60)
    return data


@router.get("/editions/{slug}/registration-categories")
async def registration_categories(
    slug: str, response: Response, db: AsyncSession = Depends(get_db)
) -> dict:
    """Public fee tiers for the college registration funnel."""
    response.headers.update(CACHE_EDGE)
    cache_key = f"public:registration-categories:{slug}"
    cached_val = cache_get(cache_key)
    if cached_val is not None:
        return cached_val
    edition = await edition_by_slug(db, slug)
    rows = await registration_service.categories_for(
        db, edition.id, include_disabled=False
    )
    data = {"data": [registration_service.category_payload(row) for row in rows]}
    cache_set(cache_key, data, ttl_seconds=60)
    return data


@router.get(
    "/teams/{code}",
    dependencies=[Depends(limiter("team_invite_preview", 20, 60))],
)
async def team_invite_preview(
    code: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Public invite preview. Deliberately non-PII: no emails, no roster.

    The shareable link is derived by the client (``<origin>/team/<code>``);
    the code is the only thing stored on the team row.
    """
    data = await team_service.invite_preview(db, code)
    return {"data": data, **CACHE_60}


@router.get("/editions/{slug}/events")
async def events(
    slug: str,
    response: Response,
    category: str | None = None,
    format: str | None = Query(default=None, pattern="^(individual|team)$"),
    q: Annotated[str | None, Query(max_length=100)] = None,
    featured: bool | None = None,
    sort: Annotated[str | None, Query(pattern="^(date|programme)$")] = None,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, alias="pageSize")] = 24,
    db: AsyncSession = Depends(get_db),
) -> dict:
    response.headers.update(CACHE_EDGE)
    # Seat counts are about to be read from the database. Before serving them,
    # release seats held by attendees whose 24-hour desk request lapsed - a
    # fresh visitor must see the freed seat, not a stale hold.
    if registration_service.lazy_sweep_due(f"public:events:{slug}"):
        edition = await edition_by_slug(db, slug)
        await registration_service.lazy_enforce_for_read(
            db, edition_id=edition.id, request=None
        )
    cache_key = (
        f"public:events:{slug}:{category}:{format}:{q}:{featured}:{sort}:{page}:{page_size}"
    )
    cached_val = cache_get(cache_key)
    if cached_val is not None:
        return cached_val
    edition = await edition_by_slug(db, slug)
    rows, total = await event_service.list_public_events(
        db,
        edition,
        category=category,
        format=format,
        q=q,
        featured=featured,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    result = paged([row.model_dump(by_alias=True) for row in rows], total, page, page_size)
    cache_set(cache_key, result, ttl_seconds=30)
    return result


@router.get("/editions/{slug}/events/{event_slug}")
async def event_detail(
    slug: str, event_slug: str, response: Response, db: AsyncSession = Depends(get_db)
) -> dict:
    response.headers.update(CACHE_EDGE)
    if registration_service.lazy_sweep_due(f"public:events:{slug}"):
        edition = await edition_by_slug(db, slug)
        await registration_service.lazy_enforce_for_read(
            db, edition_id=edition.id, request=None
        )
    cache_key = f"public:event:{slug}:{event_slug}"
    cached_val = cache_get(cache_key)
    if cached_val is not None:
        return cached_val
    edition = await edition_by_slug(db, slug)
    row = await event_service.public_event(db, edition, event_slug)
    result = {"data": row.model_dump(by_alias=True)}
    cache_set(cache_key, result, ttl_seconds=60)
    return result


@router.get("/editions/{slug}/schedule")
async def schedule(slug: str, response: Response, db: AsyncSession = Depends(get_db)) -> dict:
    response.headers.update(CACHE_EDGE)
    cache_key = f"public:schedule:{slug}"
    cached_val = cache_get(cache_key)
    if cached_val is not None:
        return cached_val
    edition = await edition_by_slug(db, slug)
    days = await event_service.schedule(db, edition)
    result = {
        "data": [
            {
                "date": day.date.isoformat(),
                "label": day.label,
                "items": [item.model_dump(by_alias=True) for item in day.items],
            }
            for day in days
        ]
    }
    cache_set(cache_key, result, ttl_seconds=60)
    return result


@router.get("/editions/{slug}/announcements")
async def announcements(
    slug: str,
    response: Response,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50, alias="pageSize")] = 10,
    db: AsyncSession = Depends(get_db),
) -> dict:
    cache_key = f"public:announcements:{slug}:{page}:{page_size}"
    cached_val = cache_get(cache_key)
    if cached_val is not None:
        response.headers.update(CACHE_60)
        return cached_val
    edition = await edition_by_slug(db, slug)
    rows, total = await announcement_service.public_list(
        db, edition, page=page, page_size=page_size
    )
    result = paged(rows, total, page, page_size)
    cache_set(cache_key, result, ttl_seconds=60)
    response.headers.update(CACHE_60)
    return result


@router.get(
    "/icons/{icon_id}",
    dependencies=[Depends(limiter("public_icon", 300, 60))],
)
async def icon(icon_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Response:
    row = await db.get(Icon, icon_id)
    if row is None or row.status != "active":
        raise NotFound("Icon not found.")

    headers = {
        "Cache-Control": "public, max-age=31536000, immutable",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    }

    if row.storage_key:
        # Icons live in the object bucket now. Hand the browser the bucket/CDN
        # URL when there is one, and only proxy the bytes for backends whose
        # "public" URL is still a signed API path (local dev).
        public = get_storage().public_url(row.storage_key)
        if public.startswith("http"):
            return RedirectResponse(public, status_code=307, headers=headers)
        try:
            payload = await get_storage().get(row.storage_key)
        except Exception:  # noqa: BLE001 - a missing object falls through to the column
            payload = None
        if payload:
            return Response(content=payload, media_type=row.mime, headers=headers)

    # Rows written before the move (or uploads made while the bucket was down)
    # still carry their bytes.
    if not row.data:
        raise NotFound("Icon not found.")
    return Response(content=row.data, media_type=row.mime, headers=headers)


@router.get(
    "/documents/{key:path}",
    dependencies=[Depends(limiter("public_document", 120, 60))],
)
async def document(key: str, expires: int, signature: str) -> Response:
    if not verify_local_signature(key, expires, signature):
        raise Forbidden("This document link has expired.", code="SIGNED_URL_EXPIRED")
    try:
        data = await LocalStorage().get(key)
    except FileNotFoundError:
        raise NotFound("Document not found.")
    if data.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif data.startswith(b"\x89PNG"):
        mime = "image/png"
    else:
        mime = "application/pdf"
    return Response(
        content=data,
        media_type=mime,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@router.get("/editions/{slug}/policy")
async def public_policy(
    slug: str, response: Response, db: AsyncSession = Depends(get_db)
) -> dict:
    response.headers.update(CACHE_60)
    cache_key = f"public:policy:{slug}"
    cached_val = cache_get(cache_key)
    if cached_val is not None:
        return cached_val
    edition = await edition_by_slug(db, slug)
    policy = await current_policy(db, edition.id)
    result = {
        "data": {
            **policy_public(policy).model_dump(by_alias=True),
            "registrationOpen": registration_open(edition),
            "selectionChangeDeadline": policy.selection_change_deadline,
        }
    }
    cache_set(cache_key, result, ttl_seconds=60)
    return result


class ContactInquiryRequest(BaseModel):
    name: str = Field(default="Inquirer", max_length=200)
    email: str = Field(default="", max_length=254)
    category: str = Field(default="general", max_length=100)
    message: str = Field(default="", max_length=50000)


async def _deliver_inquiry(payload: dict) -> None:
    """Forward a contact message to the team after the visitor is answered.

    Nothing is written to the database, so a notification failure is logged
    (with the message) rather than silently dropping it.
    """
    try:
        result = await send_telegram_inquiry(**payload)
    except Exception as exc:  # noqa: BLE001 - notification is best effort
        logger.warning(
            "inquiry_notification_failed",
            error=type(exc).__name__,
            name=payload.get("name"),
            email=payload.get("email"),
            category=payload.get("category"),
            message=payload.get("message"),
        )
        return
    if not result.get("sent"):
        logger.warning(
            "inquiry_not_notified",
            reason=result.get("reason"),
            name=payload.get("name"),
            email=payload.get("email"),
            category=payload.get("category"),
            message=payload.get("message"),
        )


@router.post("/inquiries", dependencies=[Depends(limiter("public_inquiry", 5, 600))])
async def submit_inquiry(
    request: Request,
    background: BackgroundTasks,
) -> dict:
    raw = await request.body()
    data: dict = {}
    try:
        parsed = json.loads(raw.decode("utf-8") if raw else "{}")
        if isinstance(parsed, str):
            parsed = json.loads(parsed)
        if isinstance(parsed, dict):
            data = parsed
    except Exception:
        data = {}

    name = str(data.get("name") or "").strip() or "Inquirer"
    email = str(data.get("email") or "").strip()
    category = str(data.get("category") or "General").strip()
    message = str(data.get("message") or "").strip()

    if not message:
        raise ValidationFailed("Message cannot be empty.")
    if len(message) > 4000:
        raise ValidationFailed("Message is too long (4000 characters maximum).")
    if email and (len(email) > 254 or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email)):
        raise ValidationFailed("Enter a valid email address.")

    name = name[:200]
    category = category[:100]

    ip = request.client.host if request.client else None
    settings = get_settings()
    can_notify = bool(
        settings.effective_telegram_bot_token
        and settings.effective_telegram_chat_id
        and not settings.is_test
    )
    if can_notify:
        background.add_task(
            _deliver_inquiry,
            {
                "name": name,
                "email": email,
                "category": category,
                "message": message,
                "ip": ip,
            },
        )
    else:
        logger.info(
            "inquiry_logged_no_channel",
            name=name,
            email=email,
            category=category,
            message=message,
        )

    return {
        "data": {
            "sent": True,
            "notified": can_notify,
            "message": (
                "Your message has been received. Our team will contact you shortly."
                if can_notify
                else "Your message was received and logged for the organising team. Live "
                "alerts are not configured right now, so a reply may take longer."
            ),
        }
    }


@router.get(
    "/c/{code}",
    dependencies=[Depends(limiter("public_credential", 60, 60))],
)
async def check_credential(
    code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Public credential check for scanned QR codes, returning verification and registered events."""
    from app.models.registration import CollegeRegistration
    from app.models.commerce import Registration, Ticket
    from app.models.edition import Event
    from app.services import tickets as ticket_service
    from fastapi.responses import HTMLResponse

    normalized = (code or "").strip().upper()
    reg = None

    # Studio-issued cards (staff, faculty, sponsors, guests) are stored in their
    # own table and resolved before the registration lookup.
    if normalized.startswith("PXC"):
        from app.services import credentials as credential_service
        from fastapi.responses import HTMLResponse as _Html

        credential = await credential_service.resolve_public(db, normalized)
        if credential is not None:
            body = credential_service.public_payload(credential)
            if "text/html" in request.headers.get("accept", ""):
                badge = (
                    '<span style="background:#059669;color:#fff;padding:4px 10px;border-radius:9999px;font-size:12px;font-weight:700;">✓ VALID CREDENTIAL</span>'
                    if body["valid"]
                    else '<span style="background:#dc2626;color:#fff;padding:4px 10px;border-radius:9999px;font-size:12px;font-weight:700;">⛔ REVOKED</span>'
                )
                page = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Credential Verification · Parallax</title></head>
<body style="margin:0;padding:24px;background:#09090b;color:#f4f4f5;font-family:system-ui,-apple-system,sans-serif;display:flex;justify-content:center;">
<div style="max-width:440px;width:100%;background:#0f0f12;border:1px solid #27272a;border-radius:16px;padding:24px;">
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;border-bottom:1px solid #27272a;padding-bottom:12px;">
<div><h3 style="margin:0;font-size:16px;color:#fff;letter-spacing:0.05em;">PARALLAX</h3>
<small style="color:#71717a;">Official Credential Verification</small></div>{badge}</div>
<h2 style="margin:0 0 4px 0;font-size:22px;color:#fff;">{html.escape(body["name"] or "")}</h2>
<div style="font-size:13px;color:#7c5cff;font-weight:600;margin-bottom:14px;">{html.escape(body["role"] or "")} · {html.escape(body["code"] or "")}</div>
<div style="background:#18181b;border-radius:10px;padding:12px;font-size:13px;color:#d4d4d8;">
<div><strong>Organisation:</strong> {html.escape(body["college"] or "—")}</div>
</div>
<div style="text-align:center;font-size:11px;color:#52525b;border-top:1px solid #18181b;padding-top:14px;margin-top:18px;">
Issued by the organising committee · not a participant registration</div>
</div></body></html>"""
                return _Html(
                    content=page,
                    headers={
                        "Cache-Control": "no-store",
                        "X-Robots-Tag": "noindex, nofollow",
                        "X-Content-Type-Options": "nosniff",
                        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'",
                    },
                )
            return {"data": body}

    # A pass card carries a signed ticket token; a registration card carries a
    # signed registration code. An unsigned registration number is rejected so
    # the page cannot be used to look up attendees by guessing.
    ticket_id = ticket_service.parse_ticket_token(normalized)
    if ticket_id is not None and ticket_service.token_is_valid(normalized, ticket_id):
        ticket = await db.get(Ticket, ticket_id)
        if ticket is not None:
            reg = (
                await db.execute(
                    select(CollegeRegistration)
                    .where(
                        CollegeRegistration.user_id == ticket.user_id,
                        CollegeRegistration.edition_id == ticket.edition_id,
                    )
                    .order_by(CollegeRegistration.created_at.desc())
                )
            ).scalars().first()

    if reg is None:
        number = ticket_service.public_registration_number(normalized)
        if number:
            reg = (
                await db.execute(
                    select(CollegeRegistration).where(
                        CollegeRegistration.registration_number == number
                    )
                )
            ).scalars().first()

    if reg:
        # A suspended account invalidates the credential even though the ticket
        # row itself was never revoked.
        owner_status = (
            await db.scalar(select(User.status).where(User.id == reg.user_id))
        )
        account_suspended = owner_status == "suspended"
        diff_due = reg.category_change_status == "awaiting_payment"
        # A refund in flight, or a completed *full* refund, invalidates the
        # credential. A completed partial refund does not: the attendee kept the
        # entitlement they were not refunded for.
        refund_open = reg.refund_status in {"initiated", "processing"}
        fully_refunded = reg.payment_status == "refunded"
        is_valid = (
            not account_suspended
            and not refund_open
            and not fully_refunded
            and not diff_due
            and reg.payment_status in {"paid", "completed"}
            and reg.verification_status != "rejected"
        )
        event_rows = list(
            (
                await db.execute(
                    select(Registration, Event, EventCategory)
                    .join(Event, Registration.event_id == Event.id)
                    .join(EventCategory, EventCategory.id == Event.category_id)
                    .where(
                        Registration.user_id == reg.user_id,
                        Registration.edition_id == reg.edition_id,
                        Registration.status.in_(["confirmed", "reserved"]),
                    )
                )
            ).all()
        )
        events_data = [
            {
                "id": str(event.id),
                "title": event.title,
                "category": category.name if category is not None else "",
                "startsAt": aware(event.starts_at).isoformat() if event.starts_at else None,
                "endsAt": aware(event.ends_at).isoformat() if event.ends_at else None,
                "venueRoom": event.venue_room,
                "status": r.status,
                "label": "Payment pending" if r.status == "reserved" else "Confirmed",
                "teamId": str(r.team_id) if r.team_id else None,
            }
            for r, event, category in event_rows
        ]

        if "text/html" in request.headers.get("accept", ""):
            # Every value below is participant-controlled, so it must be escaped
            # before it reaches the HTML page.
            safe_name = html.escape(reg.full_name or "")
            safe_category = html.escape(reg.category_name or "")
            safe_number = html.escape(reg.registration_number or "")
            safe_college = html.escape(reg.college_name or "NSS College of Engineering")
            status_badge = (
                '<span style="background:#059669;color:#fff;padding:4px 10px;border-radius:9999px;font-size:12px;font-weight:700;">✓ ACTIVE PASS</span>'
                if is_valid and reg.verification_status == "approved"
                else '<span style="background:#d97706;color:#fff;padding:4px 10px;border-radius:9999px;font-size:12px;font-weight:700;">⚠️ PENDING VERIFICATION</span>'
                if is_valid
                else '<span style="background:#dc2626;color:#fff;padding:4px 10px;border-radius:9999px;font-size:12px;font-weight:700;">⛔ ACCOUNT SUSPENDED</span>'
                if account_suspended
                else '<span style="background:#dc2626;color:#fff;padding:4px 10px;border-radius:9999px;font-size:12px;font-weight:700;">⚠️ UPGRADE PAYMENT DUE</span>'
                if diff_due
                else '<span style="background:#dc2626;color:#fff;padding:4px 10px;border-radius:9999px;font-size:12px;font-weight:700;">REFUND IN PROGRESS</span>'
                if refund_open or fully_refunded
                else '<span style="background:#dc2626;color:#fff;padding:4px 10px;border-radius:9999px;font-size:12px;font-weight:700;">REJECTED / NOT VALID</span>'
            )
            events_html = "".join(
                f'<li style="margin-bottom:8px;padding:8px 12px;background:#18181b;border-radius:8px;border:1px solid #27272a;">'
                f'<strong style="color:#c4b5fd;display:block;">{html.escape(e["title"] or "")}</strong>'
                f'<span style="font-size:12px;color:#a1a1aa;">Venue: {html.escape(e["venueRoom"] or "Main Campus")} · {html.escape(e["label"])}</span>'
                f'</li>'
                for e in events_data
            ) or '<p style="color:#71717a;font-size:13px;">No individual add-on events registered. Delegate has General All-Access pass privileges.</p>'

            page_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Credential Verification · Parallax</title>
</head>
<body style="margin:0;padding:24px;background:#09090b;color:#f4f4f5;font-family:system-ui,-apple-system,sans-serif;display:flex;justify-content:center;">
  <div style="max-width:440px;width:100%;background:#0f0f12;border:1px solid #27272a;border-radius:16px;padding:24px;box-shadow:0 20px 40px rgba(0,0,0,0.8);">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;border-bottom:1px solid #27272a;padding-bottom:12px;">
      <div>
        <h3 style="margin:0;font-size:16px;color:#fff;letter-spacing:0.05em;">PARALLAX 2027</h3>
        <small style="color:#71717a;">Official Credential Verification</small>
      </div>
      {status_badge}
    </div>
    <h2 style="margin:0 0 4px 0;font-size:22px;color:#fff;">{safe_name}</h2>
    <div style="font-size:13px;color:#7c5cff;font-weight:600;margin-bottom:14px;">{safe_category} · {safe_number}</div>
    <div style="background:#18181b;border-radius:10px;padding:12px;margin-bottom:18px;font-size:13px;line-height:1.6;color:#d4d4d8;">
      <div><strong>College:</strong> {safe_college}</div>
    </div>
    <h4 style="margin:0 0 10px 0;font-size:13px;color:#a1a1aa;text-transform:uppercase;letter-spacing:0.08em;">Verified Event Registrations ({len(events_data)})</h4>
    <ul style="list-style:none;padding:0;margin:0 0 20px 0;">{events_html}</ul>
    <div style="text-align:center;font-size:11px;color:#52525b;border-top:1px solid #18181b;padding-top:14px;">
      ISTE Students' Chapter · NSS College of Engineering, Palakkad
    </div>
  </div>
</body>
</html>"""
            return HTMLResponse(
                content=page_html,
                headers={
                    "Cache-Control": "no-store",
                    "X-Robots-Tag": "noindex, nofollow",
                    "X-Content-Type-Options": "nosniff",
                    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'",
                },
            )

        return {
            "data": {
                "valid": is_valid,
                "registrationNumber": reg.registration_number,
                "fullName": reg.full_name,
                "category": reg.category_name,
                "college": reg.college_name,
                "verificationStatus": reg.verification_status,
                "isVerified": reg.verification_status == "approved",
                "registeredEvents": events_data,
                "eventsCount": len(events_data),
            }
        }
    return {"data": {"valid": False, "code": code, "registeredEvents": [], "eventsCount": 0}}



