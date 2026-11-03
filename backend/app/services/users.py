"""User account operations, profile management, staff membership and Google user upsert."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.permissions import Role, STAFF_ROLES
from app.core.security import decrypt_pii, encrypt_pii, hash_token, new_token
from app.models.commerce import ConventionPass
from app.models.edition import ConventionEdition, EligibilityVerification
from app.models.user import (
    EditionMembership,
    MfaCredential,
    ParticipantProfile,
    Session,
    StaffInvite,
    User,
)
from app.schemas.auth import MeResponse, RoleGrant
from app.services.audit import record
from app.services.editions import current_edition, current_policy
from app.services.verification import profile_complete, status_for


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def find_by_sub(db: AsyncSession, sub: str) -> User | None:
    return (await db.execute(select(User).where(User.google_sub == sub))).scalar_one_or_none()


async def upsert_google_user(
    db: AsyncSession, claims: dict[str, Any], request: Request | None = None
) -> tuple[User, bool]:
    """Identity is matched on Google's stable sub claim, or existing email."""
    sub = str(claims.get("sub") or "")
    if not sub:
        raise ValidationFailed("Google did not return a user identifier.")

    email = str(claims.get("email") or "")
    if not email:
        raise ValidationFailed("Google did not return an email address.")
    if not claims.get("email_verified", False):
        raise ValidationFailed("The Google account's email is not verified.")

    norm_email = normalize_email(email)
    user = await find_by_sub(db, sub)
    created = False

    if user is None:
        # Check if user with this email already exists
        existing_by_email = (
            await db.execute(select(User).where(User.email_normalized == norm_email))
        ).scalar_one_or_none()

        if existing_by_email is not None:
            user = existing_by_email
            user.google_sub = sub
            user.email = email
            user.email_verified = True
            if claims.get("name") and not user.full_name:
                user.full_name = str(claims["name"])[:160]
            if claims.get("picture"):
                user.picture_url = claims["picture"]
        else:
            user = User(
                google_sub=sub,
                email=email,
                email_normalized=norm_email,
                email_verified=True,
                full_name=str(claims.get("name") or email.split("@")[0])[:160],
                picture_url=claims.get("picture"),
                status="active",
            )
            db.add(user)
            await db.flush()
            created = True
    else:
        user.email = email
        user.email_normalized = norm_email
        user.email_verified = True
        if claims.get("name"):
            user.full_name = str(claims["name"])[:160]
        if claims.get("picture"):
            user.picture_url = claims["picture"]

    user.last_login_at = datetime.now(UTC)
    await db.flush()
    return user, created


async def apply_bootstrap_and_invites(
    db: AsyncSession, user: User, request: Request | None = None
) -> None:
    settings = get_settings()
    owner = normalize_email(settings.bootstrap_owner_email) if settings.bootstrap_owner_email else ""

    edition = await _safe_current_edition(db)

    # 1. Check bootstrap owner
    if owner and normalize_email(user.email) == owner:
        if edition is not None:
            existing = (
                await db.execute(
                    select(EditionMembership).where(
                        EditionMembership.user_id == user.id,
                        EditionMembership.edition_id == edition.id,
                        EditionMembership.role == Role.SUPER_ADMIN,
                    )
                )
            ).scalar_one_or_none()

            if existing is None:
                db.add(
                    EditionMembership(
                        edition_id=edition.id,
                        user_id=user.id,
                        role=Role.SUPER_ADMIN,
                        status="active",
                    )
                )
                await db.flush()

    # 2. Check pending staff invites for user's email
    invites = list(
        (
            await db.execute(
                select(StaffInvite).where(
                    StaffInvite.email_normalized == user.email_normalized,
                    StaffInvite.claimed_at.is_(None),
                    StaffInvite.expires_at > datetime.now(UTC),
                )
            )
        ).scalars()
    )

    for invite in invites:
        existing_m = (
            await db.execute(
                select(EditionMembership).where(
                    EditionMembership.user_id == user.id,
                    EditionMembership.edition_id == invite.edition_id,
                    EditionMembership.role.in_(invite.roles),
                )
            )
        ).scalar_one_or_none()

        if existing_m is None:
            db.add(
                EditionMembership(
                    edition_id=invite.edition_id,
                    user_id=user.id,
                    role=invite.roles[0],
                    status="active",
                )
            )
        invite.claimed_at = datetime.now(UTC)
        invite.claimed_by = user.id
        await db.flush()


async def _safe_current_edition(db: AsyncSession) -> ConventionEdition | None:
    try:
        return await current_edition(db)
    except Exception:
        # If editions table is empty or error, fallback to first edition
        return (await db.execute(select(ConventionEdition).limit(1))).scalar_one_or_none()


async def me_payload(db: AsyncSession, user: User, session: Session) -> MeResponse:
    memberships = list(
        (
            await db.execute(
                select(EditionMembership).where(
                    EditionMembership.user_id == user.id,
                    EditionMembership.status == "active",
                )
            )
        ).scalars()
    )

    edition = await _safe_current_edition(db)
    edition_id = edition.id if edition else None

    verification = None
    if edition_id:
        verification = (
            await db.execute(
                select(EligibilityVerification).where(
                    EligibilityVerification.user_id == user.id,
                    EligibilityVerification.edition_id == edition_id,
                )
            )
        ).scalar_one_or_none()

    mfa = (
        await db.execute(
            select(MfaCredential).where(
                MfaCredential.user_id == user.id,
                MfaCredential.status == "active",
            )
        )
    ).scalar_one_or_none()

    is_complete = await profile_complete(db, user)
    v_status = verification.status if verification else "unverified"

    return MeResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        picture_url=user.picture_url,
        status=user.status,
        roles=[
            RoleGrant(
                edition_id=m.edition_id,
                role=m.role,
            )
            for m in memberships
        ],
        auth_level=session.auth_level,
        mfa_enabled=bool(mfa and mfa.status == "active"),
        mfa_required=False,
        profile_complete=is_complete,
        student_verified=bool(verification and verification.status == "verified"),
        current_edition_id=edition_id,
        verification_status=v_status,
        created_at=user.created_at,
    )


async def profile_payload(db: AsyncSession, user: User) -> dict[str, Any]:
    profile = (
        await db.execute(
            select(ParticipantProfile).where(ParticipantProfile.user_id == user.id)
        )
    ).scalar_one_or_none()

    identifier = None
    if profile and profile.student_identifier_enc:
        try:
            identifier = decrypt_pii(profile.student_identifier_enc)
        except Exception:
            identifier = None

    return {
        "fullName": user.full_name,
        "email": user.email,
        "phone": user.phone_e164,
        "collegeName": profile.college_name if profile else None,
        "universityName": profile.university_name if profile else None,
        "course": profile.course if profile else None,
        "branch": profile.branch if profile else None,
        "yearOfStudy": profile.year_of_study if profile else None,
        "studentIdentifier": identifier,
        "studentIdentifierLast4": profile.student_identifier_last4 if profile else None,
        "institutionEmail": profile.institution_email if profile else None,
        "profileComplete": await profile_complete(db, user),
        "verificationRequired": True,
    }


async def update_profile(
    db: AsyncSession, request: Request, user: User, payload: dict[str, Any]
) -> dict[str, Any]:
    profile = (
        await db.execute(
            select(ParticipantProfile).where(ParticipantProfile.user_id == user.id)
        )
    ).scalar_one_or_none()

    if profile is None:
        profile = ParticipantProfile(user_id=user.id)
        db.add(profile)

    if "fullName" in payload and payload["fullName"]:
        user.full_name = str(payload["fullName"])[:160]
    if "phone" in payload:
        user.phone_e164 = payload["phone"]
    if "collegeName" in payload:
        profile.college_name = payload["collegeName"]
    if "universityName" in payload:
        profile.university_name = payload["universityName"]
    if "course" in payload:
        profile.course = payload["course"]
    if "branch" in payload:
        profile.branch = payload["branch"]
    if "yearOfStudy" in payload:
        profile.year_of_study = payload["yearOfStudy"]
    if "studentIdentifier" in payload and payload["studentIdentifier"]:
        raw_id = str(payload["studentIdentifier"]).strip()
        profile.student_identifier_enc = encrypt_pii(raw_id)
        profile.student_identifier_last4 = raw_id[-4:]
    if "institutionEmail" in payload:
        profile.institution_email = payload["institutionEmail"]

    await db.flush()
    return await profile_payload(db, user)


async def list_users(
    db: AsyncSession,
    edition_id: uuid.UUID | None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 50,
    include_pii: bool = True,
) -> tuple[list[dict[str, Any]], int]:
    stmt = select(User)
    if q:
        needle = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(User.full_name).like(needle),
                func.lower(User.email).like(needle),
            )
        )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    users = list(
        (
            await db.execute(
                stmt.order_by(User.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars()
    )

    out = []
    for u in users:
        p = (
            await db.execute(
                select(ParticipantProfile).where(ParticipantProfile.user_id == u.id)
            )
        ).scalar_one_or_none()

        m_roles = list(
            (
                await db.execute(
                    select(EditionMembership.role).where(
                        EditionMembership.user_id == u.id,
                        EditionMembership.status == "active",
                    )
                )
            ).scalars()
        )

        out.append(
            {
                "id": str(u.id),
                "fullName": u.full_name,
                "email": u.email,
                "emailVerified": u.email_verified,
                "status": u.status,
                "collegeName": p.college_name if p else None,
                "phone": u.phone_e164,
                "studentIdentifier": p.student_identifier_last4 if p else None,
                "roles": m_roles,
                "verificationStatus": "unverified",
                "passStatus": None,
                "createdAt": u.created_at.isoformat() if u.created_at else None,
                "lastLoginAt": u.last_login_at.isoformat() if u.last_login_at else None,
            }
        )

    return out, total


async def set_status(
    db: AsyncSession,
    request: Request,
    user_id: uuid.UUID,
    status: str,
    reason: str | None = None,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFound("User not found.")
    user.status = status
    if status == "suspended":
        from app.core.sessions import revoke_all_sessions

        await revoke_all_sessions(db, user_id)
    await record(
        db,
        request,
        actor_id=actor_id,
        actor_role=actor_role,
        action="user.status_updated",
        resource_type="user",
        resource_id=str(user.id),
        after={"status": status, "reason": reason},
    )
    await db.flush()
    return user


async def invite_staff(
    db: AsyncSession,
    request: Request,
    email: str,
    role: str,
    edition_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
) -> StaffInvite:
    token = new_token(32)
    invite = StaffInvite(
        edition_id=edition_id,
        email_normalized=normalize_email(email),
        roles=[role],
        token_hash=hash_token(token),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db.add(invite)
    await record(
        db,
        request,
        actor_id=actor_id,
        actor_role=actor_role,
        action="staff.invited",
        resource_type="staff_invite",
        after={"email": email, "role": role},
    )
    await db.flush()
    return invite


async def grant_membership(
    db: AsyncSession,
    request: Request,
    email: str,
    role: str,
    edition_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
) -> EditionMembership:
    norm = normalize_email(email)
    user = (
        await db.execute(select(User).where(User.email_normalized == norm))
    ).scalar_one_or_none()

    if user is None:
        raise NotFound("User with that email does not exist yet. Invite them instead.")

    membership = (
        await db.execute(
            select(EditionMembership).where(
                EditionMembership.user_id == user.id,
                EditionMembership.edition_id == edition_id,
                EditionMembership.role == role,
            )
        )
    ).scalar_one_or_none()

    if membership is None:
        membership = EditionMembership(
            edition_id=edition_id,
            user_id=user.id,
            role=role,
            status="active",
        )
        db.add(membership)
    else:
        membership.status = "active"

    await record(
        db,
        request,
        actor_id=actor_id,
        actor_role=actor_role,
        action="membership.granted",
        resource_type="membership",
        after={"email": email, "role": role},
    )
    await db.flush()
    return membership


async def my_sessions(
    db: AsyncSession, user_id: uuid.UUID, current_id: uuid.UUID
) -> list[dict[str, Any]]:
    rows = list(
        (
            await db.execute(
                select(Session)
                .where(Session.user_id == user_id, Session.revoked_at.is_(None))
                .order_by(Session.last_seen_at.desc())
            )
        ).scalars()
    )
    return [
        {
            "id": s.id,
            "created_at": s.created_at,
            "last_seen_at": s.last_seen_at,
            "idle_expires_at": s.idle_expires_at,
            "auth_level": s.auth_level,
            "ip_prefix": s.ip_prefix,
            "user_agent_hash": s.user_agent_hash,
            "current": s.id == current_id,
        }
        for s in rows
    ]


async def revoke_own_session(
    db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID
) -> None:
    session = await db.get(Session, session_id)
    if session is None or session.user_id != user_id:
        raise NotFound("Session not found.")
    session.revoked_at = datetime.now(UTC)
    await db.flush()


async def request_deletion(db: AsyncSession, user: User) -> None:
    user.status = "deletion_requested"
    await db.flush()


async def memberships_for(
    db: AsyncSession, edition_id: uuid.UUID
) -> list[dict[str, Any]]:
    rows = list(
        (
            await db.execute(
                select(EditionMembership, User)
                .join(User, EditionMembership.user_id == User.id)
                .where(
                    EditionMembership.edition_id == edition_id,
                    EditionMembership.status == "active",
                )
                .order_by(User.full_name)
            )
        ).all()
    )
    return [
        {
            "id": str(m.id),
            "userId": str(u.id),
            "fullName": u.full_name,
            "email": u.email,
            "role": m.role,
            "status": m.status,
            "createdAt": m.created_at.isoformat() if m.created_at else None,
        }
        for m, u in rows
    ]


__all__ = [
    "normalize_email",
    "find_by_sub",
    "upsert_google_user",
    "apply_bootstrap_and_invites",
    "me_payload",
    "_safe_current_edition",
    "profile_payload",
    "update_profile",
    "list_users",
    "set_status",
    "invite_staff",
    "grant_membership",
    "my_sessions",
    "revoke_own_session",
    "request_deletion",
    "memberships_for",
]
