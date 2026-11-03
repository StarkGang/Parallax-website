"""Database-backed fixed-window limiter: safe across worker processes."""

import hashlib
from datetime import UTC, datetime

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import RateLimited
from app.db.session import get_db
from app.models.commerce import RateLimitCounter


def _subject(request: Request, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"u:{user_id}"
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    elif request.client:
        ip = request.client.host
    else:
        ip = "?"
    return f"ip:{ip}"


async def consume(
    db: AsyncSession,
    bucket: str,
    subject: str,
    limit: int,
    window_seconds: int,
) -> tuple[bool, int]:
    now = datetime.now(UTC).timestamp()
    window_start_ts = int(now // window_seconds) * window_seconds
    window_start = datetime.fromtimestamp(window_start_ts, UTC)
    values = {
        "bucket": bucket,
        "subject": subject[:160],
        "window_start": window_start,
        "count": 1,
    }

    dialect = db.bind.dialect.name if db.bind else "postgresql"
    if dialect == "sqlite":
        stmt = sqlite_insert(RateLimitCounter).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["bucket", "subject", "window_start"],
            set_={"count": RateLimitCounter.__table__.c.count + 1},
        )
    else:
        stmt = pg_insert(RateLimitCounter).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["bucket", "subject", "window_start"],
            set_={"count": RateLimitCounter.__table__.c.count + 1},
        )

    await db.execute(stmt)
    count = await db.scalar(
        select(RateLimitCounter.count).where(
            RateLimitCounter.bucket == bucket,
            RateLimitCounter.subject == subject[:160],
            RateLimitCounter.window_start == window_start,
        )
    )
    await db.commit()
    current = int(count or 1)
    allowed = current <= limit
    retry_after = max(0, int(window_start_ts + window_seconds - now))
    return allowed, retry_after


def limiter(
    bucket: str,
    limit: int,
    window_seconds: int,
    *,
    subject: str | None = None,
):
    async def dependency(
        request: Request, db: AsyncSession = Depends(get_db)
    ) -> None:
        target_subject = subject or _subject(request, None)
        allowed, retry_after = await consume(
            db,
            bucket=bucket,
            subject=target_subject,
            limit=limit,
            window_seconds=window_seconds,
        )
        if not allowed:
            exc = RateLimited("Too many attempts. Try again shortly.")
            exc.details = {"retryAfter": retry_after}
            raise exc

    return dependency


async def limit_user(
    db: AsyncSession,
    request: Request,
    bucket: str,
    limit: int,
    window_seconds: int = 60,
) -> None:
    allowed, retry_after = await consume(
        db,
        bucket=bucket,
        subject=_subject(request, None),
        limit=limit,
        window_seconds=window_seconds,
    )
    if not allowed:
        exc = RateLimited("Too many requests. Slow down for a moment.")
        exc.details = {"retryAfter": retry_after}
        raise exc


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]

