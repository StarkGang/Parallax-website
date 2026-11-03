"""The single enforcement point: authentication, permissions and step-up."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.csrf import enforce_csrf
from app.core.errors import Forbidden, NotFound, StepUpRequired, Unauthenticated
from app.core.permissions import Role, STEP_UP_ACTIONS, has_permission, requires_mfa
from app.core.sessions import SessionContext, resolve_session
from app.db.session import get_db
from app.models.user import (
    EditionMembership,
    EventCoordinatorAssignment,
    Session,
    User,
)

STEP_UP_WINDOW = timedelta(minutes=5)


@dataclass
class AuthContext:
    user: User
    session: Session
    memberships: list[EditionMembership] = field(default_factory=list)
    coordinator_event_ids: set[uuid.UUID] = field(default_factory=set)

    @property
    def roles(self) -> list[str]:
        return sorted({m.role for m in self.memberships})

    @property
    def is_staff(self) -> bool:
        return any(m.role != Role.PARTICIPANT for m in self.memberships)

    def role_for(self, edition_id: uuid.UUID | None) -> str | None:
        if any(m.role in {Role.SUPER_ADMIN, "super_admin"} for m in self.memberships):
            return Role.SUPER_ADMIN
        if not edition_id:
            roles = self.roles
            return roles[0] if roles else None
        for membership in self.memberships:
            if membership.edition_id == edition_id:
                return membership.role
        return None

    def has(self, permission: str, edition_id: uuid.UUID | None = None) -> bool:
        for membership in self.memberships:
            if membership.role in {Role.SUPER_ADMIN, "super_admin"}:
                return True
            if edition_id and membership.edition_id != edition_id:
                continue
            if has_permission(membership.role, permission):
                return True
            if membership.role == Role.PARTICIPANT and permission.startswith("self."):
                return True
        return False

    def has_global(self, permission: str) -> bool:
        if any(m.role in {Role.SUPER_ADMIN, "super_admin"} for m in self.memberships):
            return True
        return any(has_permission(m.role, permission) for m in self.memberships)

    @property
    def staff_mfa_required(self) -> bool:
        return any(requires_mfa(m.role) for m in self.memberships)

    @property
    def mfa_verified_at(self) -> datetime | None:
        value = self.session.mfa_verified_at
        if value is None:
            return None
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    @property
    def step_up_fresh(self) -> bool:
        verified = self.mfa_verified_at
        return bool(verified and datetime.now(UTC) - verified <= STEP_UP_WINDOW)


async def current_context(
    request: Request, db: AsyncSession = Depends(get_db)
) -> AuthContext:
    resolved: SessionContext | None = await resolve_session(db, request)
    assert resolved is not None
    request.state.user_id = str(resolved.user.id)
    await enforce_csrf(request, resolved)

    memberships = list(
        (
            await db.execute(
                select(EditionMembership).where(
                    EditionMembership.user_id == resolved.user.id,
                    EditionMembership.status == "active",
                )
            )
        ).scalars()
    )
    assignments = list(
        (
            await db.execute(
                select(EventCoordinatorAssignment.event_id).where(
                    EventCoordinatorAssignment.user_id == resolved.user.id
                )
            )
        ).scalars()
    )
    return AuthContext(
        user=resolved.user,
        session=resolved.session,
        memberships=memberships,
        coordinator_event_ids=set(assignments),
    )


async def optional_context(request: Request, db: AsyncSession = Depends(get_db)) -> AuthContext | None:
    resolved = await resolve_session(db, request, required=False)
    if resolved is None:
        return None
    return await current_context(request, db)


async def current_user(ctx: AuthContext = Depends(current_context)) -> User:
    return ctx.user


def edition_id_from_request(request: Request) -> uuid.UUID | None:
    raw = request.path_params.get("edition_id") or request.path_params.get("eid")
    if not raw:
        raw = request.query_params.get("edition")
    if not raw:
        return None
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        raise NotFound("Edition not found.")


def require_permission(permission: str, *, step_up: bool = False, mfa: bool = False):
    async def dependency(
        request: Request, ctx: AuthContext = Depends(current_context)
    ) -> AuthContext:
        edition_id = edition_id_from_request(request)
        if not (ctx.has(permission, edition_id) or (edition_id is None and ctx.has_global(permission))):
            raise Forbidden("You do not have access to this action.")
        if permission == "self.read":
            return ctx
        settings = get_settings()
        if settings.mfa_enforced:
            if ctx.is_staff and (mfa or ctx.staff_mfa_required):
                if ctx.session.auth_level != "staff_mfa":
                    raise Forbidden(
                        "Two-factor authentication is required for staff accounts.",
                        code="MFA_REQUIRED",
                    )
            if step_up or permission in STEP_UP_ACTIONS:
                if ctx.staff_mfa_required and not ctx.step_up_fresh:
                    raise StepUpRequired("Confirm your authenticator code to continue.")
        request.state.actor_role = ctx.role_for(edition_id) or (ctx.roles[0] if ctx.roles else None)
        return ctx

    return dependency


def require_any_permission(*permissions: str):
    async def dependency(
        request: Request, ctx: AuthContext = Depends(current_context)
    ) -> AuthContext:
        edition_id = edition_id_from_request(request)
        if not any(ctx.has(p, edition_id) for p in permissions):
            raise Forbidden("You do not have access to this action.")
        settings = get_settings()
        if settings.mfa_enforced and ctx.is_staff and ctx.session.auth_level != "staff_mfa":
            raise Forbidden("Two-factor authentication is required.", code="MFA_REQUIRED")
        return ctx

    return dependency


def require_min_role(*roles: str):
    allowed = set(roles)

    async def dependency(
        request: Request, ctx: AuthContext = Depends(current_context)
    ) -> AuthContext:
        edition_id = edition_id_from_request(request)
        role = ctx.role_for(edition_id)
        if role not in allowed:
            raise Forbidden("You do not have access to this action.")
        return ctx

    return dependency


def participant_only(ctx: AuthContext = Depends(current_context)) -> AuthContext:
    if not ctx.memberships:
        return ctx
    if all(m.role == Role.PARTICIPANT for m in ctx.memberships):
        return ctx
    return ctx


async def require_event_access(
    db: AsyncSession, ctx: AuthContext, event_id: uuid.UUID, scope: str, event_edition_id: uuid.UUID
) -> None:
    if ctx.has(scope, event_edition_id):
        return
    if event_id in ctx.coordinator_event_ids:
        return
    raise Forbidden("You are not assigned to this event.")


def get_db_session(db: AsyncSession = Depends(get_db)) -> AsyncSession:
    return db


def unauthenticated() -> None:
    raise Unauthenticated("Sign in to continue.")


__all__ = [
    "AuthContext",
    "current_context",
    "current_user",
    "edition_id_from_request",
    "optional_context",
    "require_event_access",
    "require_permission",
    "require_any_permission",
    "require_min_role",
    "participant_only",
    "get_db_session",
    "Role",
]
