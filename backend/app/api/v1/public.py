"""Public, cacheable catalogue. No cookies are read and no PII is returned."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_get, cache_set
from app.core.config import get_settings
from app.core.errors import Forbidden, NotFound, ValidationFailed
from app.integrations.storage import LocalStorage, verify_local_signature
from app.schemas.common import paged
from app.schemas.public import PublicConfig
from app.services import announcements as announcement_service
from app.services import events as event_service
from app.services.editions import (
    current_edition,
    current_policy,
    edition_by_slug,
    policy_public,
    registration_open,
    serialize_edition,
)
from app.services.system_settings import all_settings, registration_is_open, unlock_at
from app.db.session import get_db
from app.models.edition import EventCategory, Icon
from app.models.user import ProfileChoice
from sqlalchemy import select

router = APIRouter(prefix="/public", tags=["public"])

CACHE_EDGE = {"Cache-Control": "public, max-age=60, s-maxage=300, stale-while-revalidate=600"}
CACHE_60 = CACHE_EDGE


@router.get("/registration-policy")
async def registration_policy(db: AsyncSession = Depends(get_db)) -> dict:
    settings = await all_settings(db)
    opens_at = await unlock_at(db)
    return {
        "data": {
            "registrationOpen": await registration_is_open(db),
            "registrationUnlockAt": opens_at.isoformat(),
            "prices": {
                "isteMemberPaise": settings["isteMemberPaise"],
                "nonIstePaise": settings["nonIstePaise"],
                "polytechnicPaise": settings["polytechnicPaise"],
            },
        }
    }


@router.get("/profile-options")
async def profile_options(kind: str, db: AsyncSession = Depends(get_db)) -> dict:
    if kind not in {"branch", "college"}:
        raise ValidationFailed("Choose branch or college options.")
    names = list(
        (
            await db.execute(
                select(ProfileChoice.name)
                .where(ProfileChoice.kind == kind)
                .order_by(ProfileChoice.normalized_name)
                .limit(250)
            )
        ).scalars()
    )
    return {"data": names}


@router.get("/config", response_model=PublicConfig)
async def config(db: AsyncSession = Depends(get_db)) -> PublicConfig:
    cached_val = cache_get("public:config")
    if cached_val is not None:
        return cached_val
    settings = get_settings()
    slug = None
    support = None
    try:
        edition = await current_edition(db)
        slug = edition.slug
        support = edition.contact_email
    except Exception:
        pass
    result = PublicConfig(
        environment=settings.app_env,
        dev_login=settings.dev_login_available,
        google_login=settings.google_configured,
        payments_enabled=settings.payments_enabled,
        edition_slug=slug,
        support_email=support,
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
    except NotFound:
        raise
    except Exception:
        raise NotFound("Current edition not available yet.")

    policy = None
    try:
        policy = await current_policy(db, edition.id)
    except Exception:
        pass
    data = {"data": serialize_edition(edition, policy).model_dump(by_alias=True)}
    if not await registration_is_open(db) and data["data"].get("policy"):
        data["data"]["policy"]["passPricePaise"] = None
    cache_set("public:edition:current", data, ttl_seconds=60)
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
    data = {"data": serialize_edition(edition, policy).model_dump(by_alias=True)}
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
    price_visible = await registration_is_open(db)
    event_data = [row.model_dump(by_alias=True) for row in rows]
    if not price_visible:
        for item in event_data:
            item["baseValuePaise"] = None
            item["addonPricePaise"] = None
    result = paged(event_data, total, page, page_size)
    cache_set(cache_key, result, ttl_seconds=30)
    return result


@router.get("/editions/{slug}/events/{event_slug}")
async def event_detail(
    slug: str, event_slug: str, response: Response, db: AsyncSession = Depends(get_db)
) -> dict:
    response.headers.update(CACHE_EDGE)
    cache_key = f"public:event:{slug}:{event_slug}"
    cached_val = cache_get(cache_key)
    if cached_val is not None:
        return cached_val
    edition = await edition_by_slug(db, slug)
    row = await event_service.public_event(db, edition, event_slug)
    result = {"data": row.model_dump(by_alias=True)}
    if not await registration_is_open(db):
        result["data"]["baseValuePaise"] = None
        result["data"]["addonPricePaise"] = None
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
    edition = await edition_by_slug(db, slug)
    rows, total = await announcement_service.public_list(
        db, edition, page=page, page_size=page_size
    )
    response.headers.update(CACHE_60)
    return paged(rows, total, page, page_size)


@router.get("/icons/{icon_id}")
async def icon(icon_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Response:
    row = await db.get(Icon, icon_id)
    if row is None or row.status != "active" or not row.data:
        raise NotFound("Icon not found.")
    return Response(
        content=row.data,
        media_type=row.mime,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
        },
    )


@router.get("/documents/{key:path}")
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
async def public_policy(slug: str, db: AsyncSession = Depends(get_db)) -> dict:
    edition = await edition_by_slug(db, slug)
    policy = await current_policy(db, edition.id)
    data = {
        **policy_public(policy).model_dump(by_alias=True),
        "registrationOpen": registration_open(edition) and await registration_is_open(db),
        "selectionChangeDeadline": policy.selection_change_deadline,
    }
    if not await registration_is_open(db):
        data["passPricePaise"] = None
    return {"data": data}
