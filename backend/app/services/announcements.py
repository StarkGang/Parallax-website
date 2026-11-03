"""Announcements: public broadcast and targeted communication."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.core.text import render_markdown
from app.models.edition import Announcement, ConventionEdition
from app.schemas.public import AnnouncementPublic
from app.services.audit import record


def serialize(a: Announcement) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "title": a.title,
        "bodyMd": a.body_md,
        "bodyHtml": render_markdown(a.body_md),
        "audience": a.audience,
        "status": a.status,
        "eventId": str(a.event_id) if a.event_id else None,
        "publishedAt": a.published_at.isoformat() if a.published_at else None,
        "createdAt": a.created_at.isoformat() if a.created_at else None,
    }


async def public_list(
    db: AsyncSession,
    edition: ConventionEdition,
    page: int = 1,
    page_size: int = 10,
) -> tuple[list[dict[str, Any]], int]:
    stmt = select(Announcement).where(
        Announcement.edition_id == edition.id,
        Announcement.status == "published",
        Announcement.audience == "public",
    )
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    rows = list(
        (
            await db.execute(
                stmt.order_by(Announcement.published_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars()
    )
    return [serialize(r) for r in rows], total


async def list_admin(
    db: AsyncSession, edition_id: uuid.UUID
) -> list[dict[str, Any]]:
    rows = list(
        (
            await db.execute(
                select(Announcement)
                .where(Announcement.edition_id == edition_id)
                .order_by(Announcement.created_at.desc())
            )
        ).scalars()
    )
    return [serialize(r) for r in rows]


async def upsert(
    db: AsyncSession,
    request: Request,
    edition_id: uuid.UUID,
    payload: dict[str, Any],
    announcement_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
) -> Announcement:
    a = None
    if announcement_id:
        a = await db.get(Announcement, announcement_id)
        if a is None or a.edition_id != edition_id:
            raise NotFound("Announcement not found.")
    else:
        a = Announcement(edition_id=edition_id)
        db.add(a)

    for field in ["title", "body_md", "audience", "event_id", "status"]:
        if field in payload:
            setattr(a, field, payload[field])

    if a.status == "published" and not a.published_at:
        a.published_at = datetime.now(UTC)

    await record(
        db,
        request,
        actor_id=actor_id,
        actor_role=actor_role,
        action="announcement.upserted",
        resource_type="announcement",
        resource_id=str(a.id),
        after={"title": a.title, "status": a.status},
    )
    await db.flush()
    return a


async def delete(
    db: AsyncSession,
    request: Request,
    edition_id: uuid.UUID,
    announcement_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
) -> None:
    a = await db.get(Announcement, announcement_id)
    if a is None or a.edition_id != edition_id:
        raise NotFound("Announcement not found.")
    await record(
        db,
        request,
        actor_id=actor_id,
        actor_role=actor_role,
        action="announcement.deleted",
        resource_type="announcement",
        resource_id=str(a.id),
    )
    await db.delete(a)
    await db.flush()


__all__ = ["serialize", "public_list", "list_admin", "upsert", "delete"]

