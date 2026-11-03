"""Student eligibility verification: roster, college email and document review."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, ValidationFailed
from app.core.security import hash_pii, hash_token, new_token, token_matches_hash
from app.integrations import email as email_outbox
from app.integrations.storage import document_key, get_storage
from app.models.edition import (
    ConventionEdition,
    EligibilityVerification,
    RosterEntry,
    VerificationEmailCode,
)
from app.models.user import ParticipantProfile, User
from app.services.audit import record

ALLOWED_DOCUMENT_TYPES = {"image/jpeg", "image/png", "application/pdf"}


def sniff_document(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"%PDF"):
        return "application/pdf"
    raise AppError(
        "Upload a JPEG, PNG or PDF document.", code="FILE_TYPE_NOT_ALLOWED", status_code=415
    )


async def profile_complete(db: AsyncSession, user: User) -> bool:
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
        and profile.student_identifier_enc
    )


async def _existing(
    db: AsyncSession, user_id: uuid.UUID, edition_id: uuid.UUID
) -> EligibilityVerification | None:
    return await db.scalar(
        select(EligibilityVerification).where(
            EligibilityVerification.edition_id == edition_id,
            EligibilityVerification.user_id == user_id,
        )
    )


def serialize(verification: EligibilityVerification | None) -> dict:
    if verification is None:
        return {
            "status": "unverified",
            "method": None,
            "submittedAt": None,
            "reviewedAt": None,
            "rejectionReason": None,
            "documentName": None,
            "canResubmit": True,
        }
    return {
        "status": verification.status,
        "method": verification.method,
        "submittedAt": verification.submitted_at.isoformat()
        if verification.submitted_at
        else None,
        "reviewedAt": verification.reviewed_at.isoformat() if verification.reviewed_at else None,
        "rejectionReason": verification.rejection_reason,
        "documentName": verification.document_name,
        "canResubmit": verification.status != "verified" and verification.rejected_count < 3,
    }


async def status_for(
    db: AsyncSession, user: User, edition_id: uuid.UUID
) -> dict:
    return serialize(await _existing(db, user.id, edition_id))


async def submit(
    db: AsyncSession,
    request: Request,
    user: User,
    edition: ConventionEdition,
    *,
    method: str,
    institution_email: str | None = None,
    file_bytes: bytes | None = None,
    filename: str | None = None,
) -> dict:
    if not await profile_complete(db, user):
        raise AppError(
            "Complete your profile (college, course, year and student ID) first.",
            code="PROFILE_INCOMPLETE",
            status_code=409,
        )
    existing = await _existing(db, user.id, edition.id)
    if existing and existing.status == "verified":
        raise AppError("You are already verified.", code="ALREADY_VERIFIED", status_code=409)
    if existing and existing.rejected_count >= 3:
        raise AppError(
            "Three submissions were rejected. Contact the organiser for help.",
            code="CONTACT_ORGANISER",
            status_code=409,
        )

    verification = existing or EligibilityVerification(
        user_id=user.id, edition_id=edition.id, method=method, status="pending"
    )
    verification.method = method
    verification.status = "pending"
    verification.submitted_at = datetime.now(UTC)
    verification.rejection_reason = None
    if existing is None:
        db.add(verification)
    await db.flush()

    if method == "roster":
        profile = await db.scalar(
            select(ParticipantProfile).where(ParticipantProfile.user_id == user.id)
        )
        if profile is None or not profile.student_identifier_enc:
            raise AppError(
                "Add your student ID to your profile first.",
                code="PROFILE_INCOMPLETE",
                status_code=409,
            )
        from app.core.security import decrypt_pii

        student_id = decrypt_pii(profile.student_identifier_enc) or ""
        student_hash = hash_pii(student_id)
        email_hash = hash_pii(user.email)
        entry = await db.scalar(
            select(RosterEntry).where(
                RosterEntry.edition_id == edition.id,
                (RosterEntry.student_hash == student_hash) | (RosterEntry.email_hash == email_hash),
            )
        )
        if entry:
            entry.claimed_at = datetime.now(UTC)
            entry.claimed_by = user.id
            verification.status = "verified"
            verification.reviewed_at = datetime.now(UTC)
            verification.notes = "Matched the imported eligibility roster."
        else:
            verification.status = "pending"
            verification.notes = "No roster match; queued for organiser review."
    elif method == "college_email":
        if not institution_email:
            raise AppError(
                "Enter your institutional email address.",
                code="VALIDATION_FAILED",
                status_code=422,
            )
        domain = institution_email.rsplit("@", 1)[-1].lower()
        allowed = [d.lower().lstrip("@") for d in (edition.allowed_email_domains or [])]
        if not allowed or domain not in allowed:
            raise ValidationFailed(
                "That email domain is not accepted for this convention.",
                details={"allowedDomains": allowed},
                code="EMAIL_DOMAIN_NOT_ALLOWED",
            )
        code = f"{int.from_bytes(new_token(4).encode()[:4], 'big') % 1000000:06d}"
        db.add(
            VerificationEmailCode(
                verification_id=verification.id,
                code_hash=hash_token(f"vc:{verification.id}:{code}"),
                expires_at=datetime.now(UTC) + timedelta(minutes=10),
            )
        )
        verification.document_key = None
        await email_outbox.enqueue(
            db, recipient=institution_email, template="verification_code", payload={"code": code}
        )
    elif method == "document":
        if not file_bytes:
            raise AppError("Attach a document.", code="VALIDATION_FAILED", status_code=422)
        settings = get_settings()
        if len(file_bytes) > settings.max_upload_bytes_document:
            raise AppError("The document is larger than 3 MB.", code="FILE_TOO_LARGE", status_code=413)
        sniff_document(file_bytes)
        key = document_key(filename)
        await get_storage().put(key, file_bytes, sniff_document(file_bytes))
        verification.document_key = key
        verification.document_name = filename
    else:
        raise ValidationFailed("Unknown verification method.")

    await record(
        db,
        request,
        actor_id=user.id,
        actor_role="participant",
        action="verification.submitted",
        resource_type="eligibility_verification",
        resource_id=str(verification.id),
        after={"method": method, "status": verification.status},
    )
    await db.flush()
    return serialize(verification)


async def confirm_email(
    db: AsyncSession, user: User, edition_id: uuid.UUID, code: str
) -> bool:
    verification = await _existing(db, user.id, edition_id)
    if verification is None:
        raise AppError("Submit a verification request first.", code="NOT_FOUND", status_code=404)
    if verification.status == "verified":
        return True
    row = await db.scalar(
        select(VerificationEmailCode)
        .where(
            VerificationEmailCode.verification_id == verification.id,
            VerificationEmailCode.consumed_at.is_(None),
        )
        .order_by(VerificationEmailCode.expires_at.desc())
    )
    if row is None:
        raise AppError("Request a new code.", code="CODE_EXPIRED", status_code=409)
    if row.attempts >= 5:
        raise AppError("Too many attempts. Request a new code.", code="CODE_LOCKED", status_code=429)
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    if datetime.now(UTC) > expires:
        raise AppError("That code has expired.", code="CODE_EXPIRED", status_code=409)
    if not token_matches_hash(f"vc:{verification.id}:{code}", row.code_hash):
        row.attempts += 1
        await db.flush()
        raise AppError("That code is not correct.", code="CODE_INVALID", status_code=400)
    row.consumed_at = datetime.now(UTC)
    verification.status = "verified"
    verification.reviewed_at = datetime.now(UTC)
    verification.notes = "Institutional email confirmed."
    await db.flush()
    return True


async def review(
    db: AsyncSession,
    request: Request,
    verification: EligibilityVerification,
    *,
    decision: str,
    reason: str | None,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
) -> EligibilityVerification:
    verification.status = decision
    verification.reviewer_id = actor_id
    verification.reviewed_at = datetime.now(UTC)
    if decision == "rejected":
        verification.rejection_reason = reason
        verification.rejected_count += 1
    else:
        verification.rejection_reason = None
    await record(
        db,
        request,
        actor_id=actor_id,
        actor_role=actor_role,
        action=f"verification.{decision}",
        resource_type="eligibility_verification",
        resource_id=str(verification.id),
        after={"userId": str(verification.user_id), "reason": reason},
    )
    await db.flush()
    return verification


def document_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def signed_document_url(verification: EligibilityVerification) -> str | None:
    if not verification.document_key:
        return None
    return await get_storage().signed_url(verification.document_key)


__all__ = [
    "confirm_email",
    "profile_complete",
    "review",
    "serialize",
    "signed_document_url",
    "sniff_document",
    "status_for",
    "submit",
]
