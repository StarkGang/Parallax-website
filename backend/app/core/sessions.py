"""Server-side sessions: opaque token in an HttpOnly cookie, HMAC hash at rest."""

import asyncio
import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Request, Response
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import Unauthenticated
from app.core.logging import get_logger
from app.core.security import hash_token, new_token, token_matches_hash
from app.models.user import Session, User

IDLE_SLIDE_THRESHOLD = timedelta(seconds=60)
# Bounds the best-effort idle slide so a saturated pooler cannot add latency.
IDLE_SLIDE_TIMEOUT_SECONDS = 2.0
SESSION_READ_RETRY_DELAY_SECONDS = 0.15

logger = get_logger("sessions")


@dataclass
class SessionContext:
    user: User
    session: Session


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def ip_prefix(ip: str | None) -> str | None:
    if not ip:
        return None
    if ":" in ip:
        return ":".join(ip.split(":")[:4])
    parts = ip.split(".")
    return ".".join(parts[:3]) if len(parts) == 4 else ip


def user_agent_hash(request: Request) -> str:
    agent = request.headers.get("user-agent", "")
    return hashlib.sha256(agent.encode()).hexdigest()[:32]


def _ttls(is_staff: bool) -> tuple[timedelta, timedelta]:
    s = get_settings()
    if is_staff:
        return (
            timedelta(minutes=s.session_idle_ttl_staff_min),
            timedelta(minutes=s.session_absolute_ttl_staff_min),
        )
    return (
        timedelta(minutes=s.session_idle_ttl_participant_min),
        timedelta(minutes=s.session_absolute_ttl_participant_min),
    )


async def create_session(
    db: AsyncSession, user: User, request: Request, *, is_staff: bool = False
) -> tuple[Session, str]:
    token = new_token(32)
    idle, absolute = _ttls(is_staff)
    now = _now()
    session = Session(
        token_hash=hash_token(token),
        user_id=user.id,
        csrf_secret=new_token(24),
        auth_level="basic",
        created_at=now,
        last_seen_at=now,
        idle_expires_at=now + idle,
        absolute_expires_at=now + absolute,
        ip_prefix=ip_prefix(request.client.host if request.client else None),
        user_agent_hash=user_agent_hash(request),
    )
    db.add(session)
    user.last_login_at = now
    await db.flush()
    return session, token


def set_session_cookie(response: Response, token: str, *, is_staff: bool = False) -> None:
    settings = get_settings()
    idle, _ = _ttls(is_staff)
    response.set_cookie(
        key=settings.session_cookie,
        value=token,
        max_age=int(idle.total_seconds()),
        path="/",
        secure=settings.cookie_secure_effective,
        httponly=True,
        samesite=settings.cookie_samesite,
    )


def clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.session_cookie,
        path="/",
        secure=settings.cookie_secure_effective,
        httponly=True,
        samesite=settings.cookie_samesite,
    )


def token_from_request(request: Request) -> str | None:
    settings = get_settings()
    for cookie_name in (settings.session_cookie, settings.session_cookie_name, 'px_session', '__Host-px_session'):
        if not cookie_name:
            continue
        val = request.cookies.get(cookie_name)
        if val:
            return val
    auth_header = request.headers.get('authorization')
    if auth_header and auth_header.lower().startswith('bearer '):
        return auth_header[7:].strip()
    # Session tokens are deliberately not accepted from the query string: URLs
    # leak through referrers, logs and browser history.
    return None


async def resolve_session(
    db: AsyncSession, request: Request, *, required: bool = True
) -> SessionContext | None:
    token = token_from_request(request)
    if not token:
        if required:
            raise Unauthenticated("Sign in to continue.")
        return None

    hashed = hash_token(token)
    row = await _session_row(db, hashed)
    if row is None:
        if required:
            raise Unauthenticated("Your session has expired. Sign in again.")
        return None

    session, user = row
    if not token_matches_hash(token, session.token_hash):
        raise Unauthenticated("Your session has expired. Sign in again.")

    now = _now()
    if session.revoked_at or now >= _aware(session.idle_expires_at) or now >= _aware(
        session.absolute_expires_at
    ):
        if required:
            raise Unauthenticated("Your session has expired. Sign in again.")
        return None
    if user.status != "active":
        raise Unauthenticated("This account is not active.")

    # Slide the idle window forward at most once a minute; the hard cap never
    # moves. This is deliberately *not* flushed on the request's session: a
    # read-only page used to fail with a statement timeout whenever the pooled
    # connection was cold, because authenticating it also performed a write.
    last_seen = _aware(session.last_seen_at)
    if now - last_seen > IDLE_SLIDE_THRESHOLD:
        new_idle = now + _ttls(session.auth_level == "staff_mfa")[0]
        absolute_cap = _aware(session.absolute_expires_at)
        await _slide_idle(session.id, now, min(new_idle, absolute_cap))

    return SessionContext(user=user, session=session)


async def _session_row(db: AsyncSession, hashed: str):
    """Load the session row, retrying once on a stale pooled connection.

    Supabase's pooler can drop or stall the first statement after an idle gap.
    One clean retry on a fresh transaction turns that into a normal request;
    a second failure propagates as a 503 rather than a crash.
    """
    stmt = (
        select(Session, User)
        .join(User, User.id == Session.user_id)
        .where(Session.token_hash == hashed)
    )
    try:
        return (await db.execute(stmt)).first()
    except (TimeoutError, DBAPIError) as exc:
        logger.warning("session_read_retry", error=type(exc).__name__)
        # A dead connection can fail the rollback too; the retry must still run.
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(SESSION_READ_RETRY_DELAY_SECONDS)
        return (await db.execute(stmt)).first()


async def _slide_idle(
    session_id: uuid.UUID, seen_at: datetime, idle_expires_at: datetime
) -> None:
    """Extend a session's idle window on its own connection.

    Failures are logged and dropped: the row keeps its previous window, the user
    stays signed in, and the next request slides it again.
    """
    from app.db.session import session_scope

    async def run() -> None:
        async with session_scope() as touch_db:
            await touch_db.execute(
                update(Session)
                .where(Session.id == session_id, Session.revoked_at.is_(None))
                .values(last_seen_at=seen_at, idle_expires_at=idle_expires_at)
            )

    try:
        await asyncio.wait_for(run(), timeout=IDLE_SLIDE_TIMEOUT_SECONDS)
    except (TimeoutError, DBAPIError) as exc:
        logger.warning("session_slide_skipped", error=type(exc).__name__)
    except Exception as exc:  # noqa: BLE001 - touching a session is never critical
        logger.warning("session_slide_failed", error=type(exc).__name__)


async def rotate_session(
    db: AsyncSession, context: SessionContext, request: Request, *, auth_level: str | None = None
) -> str:
    """New token, old row revoked. Used on login, MFA success, role change and step-up."""
    context.session.revoked_at = _now()
    context.session.revoked_reason = "rotated"
    token = new_token(32)
    new_row = Session(
        token_hash=hash_token(token),
        user_id=context.user.id,
        csrf_secret=new_token(24),
        auth_level=auth_level or context.session.auth_level,
        created_at=_now(),
        last_seen_at=_now(),
        idle_expires_at=context.session.idle_expires_at,
        absolute_expires_at=context.session.absolute_expires_at,
        mfa_verified_at=context.session.mfa_verified_at,
        ip_prefix=ip_prefix(request.client.host if request.client else None),
        user_agent_hash=user_agent_hash(request),
    )
    if auth_level == "staff_mfa":
        idle, absolute = _ttls(True)
        new_row.idle_expires_at = _now() + idle
        new_row.absolute_expires_at = _now() + min(absolute, absolute)
        new_row.mfa_verified_at = _now()
    db.add(new_row)
    await db.flush()
    return token


async def revoke_session_row(db: AsyncSession, session: Session, reason: str = "logout") -> None:
    session.revoked_at = _now()
    session.revoked_reason = reason
    await db.flush()


async def revoke_all_sessions(db: AsyncSession, user_id: uuid.UUID, reason: str) -> None:
    from sqlalchemy import update

    await db.execute(
        update(Session)
        .where(Session.user_id == user_id, Session.revoked_at.is_(None))
        .values(revoked_at=_now(), revoked_reason=reason)
    )
