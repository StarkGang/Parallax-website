"""Database-backed fixed-window limiter: safe across worker processes."""

import hashlib
import os
import secrets
import time
from datetime import UTC, datetime

from fastapi import Depends, Request
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import RateLimited
from app.core.config import get_settings
from app.core.security import hash_token
from app.db.session import get_db
from app.models.commerce import RateLimitCounter
from app.models.user import Session as SessionRow


def client_ip(request: Request) -> str:
    # Vercel overwrites this header at its edge, so it cannot be chosen by the
    # browser. It is preferred over a potentially forged X-Forwarded-For.
    vercel_ip = request.headers.get("x-vercel-forwarded-for", "").split(",")[0].strip()
    if vercel_ip and os.getenv("VERCEL"):
        return vercel_ip
    settings = get_settings()
    peer = request.client.host if request.client else "?"
    if peer not in settings.trusted_proxies and peer not in {"127.0.0.1", "::1"}:
        # Do not let an internet client choose its own rate-limit bucket with a
        # forged X-Forwarded-For header.
        return peer
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip() or "?"
    return peer


async def _subject(
    db: AsyncSession, request: Request, explicit: str | None = None
) -> str:
    """Bucket key that an internet client cannot choose for itself.

    A cookie value is only trusted after it resolves to a real session. Using
    the raw cookie hash would let anyone send a fresh random cookie per request
    and get a brand-new counter every time, which defeats the limit entirely.
    """
    if explicit:
        return explicit
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"u:{user_id}"
    settings = get_settings()
    session_token = request.cookies.get(settings.session_cookie_name)
    if session_token:
        session_id = await db.scalar(
            select(SessionRow.id).where(SessionRow.token_hash == hash_token(session_token))
        )
        if session_id is not None:
            return f"s:{session_id}"
    return f"ip:{client_ip(request)}"


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
    if secrets.randbelow(200) == 0:
        # Keep the counter table bounded without a separate cron job.
        await db.execute(
            delete(RateLimitCounter).where(
                RateLimitCounter.window_start < datetime.fromtimestamp(now - 86400, UTC)
            )
        )
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
        target_subject = subject or await _subject(db, request, None)
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


async def login_limiter(
    request: Request, db: AsyncSession = Depends(get_db)
) -> None:
    """Limit both the submitted email and the source IP on login attempts."""
    email = ""
    try:
        payload = await request.json()
        if isinstance(payload, dict):
            email = str(payload.get("email") or "").strip().lower()[:160]
    except Exception:
        pass

    if email:
        allowed, retry_after = await consume(
            db,
            bucket="auth_login_email",
            subject=f"e:{email}",
            limit=20,
            window_seconds=300,
        )
        if not allowed:
            exc = RateLimited("Too many sign-in attempts. Try again shortly.")
            exc.details = {"retryAfter": retry_after}
            raise exc

    allowed, retry_after = await consume(
        db,
        bucket="auth_login_ip",
        subject=await _subject(db, request, None),
        limit=60,
        window_seconds=60,
    )
    if not allowed:
        exc = RateLimited("Too many sign-in attempts. Try again shortly.")
        exc.details = {"retryAfter": retry_after}
        raise exc


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
        subject=await _subject(db, request, None),
        limit=limit,
        window_seconds=window_seconds,
    )
    if not allowed:
        exc = RateLimited("Too many requests. Slow down for a moment.")
        exc.details = {"retryAfter": retry_after}
        raise exc


# Process-local limiter for read-only endpoints. It costs no database write, so
# a refresh loop is absorbed before it can hammer Postgres. Multi-instance
# deployments enforce it per instance, which is enough to bound a single caller.
_MEMORY_LIMITS: dict[tuple[str, str, int], int] = {}
_MEMORY_ENTRY_LIMIT = 5000


def _memory_subject(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"u:{user_id}"
    settings = get_settings()
    session_token = request.cookies.get(settings.session_cookie_name)
    if session_token:
        return f"s:{hashlib.sha256(session_token.encode()).hexdigest()[:16]}"
    return f"ip:{client_ip(request)}"


def memory_limiter(bucket: str, limit: int, window_seconds: int = 60):
    """In-memory fixed-window limiter for endpoints that must stay cheap."""

    async def dependency(request: Request) -> None:
        now = int(time.time())
        window = now // window_seconds
        key = (bucket, _memory_subject(request), window)
        if len(_MEMORY_LIMITS) > _MEMORY_ENTRY_LIMIT:
            stale = [item for item in _MEMORY_LIMITS if item[2] < window - 1]
            for item in stale:
                _MEMORY_LIMITS.pop(item, None)
        count = _MEMORY_LIMITS.get(key, 0) + 1
        if count > limit:
            exc = RateLimited("Too many requests. Slow down for a moment.")
            exc.details = {"retryAfter": max(0, (window + 1) * window_seconds - now)}
            raise exc
        _MEMORY_LIMITS[key] = count

    return dependency


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]

