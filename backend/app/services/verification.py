"""Student eligibility verification: roster, college email and document review."""

import hashlib
import io
import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import func, select
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
from app.models.commerce import ConventionPass, PaymentOrder, Refund, Registration
from app.models.user import ParticipantProfile, User
from app.services.audit import record

ALLOWED_DOCUMENT_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


def sniff_document(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"%PDF"):
        return "application/pdf"
    raise AppError(
        "Upload a JPEG, PNG, WebP or PDF document.", code="FILE_TYPE_NOT_ALLOWED", status_code=415
    )


def validate_and_sanitize_upload(data: bytes, declared_type: str | None) -> tuple[bytes, str]:
    detected = sniff_document(data)
    if declared_type != detected:
        raise AppError(
            "The file content does not match its MIME type.",
            code="FILE_TYPE_NOT_ALLOWED",
            status_code=415,
        )
    if detected == "application/pdf":
        return data, detected
    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as source:
            source.load()
            cleaned = source.convert("RGB" if detected == "image/jpeg" else "RGBA")
            output = io.BytesIO()
            fmt = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}[detected]
            cleaned.save(output, format=fmt, exif=b"")
            return output.getvalue(), detected
    except Exception as exc:
        raise AppError(
            "The uploaded image is invalid.", code="FILE_TYPE_NOT_ALLOWED", status_code=415
        ) from exc


async def profile_complete(db: AsyncSession, user: User) -> bool:
    profile = await db.scalar(
        select(ParticipantProfile).where(ParticipantProfile.user_id == user.id)
    )
    if profile is None:
        return False
    return bool(
        user.full_name
        and profile.college_name
        and profile.education_level in {"B.Tech", "Polytechnic"}
        and profile.year_of_study in {1, 2, 3, 4}
        and profile.branch
        and profile.privacy_consent_at
        and profile.college_id_document_key
        and (not profile.iste_member or profile.iste_proof_document_key)
    )


async def _activate_pending_entitlements(
    db: AsyncSession, user_id: uuid.UUID, edition_id: uuid.UUID
) -> None:
    from app.services.passes import selections_for, sync_included_registrations
    from app.services.tickets import issue_for_pass, issue_for_registration

    passes = list(
        (
            await db.execute(
                select(ConventionPass).where(
                    ConventionPass.user_id == user_id,
                    ConventionPass.edition_id == edition_id,
                    ConventionPass.status == "pending_verification",
                )
            )
        ).scalars()
    )
    for user_pass in passes:
        paid = await db.scalar(
            select(PaymentOrder.id).where(
                PaymentOrder.linked_record_id == user_pass.id,
                PaymentOrder.status == "paid",
            )
        )
        if paid is None:
            continue
        user_pass.status = "active"
        await issue_for_pass(db, user_pass)
        await sync_included_registrations(db, user_pass, await selections_for(db, user_pass.id))

    registrations = list(
        (
            await db.execute(
                select(Registration).where(
                    Registration.user_id == user_id,
                    Registration.edition_id == edition_id,
                    Registration.status == "pending_verification",
                    Registration.order_id.is_not(None),
                )
            )
        ).scalars()
    )
    for registration in registrations:
        order = await db.get(PaymentOrder, registration.order_id)
        if order and order.status == "paid":
            registration.status = "confirmed"
            await issue_for_registration(db, registration)


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
    result = {
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
    if verification.notes:
        try:
            provider_result = json.loads(verification.notes)
            if provider_result.get("provider"):
                result["providerMessage"] = provider_result.get("apiMessage") or (
                    f"Verification provider result: {provider_result.get('apiStatus', 'unknown')}."
                )
        except (TypeError, ValueError):
            pass
    return result


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
    content_type: str | None = None,
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

    mode = get_settings().verification_mode
    if mode in {"api", "both"}:
        profile = await db.scalar(
            select(ParticipantProfile).where(ParticipantProfile.user_id == user.id)
        )
        if not profile or not profile.college_id_document_key:
            raise AppError("Upload your college ID before verification.", code="PROFILE_INCOMPLETE", status_code=409)
        college_id = await get_storage().get(profile.college_id_document_key)
        from app.integrations.id_verification import get_student_verifier

        api_result = await get_student_verifier().verify(
            user_id=str(user.id),
            education_level=profile.education_level or "",
            document=college_id,
        )
        verification.notes = json.dumps(
            {
                "provider": api_result.provider,
                "apiStatus": api_result.status,
                "apiMessage": api_result.message,
                "apiReference": api_result.reference,
            }
        )
        if mode == "api":
            verification.method = "api"
            verification.status = api_result.status
            verification.reviewed_at = datetime.now(UTC) if api_result.status in {"verified", "rejected"} else None
            await record(
                db,
                request,
                actor_id=user.id,
                actor_role="participant",
                action="verification.api_submitted",
                resource_type="eligibility_verification",
                resource_id=str(verification.id),
                after={"provider": api_result.provider, "status": api_result.status},
            )
            if verification.status == "verified":
                await _activate_pending_entitlements(db, user.id, edition.id)
            await db.flush()
            return serialize(verification)

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
        if allowed and "*" not in allowed and "all" not in allowed and domain not in allowed:
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
            raise AppError("The document is larger than 5 MB.", code="FILE_TOO_LARGE", status_code=413)
        file_bytes, mime_type = validate_and_sanitize_upload(file_bytes, content_type)
        key = document_key(filename)
        await get_storage().put(key, file_bytes, mime_type)
        verification.document_key = key
        verification.document_name = filename
    else:
        raise ValidationFailed("Unknown verification method.")

    if verification.status == "verified":
        await _activate_pending_entitlements(db, user.id, edition.id)

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
    await _activate_pending_entitlements(db, user.id, edition_id)
    await db.flush()
    return True


async def review(
    db: AsyncSession,
    request: Request,
    verification: EligibilityVerification,
    *,
    decision: str,
    reason: str | None,
    fake_or_invalid: bool = False,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
) -> EligibilityVerification:
    was_rejected = verification.status == "rejected"
    verification.status = decision
    verification.reviewer_id = actor_id
    verification.reviewed_at = datetime.now(UTC)
    if decision == "rejected":
        verification.rejection_reason = reason
        if not was_rejected:
            verification.rejected_count += 1
    else:
        verification.rejection_reason = None
        await _activate_pending_entitlements(db, verification.user_id, verification.edition_id)
    await record(
        db,
        request,
        actor_id=actor_id,
        actor_role=actor_role,
        action=f"verification.{decision}",
        resource_type="eligibility_verification",
        resource_id=str(verification.id),
        after={
            "userId": str(verification.user_id),
            "reason": reason,
            "fakeOrInvalid": fake_or_invalid,
        },
    )
    if decision == "rejected" and fake_or_invalid:
        paid_orders = list(
            (
                await db.execute(
                    select(PaymentOrder).where(
                        PaymentOrder.user_id == verification.user_id,
                        PaymentOrder.edition_id == verification.edition_id,
                        PaymentOrder.status == "paid",
                    )
                )
            ).scalars()
        )
        from app.services import payments as payment_service

        for order in paid_orders:
            already_refunded = await db.scalar(
                select(func.coalesce(func.sum(Refund.amount_paise), 0)).where(
                    Refund.order_id == order.id,
                    Refund.status.in_(("pending", "processed")),
                )
            )
            remaining = order.amount_paise - int(already_refunded or 0)
            if remaining <= 0:
                continue
            refund = await payment_service.refund_order(
                db,
                order,
                amount_paise=remaining,
                reason_code="invalid_proof",
                reason_note=reason,
                requested_by_id=actor_id,
                idempotency_key=f"verification-invalid:{verification.id}:{order.id}",
            )
            if refund.status == "processed":
                await email_outbox.enqueue(
                    db,
                    recipient=(await db.get(User, verification.user_id)).email,
                    template="refund_processed",
                    payload={"message": "Your payment refund for the rejected eligibility proof has been processed."},
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
