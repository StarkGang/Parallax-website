"""Synchronizer CSRF token derived from the session, never stored in the browser."""

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import Forbidden
from app.core.security import constant_compare, derive_csrf_token
from app.core.sessions import SessionContext

SAFE_METHODS = {"GET", "OPTIONS", "HEAD"}


def csrf_token_for(context: SessionContext) -> str:
    return derive_csrf_token(context.session.csrf_secret, str(context.session.id))


async def enforce_csrf(request: Request, context: SessionContext) -> None:
    if request.method in SAFE_METHODS:
        return
    settings = get_settings()
    if settings.is_test:
        return
    if request.headers.get("authorization", "").lower().startswith("bearer "):
        return
    supplied = request.headers.get("x-csrf-token", "")
    if not supplied or not constant_compare(supplied, csrf_token_for(context)):
        raise Forbidden("The form token is stale. Refresh the page and try again.", code="CSRF_INVALID")


async def ensure_origin(request: Request) -> None:
    if request.method in SAFE_METHODS:
        return
    settings = get_settings()
    if settings.is_test:
        return
    origin = request.headers.get("origin")
    if origin and origin != settings.frontend_origin:
        raise Forbidden("Cross-origin request rejected.", code="ORIGIN_REJECTED")


__all__ = ["SAFE_METHODS", "csrf_token_for", "enforce_csrf", "ensure_origin", "AsyncSession"]
