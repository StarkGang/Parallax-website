"""User account operations, profile management, staff membership and Google user upsert."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.attendee import decode_food, decode_gender, encode_food, encode_gender
from app.core.config import get_settings
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.permissions import Role, requires_mfa
from app.core.security import encrypt_pii, hash_token, new_token
from app.core.sessions import revoke_all_sessions
from app.models.commerce import ConventionPass, Registration
from app.models.edition import ConventionEdition
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
from app.services.editions import current_edition


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
    db: AsyncSession,
    user: User,
    request: Request | None = None,
    invite_token: str | None = None,
) -> None:
    """Grant the bootstrap owner and claim the invite the user actually opened.

    Signing in used to claim *every* open invite for the email address, so a
    person who was only invited as check-in staff also received the super-admin
    invite sitting unused in the same address's inbox. A role now requires the
    token from its own link.
    """
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

    # 2. Claim the invite whose token this browser presented, and only that one.
    token = (invite_token or "").strip()
    if not token:
        return
    invites = list(
        (
            await db.execute(
                select(StaffInvite).where(
                    StaffInvite.email_normalized == user.email_normalized,
                    StaffInvite.token_hash == hash_token(token),
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

        # One staff role per edition: claiming an invite for a new role retires
        # the old one instead of stacking a second permission set on the account.
        others = list(
            (
                await db.execute(
                    select(EditionMembership).where(
                        EditionMembership.user_id == user.id,
                        EditionMembership.edition_id == invite.edition_id,
                        EditionMembership.status == "active",
                        EditionMembership.role.notin_(invite.roles),
                        EditionMembership.role != Role.SUPER_ADMIN,
                    )
                )
            ).scalars()
        )
        for row in others:
            await db.delete(row)

        if existing_m is None:
            db.add(
                EditionMembership(
                    edition_id=invite.edition_id,
                    user_id=user.id,
                    role=invite.roles[0],
                    status="active",
                )
            )
        else:
            existing_m.status = "active"
        invite.claimed_at = datetime.now(UTC)
        invite.claimed_by = user.id
        await db.flush()


async def cleanup_expired_invites(db: AsyncSession) -> int:
    """Delete invites that expired unclaimed.

    Nothing swept them, so the table grew forever and the admin screen kept
    listing invitations nobody could use.
    """
    from sqlalchemy import delete

    result = await db.execute(
        delete(StaffInvite).where(
            StaffInvite.claimed_at.is_(None),
            StaffInvite.expires_at < datetime.now(UTC),
        )
    )
    return int(result.rowcount or 0)


async def _safe_current_edition(db: AsyncSession) -> ConventionEdition | None:
    try:
        return await current_edition(db)
    except Exception:
        # If editions table is empty or error, fallback to first edition
        return (await db.execute(select(ConventionEdition).limit(1))).scalar_one_or_none()


async def profile_complete(db: AsyncSession, user: User) -> bool:
    """True when the attendee has the college details an ID card needs."""
    profile = await db.scalar(
        select(ParticipantProfile).where(ParticipantProfile.user_id == user.id)
    )
    if profile is None:
        return False
    return bool(
        user.full_name
        and profile.college_name
        and profile.course
        and profile.year_of_study
    )


def mask_email(email: str | None) -> str | None:
    """Hide the local part but keep it recognisable for staff without PII rights."""
    if not email or "@" not in email:
        return email
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


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

    mfa = (
        await db.execute(
            select(MfaCredential).where(
                MfaCredential.user_id == user.id,
                MfaCredential.status == "active",
            )
        )
    ).scalar_one_or_none()

    is_complete = await profile_complete(db, user)
    settings = get_settings()
    staff_mfa_role = any(requires_mfa(m.role) for m in memberships)
    mfa_required = bool(
        settings.mfa_enforced and staff_mfa_role and session.auth_level != "staff_mfa"
    )

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
        mfa_required=mfa_required,
        profile_complete=is_complete,
        current_edition_id=edition_id,
        created_at=user.created_at,
    )


async def profile_payload(db: AsyncSession, user: User) -> dict[str, Any]:
    profile = (
        await db.execute(
            select(ParticipantProfile).where(ParticipantProfile.user_id == user.id)
        )
    ).scalar_one_or_none()

    # The convention pass form is the primary place attendees enter their college
    # details. Fall back to their latest registration so an existing profile view
    # is never blank just because they bought a pass first.
    if profile is None or not any(
        [profile.college_name, profile.course, profile.branch, profile.year_of_study]
    ):
        from app.models.registration import CollegeRegistration

        registration = (
            await db.execute(
                select(CollegeRegistration)
                .where(CollegeRegistration.user_id == user.id)
                .order_by(CollegeRegistration.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if registration is not None:
            if profile is None:
                profile = ParticipantProfile(user_id=user.id)
                db.add(profile)
            profile.college_name = profile.college_name or registration.college_name
            profile.course = profile.course or registration.course
            profile.branch = profile.branch or registration.branch
            profile.city = profile.city or registration.city
            profile.state = profile.state or registration.state
            if profile.gender is None:
                profile.gender = registration.gender
            if profile.food_preference is None:
                profile.food_preference = registration.food_preference
            if not profile.needs_accommodation and registration.needs_accommodation:
                profile.needs_accommodation = True
            if profile.year_of_study is None and registration.year_of_study:
                try:
                    profile.year_of_study = int(str(registration.year_of_study).strip()[:1])
                except (TypeError, ValueError):
                    pass

    # The full student identifier is deliberately not returned: the profile
    # form no longer collects or displays it, and shipping a decrypted PII
    # value to the browser for no reason is not worth the risk.
    return {
        "fullName": user.full_name,
        "email": user.email,
        "phone": user.phone_e164,
        "collegeName": profile.college_name if profile else None,
        "universityName": profile.university_name if profile else None,
        "course": profile.course if profile else None,
        "branch": profile.branch if profile else None,
        "yearOfStudy": profile.year_of_study if profile else None,
        "city": profile.city if profile else None,
        "state": profile.state if profile else None,
        "gender": decode_gender(profile.gender) if profile else None,
        "foodPreference": decode_food(profile.food_preference) if profile else None,
        "needsAccommodation": bool(profile.needs_accommodation) if profile else False,
        "dateOfBirth": profile.date_of_birth.isoformat() if profile and profile.date_of_birth else None,
        "studentIdentifierLast4": profile.student_identifier_last4 if profile else None,
        "institutionEmail": profile.institution_email if profile else None,
        "profileComplete": await profile_complete(db, user),
        "profileLocked": await is_profile_locked(db, user.id),
    }


async def is_profile_locked(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """True once the user has paid for a registration or holds an active pass.

    Before payment, the profile remains editable. Once payment is done and the
    pass is bought, self-service profile edits are locked so identity, meal
    and accommodation stay consistent with the kitchen, hostel and ID check.
    """
    from app.models.registration import CollegeRegistration

    has_paid_reg = await db.scalar(
        select(CollegeRegistration.id)
        .where(
            CollegeRegistration.user_id == user_id,
            CollegeRegistration.payment_status.in_(["paid", "completed"]),
            CollegeRegistration.verification_status != "cancelled",
        )
        .limit(1)
    )
    if has_paid_reg is not None:
        return True
    has_pass = await db.scalar(
        select(ConventionPass.id)
        .where(
            ConventionPass.user_id == user_id,
            ConventionPass.status == "active",
        )
        .limit(1)
    )
    return has_pass is not None


async def update_profile(
    db: AsyncSession, request: Request, user: User, payload: dict[str, Any]
) -> dict[str, Any]:
    if await is_profile_locked(db, user.id):
        raise Conflict(
            "Your profile is locked after registering or paying. Ask the organiser desk to update your details.",
            code="PROFILE_LOCKED",
        )
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
    if "city" in payload:
        profile.city = payload["city"]
    if "state" in payload:
        profile.state = payload["state"]
    if "gender" in payload:
        profile.gender = encode_gender(payload["gender"])
    if "foodPreference" in payload:
        profile.food_preference = encode_food(payload["foodPreference"])
    if "needsAccommodation" in payload and payload["needsAccommodation"] is not None:
        profile.needs_accommodation = bool(payload["needsAccommodation"])
    if "dateOfBirth" in payload:
        profile.date_of_birth = payload["dateOfBirth"]
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
    include_pii: bool = False,  # callers must opt in with user.read_pii
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
                stmt.order_by(User.last_login_at.desc().nullslast(), User.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars()
    )

    user_ids = [u.id for u in users]
    profiles: dict[uuid.UUID, ParticipantProfile] = {}
    roles_by_user: dict[uuid.UUID, list[str]] = {}
    pass_statuses: dict[uuid.UUID, str] = {}
    reg_counts: dict[uuid.UUID, int] = {}
    if user_ids:
        for profile in (
            await db.execute(
                select(ParticipantProfile).where(ParticipantProfile.user_id.in_(user_ids))
            )
        ).scalars():
            profiles[profile.user_id] = profile
        for user_id, role in (
            await db.execute(
                select(EditionMembership.user_id, EditionMembership.role).where(
                    EditionMembership.user_id.in_(user_ids),
                    EditionMembership.status == "active",
                )
            )
        ).all():
            roles_by_user.setdefault(user_id, []).append(role)
        pass_stmt = select(ConventionPass.user_id, ConventionPass.status).where(
            ConventionPass.user_id.in_(user_ids)
        )
        if edition_id:
            pass_stmt = pass_stmt.where(ConventionPass.edition_id == edition_id)
        for user_id, p_status in (
            await db.execute(pass_stmt.order_by(ConventionPass.created_at.desc()))
        ).all():
            if user_id not in pass_statuses:
                pass_statuses[user_id] = p_status

        from app.models.registration import CollegeRegistration

        cr_stmt = select(
            CollegeRegistration.user_id, CollegeRegistration.verification_status
        ).where(CollegeRegistration.user_id.in_(user_ids))
        if edition_id:
            cr_stmt = cr_stmt.where(CollegeRegistration.edition_id == edition_id)
        for user_id, cr_status in (
            await db.execute(cr_stmt.order_by(CollegeRegistration.created_at.desc()))
        ).all():
            if user_id not in pass_statuses and cr_status:
                pass_statuses[user_id] = cr_status

        reg_stmt = (
            select(Registration.user_id, func.count(Registration.id))
            .where(
                Registration.user_id.in_(user_ids),
                Registration.status != "cancelled",
            )
            .group_by(Registration.user_id)
        )
        if edition_id:
            reg_stmt = reg_stmt.where(Registration.edition_id == edition_id)
        for user_id, cnt in (await db.execute(reg_stmt)).all():
            reg_counts[user_id] = int(cnt or 0)

    out = []
    for u in users:
        p = profiles.get(u.id)
        out.append(
            {
                "id": str(u.id),
                "fullName": u.full_name,
                "email": u.email if include_pii else mask_email(u.email),
                "emailVerified": u.email_verified,
                "status": u.status,
                "collegeName": p.college_name if p else None,
                "course": p.course if p else None,
                "branch": p.branch if p else None,
                "yearOfStudy": p.year_of_study if p else None,
                "city": p.city if p else None,
                "state": p.state if p else None,
                "phone": u.phone_e164 if include_pii else None,
                "studentIdentifier": p.student_identifier_last4 if p else None,
                "roles": roles_by_user.get(u.id, []),
                "passStatus": pass_statuses.get(u.id),
                "eventCount": reg_counts.get(u.id, 0),
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
        # revoke_all_sessions takes a reason; omitting it made every suspension
        # a 500 before the status was even written.
        await revoke_all_sessions(db, user_id, "account_suspended")
        from app.services.passes import release_event_entitlements
        from app.services.tickets import revoke_for_pass

        passes = (
            await db.execute(
                select(ConventionPass).where(
                    ConventionPass.user_id == user_id,
                    ConventionPass.status.in_(["active", "pending", "suspended"]),
                )
            )
        ).scalars().all()
        edition_ids = list(
            (
                await db.execute(
                    select(Registration.edition_id)
                    .where(Registration.user_id == user_id)
                    .distinct()
                )
            ).scalars()
        )
        # Suspending the account has to suspend the pass itself, not just the
        # seats: an "active" pass kept the portal listing a valid pass and let
        # the door scan it after the account was suspended.
        for p in passes:
            if p.status in ("active", "pending"):
                p.status = "suspended"
            await revoke_for_pass(db, p.id)
        pass_editions = [p.edition_id for p in passes]
        for eid in set(edition_ids + pass_editions):
            await release_event_entitlements(
                db,
                user_id=user_id,
                edition_id=eid,
                reason=f"Account suspended by administration: {reason or 'Violation of convention policy'}",
                actor_id=actor_id,
            )
    elif status == "active":
        from app.models.registration import CollegeRegistration
        from app.services.tickets import issue_for_pass

        passes = (
            await db.execute(
                select(ConventionPass).where(
                    ConventionPass.user_id == user_id,
                    ConventionPass.status == "suspended",
                )
            )
        ).scalars().all()
        for p in passes:
            # Re-activating the account must not hand back a pass that was
            # rejected or refunded while the account was suspended.
            dead = (
                await db.execute(
                    select(CollegeRegistration.id).where(
                        CollegeRegistration.user_id == user_id,
                        CollegeRegistration.edition_id == p.edition_id,
                        (
                            (CollegeRegistration.payment_status == "refunded")
                            | (CollegeRegistration.verification_status == "rejected")
                            | (
                                CollegeRegistration.refund_status.in_(
                                    ["initiated", "processing", "completed"]
                                )
                            )
                        ),
                    )
                )
            ).scalars().first()
            if dead is not None:
                p.status = "cancelled"
                continue
            p.status = "active"
            await issue_for_pass(db, p)
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
) -> tuple[StaffInvite, str]:
    """Create a staff invite and return it with the one-time plaintext token.

    Only the token hash is stored, so the caller must surface the token (as a
    shareable link) immediately; it can never be recovered later.
    """
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
    return invite, token


async def grant_membership(
    db: AsyncSession,
    request: Request,
    email: str,
    role: str,
    edition_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
) -> tuple[EditionMembership, list[str]]:
    """Give one account exactly one staff role for this edition.

    Granting used to stack: an event coordinator granted finance admin ended up
    with both permission sets, and the console listed the same person twice, so
    nobody could tell what a teammate was actually allowed to do. A new grant
    now replaces the previous staff role; ``super_admin`` is never removed here,
    because locking out the owner is how an edition becomes unmanageable.

    Returns the membership and the roles it replaced.
    """
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

    # Retire every other staff role for this account in this edition.
    others = list(
        (
            await db.execute(
                select(EditionMembership).where(
                    EditionMembership.user_id == user.id,
                    EditionMembership.edition_id == edition_id,
                    EditionMembership.status == "active",
                    EditionMembership.role != role,
                    EditionMembership.role != Role.SUPER_ADMIN,
                )
            )
        ).scalars()
    )
    replaced = [row.role for row in others]
    for row in others:
        # Deleted, not flagged: a revoked row still shows up in raw table dumps
        # and in the unique (user, edition, role) key, and the audit log already
        # keeps the history of what was granted when.
        await db.delete(row)

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
        after={"email": email, "role": role, "replacedRoles": replaced},
    )
    await db.flush()
    return membership, replaced


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
    """Close the account without leaving paid entitlements behind.

    This is not wired to a route yet. It used to flip a status nobody read, so
    an account that asked for deletion kept a live pass and held seats. Sessions
    already refuse any non-active status; this also releases the seats, revokes
    the tickets and cancels the entry pass so nothing is left to honour.
    """
    from app.models.commerce import ConventionPass, PaymentOrder, Registration
    from app.services.tickets import revoke_for_pass, revoke_for_registration

    regs = list(
        (
            await db.execute(
                select(Registration).where(
                    Registration.user_id == user.id,
                    Registration.status.in_(["confirmed", "reserved"]),
                )
            )
        ).scalars()
    )
    for reg in regs:
        reg.status = "cancelled"
        reg.cancelled_at = datetime.now(UTC)
        reg.cancelled_by = "admin"
        reg.cancellation_reason = "Account deletion requested"
        await revoke_for_registration(db, reg.id)

    passes = list(
        (
            await db.execute(
                select(ConventionPass).where(ConventionPass.user_id == user.id)
            )
        ).scalars()
    )
    for user_pass in passes:
        if user_pass.status == "active":
            user_pass.status = "cancelled"
            await revoke_for_pass(db, user_pass.id)

    orders = list(
        (
            await db.execute(
                select(PaymentOrder).where(
                    PaymentOrder.user_id == user.id,
                    PaymentOrder.status == "created",
                )
            )
        ).scalars()
    )
    for order in orders:
        order.status = "expired"

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
