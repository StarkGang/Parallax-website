"""College registration: ISTE / Non-ISTE / Polytechnic pricing, document review,
verification workflow, notifications and refund tracking.

Payment, verification and refund status are separate columns on
``CollegeRegistration``. Nothing in this module ever marks a registration
approved because money moved, and a refund is never completed without a
gateway confirmation or an explicit finance-desk reference.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable

from fastapi import Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_delete_pattern
from app.core.config import get_settings
from app.core.attendee import decode_food, decode_gender, encode_food, encode_gender
from app.core.errors import AppError, Conflict, NotFound, ValidationFailed
from app.integrations import email as email_outbox
from app.integrations.storage import (
    get_document_storage,
    registration_document_key,
)
from app.models.commerce import (
    ConventionPass,
    PaymentOrder,
    PaymentTransaction,
    Refund,
    Ticket,
)
from app.models.edition import ConventionEdition
from app.models.registration import (
    CollegeRegistration,
    RegistrationCategory,
    RegistrationCategoryChange,
    RegistrationDocument,
    RegistrationNotification,
    RegistrationSettings,
)
from app.models.user import User
from app.services import tickets as ticket_service
from app.services.audit import record
from app.services.editions import aware

logger = logging.getLogger(__name__)

DOC_DEFINITIONS = {
    "photo": "Passport-size photo",
    "college_id": "College / University ID card",
    "iste_card": "ISTE Membership Card",
}

PHOTO_MAX_BYTES = 102_400  # 100 KB ceiling for the printed pass photo
PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}
PHOTO_REQUIREMENT = {
    "type": "photo",
    "label": "Passport-size photo",
    "required": True,
}

REJECTION_REASONS = {
    "fake_id": "Fake ID / Unverifiable Student Credentials",
    "wrong_category": "Wrong Category (e.g. Non-ISTE registered as ISTE)",
    "unclear_proof": "Unclear / Illegible Document Proof",
    "duplicate": "Duplicate Registration",
    "invalid_college_id": "Invalid college ID card",
    "invalid_iste_card": "Invalid ISTE membership card",
    "iste_without_proof": "User selected ISTE membership without valid proof",
    "incorrect_category": "Incorrect registration category",
    "duplicate_registration": "Duplicate registration",
    "other": "Other (custom explanation)",
}

DEFAULT_TEMPLATES = {
    "payment_success": "Payment of ₹{amount} received for {category}. Registration {registrationId} is now pending document verification.",
    "submitted": "Registration {registrationId} was submitted for verification. We will email you once the registration desk reviews your documents.",
    "approved": "Your {category} registration {registrationId} has been approved. Download your confirmation from the participant portal.",
    "rejected": "Your registration {registrationId} was rejected: {reason}",
    "documents_correction": "Documents for registration {registrationId} need correction: {reason} You have until {deadline} to fix this. After that, event seats and team placement are released and refunds for paid events are started.",
    "refund_initiated": "A refund of ₹{amount} has been initiated for registration {registrationId}. Refund status is tracked separately and is not complete yet.",
    "refund_completed": "The refund of ₹{amount} for registration {registrationId} has been confirmed as completed.",
    "refund_failed": "The refund for registration {registrationId} failed. The finance desk will review it.",
    "event_cancelled": "{event} was cancelled: {reason}. Your seat has been released and any amount paid for it is being refunded.",
    "event_cancelled_refund": "The amount you paid for the cancelled event was refunded to registration {registrationId}.",
    "category_change_approved": "Your category change to {category} for registration {registrationId} is approved. Pay the difference by {deadline}. After that, event seats and team placement are released and refunds for paid events are started.",
    "compliance_enforced": "The 24-hour window for registration {registrationId} closed. Event seats and team placement were released and paid event seats were refunded. Fix the request from the participant portal and select your events and team again.",
    "partial_refund": "A partial refund of ₹{amount} was recorded against registration {registrationId}. Your pass remains valid.",
}

EMAIL_TEMPLATES = {
    "payment_success": "registration_payment_success",
    "submitted": "registration_submitted",
    "approved": "registration_approved",
    "rejected": "registration_rejected",
    "documents_correction": "registration_documents_correction",
    "refund_initiated": "registration_refund_initiated",
    "refund_completed": "registration_refund_completed",
    "refund_failed": "registration_refund_failed",
    "compliance_enforced": "registration_compliance_enforced",
}

MAX_DOCUMENT_BYTES = 20_971_520  # 20 MB absolute system ceiling
ATTENDEE_DOCUMENT_BYTES = 512_000  # 500 KB limit for ID card verification uploads

# How long an attendee has to answer a desk request (corrected documents or a
# category-change difference) before their event seats are released and paid
# event money is refunded. Kept as a constant so every surface agrees.
COMPLIANCE_WINDOW_HOURS = 24
COMPLIANCE_KIND_DOCUMENTS = "documents"
COMPLIANCE_KIND_CATEGORY_PAYMENT = "category_payment"
COMPLIANCE_LABELS = {
    COMPLIANCE_KIND_DOCUMENTS: "Corrected documents requested",
    COMPLIANCE_KIND_CATEGORY_PAYMENT: "Category-change payment pending",
}


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


async def settings_for(
    db: AsyncSession, edition_id: uuid.UUID, *, create: bool = False
) -> RegistrationSettings | None:
    row = (
        await db.execute(
            select(RegistrationSettings).where(
                RegistrationSettings.edition_id == edition_id
            )
        )
    ).scalar_one_or_none()
    if row is None and create:
        edition = await db.get(ConventionEdition, edition_id)
        from app.seed import ensure_registration_config

        if edition is None:
            from app.services.editions import current_edition
            try:
                edition = await current_edition(db)
                edition_id = edition.id
            except Exception:
                raise NotFound("Edition not found.")
        await ensure_registration_config(db, edition)
        row = (
            await db.execute(
                select(RegistrationSettings).where(
                    RegistrationSettings.edition_id == edition_id
                )
            )
        ).scalar_one_or_none()
    return row


async def categories_for(
    db: AsyncSession, edition_id: uuid.UUID, *, include_disabled: bool = True
) -> list[RegistrationCategory]:
    stmt = select(RegistrationCategory).where(
        RegistrationCategory.edition_id == edition_id
    )
    if not include_disabled:
        stmt = stmt.where(RegistrationCategory.enabled.is_(True))
    return list(
        (await db.execute(stmt.order_by(RegistrationCategory.display_order))).scalars()
    )


async def category_for(
    db: AsyncSession, edition_id: uuid.UUID, category_id: uuid.UUID
) -> RegistrationCategory:
    row = await db.get(RegistrationCategory, category_id)
    if row is None or row.edition_id != edition_id:
        raise NotFound("Registration category not found.")
    return row


def category_payload(row: RegistrationCategory) -> dict:
    return {
        "id": str(row.id),
        "code": row.code,
        "name": row.name,
        "description": row.description,
        "feePaise": row.fee_paise,
        "enabled": row.enabled,
        "displayOrder": row.display_order,
        # Every category carries the printed-pass photo requirement, even if the
        # stored category row predates it. The participant form reads this list,
        # so the photo upload must appear here or it can never be provided.
        "requiredDocuments": _required_docs(row),
    }


def settings_payload(row: RegistrationSettings) -> dict:
    return {
        "registrationEnabled": row.registration_enabled,
        "opensAt": aware(row.opens_at).isoformat() if row.opens_at else None,
        "closesAt": aware(row.closes_at).isoformat() if row.closes_at else None,
        "acceptedFormats": row.accepted_formats or [],
        "maxUploadBytes": row.max_upload_bytes,
        "allowResubmission": row.allow_resubmission,
        "allowDriveLinks": bool(getattr(row, "allow_drive_links", False)),
        "broadcastUrl": getattr(row, "broadcast_url", None) or None,
        "helpdeskPhone": getattr(row, "helpdesk_phone", "+91 94460 00000") or "+91 94460 00000",
        "paymentInstructions": row.payment_instructions,
        "refundPolicy": row.refund_policy,
        "approvalMessage": row.approval_message,
        "rejectionMessage": row.rejection_message,
        "notificationTemplates": row.notification_templates or {},
        "updatedAt": aware(row.updated_at).isoformat() if row.updated_at else None,
    }


def window_state(
    settings: RegistrationSettings | None, edition: ConventionEdition
) -> tuple[bool, str | None]:
    # An edition that is not live cannot take registrations, whatever the
    # dates say. Publishing/draft state is the organiser's off switch.
    if edition is not None and edition.status not in ("published", "open"):
        return False, "Registration is closed for this convention edition."
    if settings is None or not settings.registration_enabled:
        return False, "Registration is currently disabled."
    opens = aware(settings.opens_at or edition.registration_opens_at)
    closes = aware(settings.closes_at or edition.registration_closes_at)
    now = datetime.now(UTC)
    if opens and now < opens:
        return False, f"Registration opens on {opens.isoformat()}."
    if closes and now > closes:
        return False, "Registration has closed."
    return True, None


async def public_config(db: AsyncSession, edition_id: uuid.UUID) -> dict:
    settings = await settings_for(db, edition_id, create=True)
    rows = await categories_for(db, edition_id)
    return {
        "registration": registration_config_payload(settings),
        "categories": [category_payload(row) for row in rows],
        "rejectionReasons": [
            {"code": code, "label": label} for code, label in REJECTION_REASONS.items()
        ],
    }


def registration_config_payload(settings: RegistrationSettings | None) -> dict:
    if settings is None:
        return {
            "registrationEnabled": False,
            "opensAt": None,
            "closesAt": None,
            "acceptedFormats": ["pdf", "jpg", "jpeg", "png"],
            "maxUploadBytes": 5_242_880,
            "allowResubmission": True,
            "allowDriveLinks": False,
            "broadcastUrl": None,
            "helpdeskPhone": "+91 94460 00000",
            "paymentInstructions": "",
            "refundPolicy": "",
            "approvalMessage": "",
            "rejectionMessage": "",
            "notificationTemplates": {},
        }
    return settings_payload(settings)


# --------------------------------------------------------------------------- #
# Documents
# --------------------------------------------------------------------------- #


def _sniff(data: bytes) -> tuple[str, str]:
    if data.startswith(b"\xff\xd8\xff"):
        if not data.rstrip().endswith(b"\xff\xd9"):
            raise AppError(
                "That JPEG file looks incomplete or corrupt.",
                code="FILE_CONTENT_INVALID",
                status_code=415,
            )
        return "image/jpeg", "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        if b"IEND" not in data[-32:]:
            raise AppError(
                "That PNG file looks incomplete or corrupt.",
                code="FILE_CONTENT_INVALID",
                status_code=415,
            )
        return "image/png", "png"
    if data.startswith(b"%PDF"):
        if b"%%EOF" not in data[-2048:]:
            raise AppError(
                "That PDF file looks incomplete or corrupt.",
                code="FILE_CONTENT_INVALID",
                status_code=415,
            )
        return "application/pdf", "pdf"
    raise AppError(
        "Upload a PDF, JPG, JPEG or PNG document.",
        code="FILE_TYPE_NOT_ALLOWED",
        status_code=415,
    )


def _normalise_formats(formats: Iterable[str]) -> set[str]:
    normalised = set()
    for value in formats:
        item = str(value).strip().lower().lstrip(".")
        if item == "jpeg":
            item = "jpg"
        if item:
            normalised.add(item)
    return normalised


def validate_document(
    data: bytes, filename: str | None, settings: RegistrationSettings
) -> tuple[str, str, str]:
    """Validate declared extension, actual bytes and size, returning mime/ext/hash."""
    if not data:
        raise AppError("The uploaded file is empty.", code="FILE_EMPTY", status_code=415)
    limit = min(int(settings.max_upload_bytes or ATTENDEE_DOCUMENT_BYTES), ATTENDEE_DOCUMENT_BYTES)
    if len(data) > limit:
        raise AppError(
            "The document is larger than 500 KB. Please compress your file (under 500 KB) and try again.",
            code="FILE_TOO_LARGE",
            status_code=413,
            details={"maxUploadBytes": limit},
        )
    mime, sniffed_ext = _sniff(data)
    declared = (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
    if declared == "jpeg":
        declared = "jpg"
    if declared and declared != sniffed_ext:
        raise AppError(
            "The file extension does not match its contents.",
            code="FILE_CONTENT_MISMATCH",
            status_code=415,
        )
    accepted = _normalise_formats(settings.accepted_formats or [])
    if sniffed_ext not in accepted:
        raise AppError(
            f"{sniffed_ext.upper()} uploads are not accepted.",
            code="FILE_TYPE_NOT_ALLOWED",
            status_code=415,
            details={"acceptedFormats": sorted(accepted)},
        )
    return mime, sniffed_ext, hashlib.sha256(data).hexdigest()


def document_payload(
    row: RegistrationDocument, edition_id: uuid.UUID, registration_id: uuid.UUID
) -> dict:
    return {
        "id": str(row.id),
        "type": row.doc_type,
        "label": row.label,
        "mime": row.mime,
        "sizeBytes": row.size_bytes,
        "originalName": row.original_name,
        "externalUrl": getattr(row, "external_url", None),
        "status": row.status,
        "reviewNote": row.review_note,
        "uploadedAt": aware(row.uploaded_at).isoformat() if row.uploaded_at else None,
        "contentPath": (
            f"/api/v1/editions/{edition_id}/registration/documents/{row.id}/content"
        ),
        "adminContentPath": (
            f"/api/v1/editions/{edition_id}/admin/registrations/"
            f"{registration_id}/documents/{row.id}/content"
        ),
    }


# --------------------------------------------------------------------------- #
# Notifications
# --------------------------------------------------------------------------- #


def _render(
    db_settings: RegistrationSettings | None, kind: str, values: dict[str, Any]
) -> str:
    templates = (db_settings.notification_templates or {}) if db_settings else {}
    template = templates.get(kind) or DEFAULT_TEMPLATES.get(kind, "{registrationId}")
    safe_values = {
        **values,
        "amount": f"{(values.get('amountPaise') or 0) / 100:,.0f}",
        "reason": values.get("reason") or "see the participant portal",
        "registrationId": values.get("registrationId") or "",
        "category": values.get("category") or "registration",
        "name": values.get("name") or "participant",
    }
    try:
        return template.format(**safe_values)
    except (KeyError, IndexError, ValueError):
        return template


async def notify(
    db: AsyncSession,
    registration: CollegeRegistration,
    kind: str,
    *,
    title: str,
    values: dict[str, Any] | None = None,
    email: bool = True,
) -> RegistrationNotification:
    db_settings = await settings_for(db, registration.edition_id)
    body = _render(db_settings, kind, {**(values or {}), "registrationId": registration.registration_number})
    row = RegistrationNotification(
        edition_id=registration.edition_id,
        user_id=registration.user_id,
        registration_id=registration.id,
        kind=kind,
        title=title,
        body=body,
    )
    db.add(row)
    if email:
        user = await db.get(User, registration.user_id)
        recipient = registration.email or (user.email if user else None)
        if recipient:
            await email_outbox.enqueue(
                db,
                recipient=recipient,
                template=EMAIL_TEMPLATES.get(kind, "registration_update"),
                payload={
                    "message": body,
                    "title": title,
                    "registrationId": registration.registration_number,
                    "kind": kind,
                },
            )
    return row


async def notifications_for(
    db: AsyncSession, user_id: uuid.UUID, edition_id: uuid.UUID
) -> list[RegistrationNotification]:
    return list(
        (
            await db.execute(
                select(RegistrationNotification)
                .where(
                    RegistrationNotification.user_id == user_id,
                    RegistrationNotification.edition_id == edition_id,
                )
                .order_by(RegistrationNotification.created_at.desc())
                .limit(50)
            )
        ).scalars()
    )


def notification_payload(row: RegistrationNotification) -> dict:
    return {
        "id": str(row.id),
        "kind": row.kind,
        "title": row.title,
        "body": row.body,
        "readAt": aware(row.read_at).isoformat() if row.read_at else None,
        "createdAt": aware(row.created_at).isoformat() if row.created_at else None,
    }


# --------------------------------------------------------------------------- #
# Registration state
# --------------------------------------------------------------------------- #


async def registration_for_user(
    db: AsyncSession, user_id: uuid.UUID, edition_id: uuid.UUID
) -> CollegeRegistration | None:
    return (
        await db.execute(
            select(CollegeRegistration).where(
                CollegeRegistration.user_id == user_id,
                CollegeRegistration.edition_id == edition_id,
            )
        )
    ).scalar_one_or_none()


async def registration_by_id(
    db: AsyncSession, edition_id: uuid.UUID, registration_id: uuid.UUID
) -> CollegeRegistration:
    row = await db.get(CollegeRegistration, registration_id)
    if row is None or row.edition_id != edition_id:
        raise NotFound("Registration not found.")
    return row


def overall_state(row: CollegeRegistration) -> str:
    if row.refund_status == "completed":
        # A partial refund leaves the pass alive (money back, entitlement kept).
        # Reporting it as "refunded" hid that the attendee still holds a pass.
        return "refunded" if row.payment_status == "refunded" else "partially_refunded"
    if row.refund_status == "processing":
        return "refund_processing"
    if row.refund_status == "failed":
        # A gateway failure is not the same as "never started": the desk has to
        # retry it. Collapsing both into refund_pending lost that.
        return "refund_failed"
    if row.refund_status == "initiated":
        return "refund_pending"
    return row.verification_status


def _deadline_label(value: datetime | None) -> str:
    if value is None:
        return ""
    return aware(value).strftime("%d %b %Y, %H:%M UTC")


def _set_compliance(row: CollegeRegistration, kind: str) -> datetime:
    """Open a fresh 24-hour window for a desk request.

    A second request (e.g. corrected documents asked for again) restarts the
    window and re-arms enforcement. The old ``compliance_enforced_at`` is kept
    as history only until the new window is enforced.
    """
    now = datetime.now(UTC)
    row.compliance_kind = kind
    row.compliance_flagged_at = now
    row.compliance_deadline_at = now + timedelta(hours=COMPLIANCE_WINDOW_HOURS)
    row.compliance_enforced_at = None
    return row.compliance_deadline_at


def _clear_compliance(row: CollegeRegistration) -> None:
    """Close an active window because the attendee did what was asked.

    The deadline and kind are cleared so neither portal keeps warning about a
    resolved request. ``compliance_enforced_at`` is deliberately left in place
    as history for the desk and the audit trail.
    """
    row.compliance_kind = None
    row.compliance_flagged_at = None
    row.compliance_deadline_at = None
    row.compliance_refund_pass = True
    row.compliance_refund_events = True


def compliance_payload(row: CollegeRegistration) -> dict | None:
    """The 24-hour window in the shape both portals render."""
    if not row.compliance_kind:
        return None
    deadline = aware(row.compliance_deadline_at)
    now = datetime.now(UTC)
    enforced = row.compliance_enforced_at is not None
    overdue = bool(deadline and deadline <= now)
    seconds_left = (deadline - now).total_seconds() if deadline and not enforced else 0
    hours_left = max(0.0, round(seconds_left / 3600, 1))
    kind = row.compliance_kind
    if enforced:
        message = (
            "This request passed its 24-hour deadline. Event seats and team "
            "placement were released, and paid event seats were refunded. "
            "Answer the request, then select your events and team again."
        )
    elif overdue:
        message = (
            "This request passed its 24-hour deadline and is waiting for the "
            "next sweep to release your event seats."
        )
    else:
        message = (
            f"You have {hours_left:g} hour{'s' if hours_left != 1 else ''} left "
            "to answer this request. After that, event seats and team placement "
            "are released and paid event seats are refunded."
        )
    return {
        "kind": kind,
        "label": COMPLIANCE_LABELS.get(kind, "Registration desk request"),
        "flaggedAt": aware(row.compliance_flagged_at).isoformat()
        if row.compliance_flagged_at
        else None,
        "deadlineAt": deadline.isoformat() if deadline else None,
        "enforcedAt": aware(row.compliance_enforced_at).isoformat()
        if row.compliance_enforced_at
        else None,
        "overdue": overdue or enforced,
        "enforced": enforced,
        "hoursRemaining": hours_left,
        "message": message,
    }


def _required_docs(row: RegistrationCategory) -> list[dict]:
    docs = [doc for doc in (row.required_documents or []) if doc.get("type")]
    # The printed pass always carries a photo. Categories configured before the
    # photo requirement existed still get it, so a pass cannot be issued without
    # one.
    if not any(doc.get("type") == "photo" for doc in docs):
        docs.insert(0, dict(PHOTO_REQUIREMENT))
    return docs


def _missing_documents(
    category: RegistrationCategory, documents: list[RegistrationDocument]
) -> list[str]:
    present = {doc.doc_type for doc in documents}
    return [
        doc.get("label") or DOC_DEFINITIONS.get(doc["type"], doc["type"])
        for doc in _required_docs(category)
        if doc.get("required", True) and doc["type"] not in present
    ]


def _can_replace(row: CollegeRegistration, *, allow_resubmission: bool) -> bool:
    if row.payment_status == "refunded" or row.refund_status == "completed":
        return False
    return row.verification_status not in {"approved"}


def _can_submit_documents(row: CollegeRegistration, *, allow_resubmission: bool) -> bool:
    # A refunded registration is closed: uploaded files were stored forever on a
    # booking nobody will review. "initiated" alone is not enough - a rejection
    # that only *parked* the money for finance still lets the attendee resubmit.
    if row.payment_status == "refunded" or row.refund_status in {
        "processing",
        "completed",
    }:
        return False
    if row.payment_status != "paid":
        return True
    if row.verification_status == "approved":
        return False
    if row.verification_status == "rejected":
        return allow_resubmission
    if row.verification_status == "resubmission_required":
        return allow_resubmission
    return True


async def serialize_registration(
    db: AsyncSession,
    row: CollegeRegistration,
    *,
    include_documents: bool = True,
    include_notifications: bool = False,
) -> dict:
    category = await db.get(RegistrationCategory, row.category_id)
    documents = list(
        (
            await db.execute(
                select(RegistrationDocument)
                .where(RegistrationDocument.registration_id == row.id)
                .order_by(RegistrationDocument.doc_type)
            )
        ).scalars()
    )
    order = await db.get(PaymentOrder, row.order_id) if row.order_id else None
    db_settings = await settings_for(db, row.edition_id)
    change = (
        await db.execute(
            select(RegistrationCategoryChange)
            .where(RegistrationCategoryChange.registration_id == row.id)
            .order_by(RegistrationCategoryChange.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    change_category = (
        await db.get(RegistrationCategory, change.to_category_id) if change else None
    )
    missing = _missing_documents(category, documents) if category else []
    allow_resubmission = bool(db_settings.allow_resubmission) if db_settings else True
    docs_config = _required_docs(category) if category else []
    state = overall_state(row)
    payload = {
        "id": str(row.id),
        "registrationNumber": row.registration_number,
        "state": state,
        "category": category_payload(category) if category else None,
        "fullName": row.full_name,
        "email": row.email,
        "phone": row.phone,
        "collegeName": row.college_name,
        "course": row.course,
        "branch": row.branch,
        "yearOfStudy": row.year_of_study,
        "dateOfBirth": row.date_of_birth.isoformat() if row.date_of_birth else None,
        "city": row.city,
        "stateName": row.state,
        "gender": decode_gender(row.gender),
        "foodPreference": decode_food(row.food_preference),
        "needsAccommodation": row.needs_accommodation,
        "feePaise": row.fee_paise,
        "additionalPaidPaise": row.additional_paid_paise,
        "totalPaidPaise": row.fee_paise + row.additional_paid_paise,
        "paymentStatus": row.payment_status,
        "verificationStatus": row.verification_status,
        "refundStatus": row.refund_status,
        "refundAmountPaise": row.refund_amount_paise,
        "collectedPaise": await _collected_paise(db, row),
        "refundablePaise": await _refundable_paise(db, row),
        "transactionId": row.transaction_id,
        "paidAt": aware(row.paid_at).isoformat() if row.paid_at else None,
        "submittedAt": aware(row.submitted_at).isoformat() if row.submitted_at else None,
        "decidedAt": aware(row.decided_at).isoformat() if row.decided_at else None,
        "rejectionCode": row.rejection_code,
        "rejectionReason": row.rejection_reason,
        "requestedDocuments": row.requested_documents or [],
        "resubmissionCount": row.resubmission_count,
        "resubmissionRequestedAt": (
            aware(row.resubmission_requested_at).isoformat()
            if row.resubmission_requested_at
            else None
        ),
        "categoryChangeStatus": row.category_change_status,
        "compliance": compliance_payload(row),
        "complianceKind": row.compliance_kind,
        "complianceDeadlineAt": aware(row.compliance_deadline_at).isoformat()
        if row.compliance_deadline_at
        else None,
        "complianceOverdue": bool(
            row.compliance_deadline_at is not None
            and aware(row.compliance_deadline_at) <= datetime.now(UTC)
        ),
        "documents": [document_payload(doc, row.edition_id, row.id) for doc in documents]
        if include_documents
        else [],
        "documentRequirements": docs_config,
        "missingDocuments": missing,
        "order": (
            {
                "id": str(order.id),
                "status": order.status,
                "amountPaise": order.amount_paise,
                "platformFeePaise": int(getattr(order, "platform_fee_paise", 0) or 0),
                "gatewayOrderId": order.gateway_order_id,
                "purpose": order.purpose,
                "mock": not get_settings().payments_enabled,
                "razorpayKeyId": get_settings().razorpay_key_id,
            }
            if order
            else None
        ),
        "categoryChange": (
            {
                "id": str(change.id),
                "status": change.status,
                "settlementType": change.settlement_type,
                "settlementAmountPaise": change.settlement_amount_paise,
                "note": change.note,
                "adminNote": change.admin_note,
                "toCategory": category_payload(change_category) if change_category else None,
                "toFeePaise": change.to_fee_paise,
                "fromFeePaise": change.from_fee_paise,
                "orderId": str(change.order_id) if change.order_id else None,
                "requestedAt": aware(change.created_at).isoformat()
                if change.created_at
                else None,
                "decidedAt": aware(change.decided_at).isoformat()
                if change.decided_at
                else None,
            }
            if change and change.status != "cancelled"
            else None
        ),
        "canEdit": row.payment_status != "paid" and row.refund_status != "completed",
        "canUpload": _can_submit_documents(row, allow_resubmission=allow_resubmission),
        "canReplace": _can_replace(row, allow_resubmission=allow_resubmission),
        "canResubmit": bool(
            row.payment_status == "paid"
            and allow_resubmission
            and row.verification_status in {"rejected", "resubmission_required"}
        ),
        "canChangeCategory": bool(
            row.payment_status == "paid"
            and row.refund_status != "completed"
            and row.category_change_status != "pending"
        ),
        "canPay": row.payment_status == "pending" and row.verification_status == "payment_pending",
        "canDownloadReceipt": row.payment_status in {"paid", "refunded"},
        "canDownloadConfirmation": row.verification_status == "approved",
        "createdAt": aware(row.created_at).isoformat() if row.created_at else None,
        "updatedAt": aware(row.updated_at).isoformat() if row.updated_at else None,
    }
    if include_notifications:
        payload["notifications"] = [
            notification_payload(item)
            for item in await notifications_for(db, row.user_id, row.edition_id)
        ]
    return payload


# --------------------------------------------------------------------------- #
# Participant writes
# --------------------------------------------------------------------------- #


async def _sync_profile_from_registration(
    db: AsyncSession, user: User, row: CollegeRegistration
) -> None:
    """Keep ParticipantProfile and User aligned with the draft registration."""
    from app.models.user import ParticipantProfile

    if row.full_name:
        user.full_name = row.full_name[:160]
    if row.phone:
        user.phone_e164 = row.phone
    profile = await db.scalar(
        select(ParticipantProfile).where(ParticipantProfile.user_id == user.id)
    )
    if profile is None:
        profile = ParticipantProfile(user_id=user.id)
        db.add(profile)
    profile.college_name = row.college_name or profile.college_name
    profile.course = row.course if row.course is not None else profile.course
    profile.branch = row.branch if row.branch is not None else profile.branch
    if row.year_of_study:
        match = re.search(r"\d+", str(row.year_of_study))
        if match:
            try:
                profile.year_of_study = int(match.group(0))
            except (TypeError, ValueError):
                pass
    if row.date_of_birth is not None:
        profile.date_of_birth = row.date_of_birth
    profile.city = row.city if row.city is not None else profile.city
    profile.state = row.state if row.state is not None else profile.state
    if row.gender is not None:
        profile.gender = row.gender
    if row.food_preference is not None:
        profile.food_preference = row.food_preference
    profile.needs_accommodation = bool(row.needs_accommodation)


async def create_or_update_profile(
    db: AsyncSession,
    request: Request,
    user: User,
    edition: ConventionEdition,
    payload: dict,
) -> CollegeRegistration:
    # Lazy compliance sweep: a participant touching their registration is the
    # natural point to release seats for someone whose 24-hour window expired.
    try:
        async with db.begin_nested():
            await enforce_lapsed_compliance(
                db, edition_id=edition.id, limit=10, request=request
            )
    except Exception:  # noqa: BLE001 - never block a legitimate registration
        logger.warning("lazy_compliance_sweep_failed", exc_info=True)
    db_settings = await settings_for(db, edition.id, create=True)
    open_now, reason = window_state(db_settings, edition)
    category = await category_for(db, edition.id, payload["category_id"])
    if not category.enabled:
        raise ValidationFailed("That registration category is currently disabled.")
    row = await registration_for_user(db, user.id, edition.id)
    if row is not None and row.payment_status == "paid" and row.category_id != category.id:
        raise Conflict(
            "Your registration is already paid. Request a category change instead.",
            code="CATEGORY_CHANGE_REQUIRED",
        )
    if row is not None and (
        row.verification_status == "approved"
        or row.payment_status in ("paid", "completed", "refunded")
    ):
        # Paid/approved registrations are locked; nothing can be self-edited
        # (including meal preference and accommodation) so kitchen/hostel
        # counts stay accurate. Corrections go through the organiser desk.
        raise Conflict(
            "Your registration is locked after payment and cannot be edited. "
            "Ask the organiser desk if any detail needs to be corrected.",
            code="REGISTRATION_LOCKED",
        )
    if row is None and not open_now:
        raise Conflict(reason or "Registration is closed.", code="REGISTRATION_CLOSED")

    allowed_after_payment = {
        "phone",
        "course",
        "branch",
        "year_of_study",
        "city",
        "state",
        # Food and accommodation are logistics, not identity: a paid attendee
        # must still be able to tell the organisers they now need a bed.
        "gender",
        "food_preference",
        "needs_accommodation",
    }
    if row is None:
        row = CollegeRegistration(
            edition_id=edition.id,
            user_id=user.id,
            category_id=category.id,
            category_code=category.code,
            category_name=category.name,
            full_name=payload["full_name"],
            email=payload["email"],
            phone=payload.get("phone"),
            college_name=payload.get("college_name") or "",
            course=payload.get("course"),
            branch=payload.get("branch"),
            year_of_study=payload.get("year_of_study"),
            date_of_birth=payload.get("date_of_birth"),
            city=payload.get("city"),
            state=payload.get("state"),
            gender=encode_gender(payload.get("gender")),
            food_preference=encode_food(payload.get("food_preference")),
            needs_accommodation=bool(payload.get("needs_accommodation")),
            fee_paise=category.fee_paise,
            payment_status="pending",
            verification_status="payment_pending",
            refund_status="not_initiated",
            payment_details={},
        )
        db.add(row)
        await db.flush()
        await _sync_profile_from_registration(db, user, row)
        await record(
            db,
            request,
            actor_id=user.id,
            actor_role="participant",
            action="college_registration.created",
            resource_type="college_registration",
            resource_id=str(row.id),
            after={"category": category.code, "feePaise": category.fee_paise},
        )
        return row

    before = {
        "fullName": row.full_name,
        "email": row.email,
        "category": row.category_code,
        "feePaise": row.fee_paise,
    }
    for field in (
        "phone",
        "course",
        "branch",
        "year_of_study",
        "date_of_birth",
        "city",
        "state",
    ):
        if field in payload:
            setattr(row, field, payload.get(field))
    # Stored as 0/1: the payload carries names, the column carries the code.
    # Once the pass is paid these answers have been counted by the kitchen and
    # the hostel, so a later edit may correct them but never blank them out.
    # The endpoint is a full replace, so an omitted or null answer is a request
    # to remove it: that is refused here instead of being quietly ignored and
    # reported back as if the edit had been stored.
    frozen = row.payment_status in ("paid", "refunded")
    if "gender" in payload:
        code = encode_gender(payload.get("gender"))
        if code is None and frozen and row.gender is not None:
            raise Conflict(
                "Gender cannot be removed once the pass is paid. Pick male or female; "
                "the registration desk can correct a wrong entry.",
                code="LOGISTICS_LOCKED",
            )
        row.gender = code
    if "food_preference" in payload:
        code = encode_food(payload.get("food_preference"))
        if code is None and frozen and row.food_preference is not None:
            raise Conflict(
                "Meal preference cannot be removed once the pass is paid. Pick veg or "
                "non-veg; the registration desk can correct a wrong entry.",
                code="LOGISTICS_LOCKED",
            )
        row.food_preference = code
    if "needs_accommodation" in payload:
        row.needs_accommodation = bool(payload.get("needs_accommodation"))
    if row.payment_status not in ("paid", "refunded"):
        for field in ("full_name", "email", "college_name"):
            if field in payload:
                setattr(row, field, payload.get(field))
        # The selected category defines both the fee and the document set.
        # It is always re-read from the category row, never from a fee field.
        row.category_id = category.id
        row.category_code = category.code
        row.category_name = category.name
        row.fee_paise = category.fee_paise
    else:
        # Paying (or being refunded) locks the bill. Rewriting the category on a
        # refunded row used to change the fee, the receipt and the refund cap
        # while the money had already gone back.
        # Reject attempts to rewrite verified data through this endpoint.
        for field, value in payload.items():
            if field in allowed_after_payment:
                continue
            current = getattr(row, field, None)
            if value is not None and current is not None and str(current) != str(value):
                if field == "full_name" or field == "email" or field == "college_name":
                    raise Conflict(
                        "Identity details cannot be changed after payment. Contact the registration desk.",
                        code="VERIFIED_FIELDS_LOCKED",
                    )
    await _sync_profile_from_registration(db, user, row)
    await db.flush()
    await record(
        db,
        request,
        actor_id=user.id,
        actor_role="participant",
        action="college_registration.profile_updated",
        resource_type="college_registration",
        resource_id=str(row.id),
        before=before,
        after={
            "fullName": row.full_name,
            "email": row.email,
            "category": row.category_code,
            "feePaise": row.fee_paise,
        },
    )
    return row


async def save_document(
    db: AsyncSession,
    request: Request,
    user: User,
    edition: ConventionEdition,
    doc_type: str,
    data: bytes,
    filename: str | None,
) -> RegistrationDocument:
    row = await registration_for_user(db, user.id, edition.id)
    if row is None:
        raise NotFound("Start your registration before uploading documents.")
    db_settings = await settings_for(db, edition.id, create=True)
    category = await db.get(RegistrationCategory, row.category_id)
    if category is None:
        raise NotFound("Registration category not found.")
    config = {item["type"]: item for item in _required_docs(category)}
    # While a category change is pending, the participant must be able to upload
    # the proof the target category needs before the desk approves the change.
    change = await pending_change(db, row.id)
    if change is not None:
        target = await db.get(RegistrationCategory, change.to_category_id)
        if target is not None:
            for item in _required_docs(target):
                config.setdefault(item["type"], item)
    if doc_type not in config or doc_type not in DOC_DEFINITIONS:
        raise ValidationFailed("That document is not part of your registration category.")
    if not _can_submit_documents(
        row, allow_resubmission=bool(db_settings.allow_resubmission)
    ):
        raise Conflict(
            "Your documents are locked while the registration is approved or closed.",
            code="DOCUMENTS_LOCKED",
        )
    mime, ext, digest = validate_document(data, filename, db_settings)
    if doc_type == "photo":
        if len(data) > PHOTO_MAX_BYTES:
            raise AppError(
                "The passport photo must be 100 KB or smaller.",
                code="PHOTO_TOO_LARGE",
                status_code=413,
                details={"maxBytes": PHOTO_MAX_BYTES, "sizeBytes": len(data)},
            )
        if mime not in PHOTO_TYPES:
            raise AppError(
                "Upload the passport photo as a JPG, PNG or WEBP image.",
                code="PHOTO_TYPE_INVALID",
                status_code=415,
            )
    storage = get_document_storage()
    key = registration_document_key(edition.id, row.id, doc_type, filename)
    await storage.put(key, data, mime)

    existing = (
        await db.execute(
            select(RegistrationDocument).where(
                RegistrationDocument.registration_id == row.id,
                RegistrationDocument.doc_type == doc_type,
            )
        )
    ).scalar_one_or_none()
    before = None
    if existing is not None:
        before = {
            "docType": existing.doc_type,
            "sha256": existing.sha256,
            "originalName": existing.original_name,
        }
        old_key = existing.storage_key
        existing.storage_key = key
        existing.external_url = None
        existing.label = config[doc_type].get("label") or DOC_DEFINITIONS[doc_type]
        existing.original_name = (filename or "")[:255] or None
        existing.mime = mime
        existing.size_bytes = len(data)
        existing.sha256 = digest
        existing.status = "pending"
        existing.review_note = None
        existing.uploaded_at = datetime.now(UTC)
        document = existing
        try:
            await storage.delete(old_key)
        except Exception:  # old object cleanup must not lose the new upload
            pass
    else:
        document = RegistrationDocument(
            registration_id=row.id,
            doc_type=doc_type,
            label=config[doc_type].get("label") or DOC_DEFINITIONS[doc_type],
            storage_key=key,
            original_name=(filename or "")[:255] or None,
            mime=mime,
            size_bytes=len(data),
            sha256=digest,
            status="pending",
        )
        db.add(document)
    row.last_document_at = datetime.now(UTC)
    if row.verification_status in {"rejected", "resubmission_required"}:
        # Uploading a correction does not silently approve anything; the user
        # explicitly requests re-verification afterwards.
        document.status = "pending"
    await db.flush()
    await record(
        db,
        request,
        actor_id=user.id,
        actor_role="participant",
        action="college_registration.document_uploaded",
        resource_type="college_registration",
        resource_id=str(row.id),
        before=before,
        after={"docType": doc_type, "sha256": digest, "sizeBytes": len(data)},
    )
    return document


def _validate_google_drive_url(raw_url: str) -> str:
    """Validate that a submitted URL is an https Google Drive / Docs file link."""
    import re
    from urllib.parse import urlparse

    url = (raw_url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.lower() not in {
        "drive.google.com",
        "docs.google.com",
    }:
        raise ValidationFailed(
            "Enter a valid https://drive.google.com or https://docs.google.com file URL."
        )
    has_id = bool(
        re.search(r"/d/[A-Za-z0-9_-]{10,}", parsed.path)
        or re.search(r"(?:^|&)id=[A-Za-z0-9_-]{10,}", parsed.query)
    )
    if not has_id:
        raise ValidationFailed(
            "Paste the exact Google Drive file share URL (for example, https://drive.google.com/file/d/.../view)."
        )
    return url


async def save_document_link(
    db: AsyncSession,
    request: Request,
    user: User,
    edition: ConventionEdition,
    doc_type: str,
    url: str,
) -> RegistrationDocument:
    row = await registration_for_user(db, user.id, edition.id)
    if row is None:
        raise NotFound("Start your registration before submitting documents.")
    db_settings = await settings_for(db, edition.id, create=True)
    if not getattr(db_settings, "allow_drive_links", False):
        raise Conflict(
            "Google Drive document links are not enabled for this edition.",
            code="DRIVE_LINKS_DISABLED",
        )
    category = await db.get(RegistrationCategory, row.category_id)
    if category is None:
        raise NotFound("Registration category not found.")
    config = {item["type"]: item for item in _required_docs(category)}
    change = await pending_change(db, row.id)
    if change is not None:
        target = await db.get(RegistrationCategory, change.to_category_id)
        if target is not None:
            for item in _required_docs(target):
                config.setdefault(item["type"], item)
    if doc_type not in config or doc_type not in DOC_DEFINITIONS:
        raise ValidationFailed("That document is not part of your registration category.")
    if not _can_submit_documents(
        row, allow_resubmission=bool(db_settings.allow_resubmission)
    ):
        raise Conflict(
            "Your documents are locked while the registration is approved or closed.",
            code="DOCUMENTS_LOCKED",
        )

    clean_url = _validate_google_drive_url(url)
    digest = hashlib.sha256(clean_url.encode("utf-8")).hexdigest()

    existing = (
        await db.execute(
            select(RegistrationDocument).where(
                RegistrationDocument.registration_id == row.id,
                RegistrationDocument.doc_type == doc_type,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        old_key = existing.storage_key
        existing.storage_key = "external:drive"
        existing.external_url = clean_url
        existing.label = config[doc_type].get("label") or DOC_DEFINITIONS[doc_type]
        existing.original_name = "Google Drive Link"
        existing.mime = "text/uri-list"
        existing.size_bytes = 0
        existing.sha256 = digest
        existing.status = "pending"
        existing.review_note = None
        existing.uploaded_at = datetime.now(UTC)
        document = existing
        if old_key and not old_key.startswith("external:"):
            try:
                await get_document_storage().delete(old_key)
            except Exception:
                pass
    else:
        document = RegistrationDocument(
            registration_id=row.id,
            doc_type=doc_type,
            label=config[doc_type].get("label") or DOC_DEFINITIONS[doc_type],
            storage_key="external:drive",
            external_url=clean_url,
            original_name="Google Drive Link",
            mime="text/uri-list",
            size_bytes=0,
            sha256=digest,
            status="pending",
        )
        db.add(document)

    row.last_document_at = datetime.now(UTC)
    await db.flush()
    await record(
        db,
        request,
        actor_id=user.id,
        actor_role="participant",
        action="college_registration.document_link_saved",
        resource_type="college_registration",
        resource_id=str(row.id),
        after={"docType": doc_type, "externalUrl": clean_url},
    )
    return document


async def document_for_user(
    db: AsyncSession, user_id: uuid.UUID, edition_id: uuid.UUID, document_id: uuid.UUID
) -> RegistrationDocument:
    document = await db.get(RegistrationDocument, document_id)
    if document is None:
        raise NotFound("Document not found.")
    registration = await db.get(CollegeRegistration, document.registration_id)
    if (
        registration is None
        or registration.user_id != user_id
        or registration.edition_id != edition_id
    ):
        raise NotFound("Document not found.")
    return document


async def delete_document(
    db: AsyncSession,
    request: Request,
    user: User,
    edition: ConventionEdition,
    doc_type: str,
) -> CollegeRegistration:
    """Delete a participant document from Supabase storage and the database."""
    row = await registration_for_user(db, user.id, edition.id)
    if row is None:
        raise NotFound("No registration found.")
    db_settings = await settings_for(db, edition.id, create=True)
    if not _can_submit_documents(
        row, allow_resubmission=bool(db_settings.allow_resubmission)
    ):
        raise Conflict(
            "Your documents are locked while the registration is approved or closed.",
            code="DOCUMENTS_LOCKED",
        )
    existing = (
        await db.execute(
            select(RegistrationDocument).where(
                RegistrationDocument.registration_id == row.id,
                RegistrationDocument.doc_type == doc_type,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        storage = get_document_storage()
        try:
            await storage.delete(existing.storage_key)
        except Exception as exc:
            logger.warning(
                "storage_delete_failed key=%s error=%s", existing.storage_key, exc
            )
        before = {
            "docType": existing.doc_type,
            "sha256": existing.sha256,
            "originalName": existing.original_name,
        }
        await db.delete(existing)
        row.last_document_at = datetime.now(UTC)
        await db.flush()
        await record(
            db,
            request,
            actor_id=user.id,
            actor_role="participant",
            action="college_registration.document_deleted",
            resource_type="college_registration",
            resource_id=str(row.id),
            before=before,
            after=None,
        )
    return row


async def submit_for_payment(
    db: AsyncSession,
    request: Request,
    user: User,
    edition: ConventionEdition,
) -> tuple[CollegeRegistration, PaymentOrder | None]:
    # A new checkout is another natural sweep point: the next registration in
    # the system releases seats of attendees who ignored their 24-hour window.
    try:
        async with db.begin_nested():
            await enforce_lapsed_compliance(
                db, edition_id=edition.id, limit=10, request=request
            )
    except Exception:  # noqa: BLE001 - never block a legitimate registration
        logger.warning("lazy_compliance_sweep_failed", exc_info=True)
    row = await registration_for_user(db, user.id, edition.id)
    if row is None:
        raise NotFound("Complete your registration details first.")
    db_settings = await settings_for(db, edition.id, create=True)
    open_now, reason = window_state(db_settings, edition)
    if row.payment_status == "paid":
        raise Conflict("This registration has already been paid.", code="ALREADY_PAID")
    # Closed registrations cannot take fresh money. Without these guards the
    # endpoint happily created a new order for a refunded/rejected registration
    # and the capture then had nowhere to go.
    if row.payment_status == "refunded" or row.refund_status in {
        "initiated",
        "processing",
        "completed",
    }:
        raise Conflict(
            "This registration has been refunded or is under refund.",
            code="ALREADY_REFUNDED",
        )
    if row.verification_status == "rejected":
        raise Conflict(
            "This registration was rejected. Contact the registration desk.",
            code="ALREADY_REJECTED",
        )
    if not open_now:
        raise Conflict(reason or "Registration is closed.", code="REGISTRATION_CLOSED")
    category = await db.get(RegistrationCategory, row.category_id)
    if category is None or not category.enabled:
        raise Conflict("This registration category is no longer available.")
    documents = list(
        (
            await db.execute(
                select(RegistrationDocument).where(
                    RegistrationDocument.registration_id == row.id
                )
            )
        ).scalars()
    )
    missing = _missing_documents(category, documents)
    if missing:
        raise ValidationFailed(
            "Upload all mandatory documents before paying.",
            code="DOCUMENTS_MISSING",
            details={"missing": missing},
        )

    # Mandatory Attendee Details Validation
    missing_fields = []
    if not (row.full_name and row.full_name.strip()):
        missing_fields.append("Full Name")
    if not (row.email and row.email.strip()):
        missing_fields.append("Email Address")
    if not (row.phone and row.phone.strip()):
        missing_fields.append("Mobile Phone")
    if not (row.college_name and row.college_name.strip()):
        missing_fields.append("College Name")
    if not (row.branch and row.branch.strip()):
        missing_fields.append("Branch / Department")
    if not (row.year_of_study and row.year_of_study.strip()):
        missing_fields.append("Year of Study")
    # Gender and meal are operational answers, not decoration: the kitchen cooks
    # to the counts and the hostel allocates beds from them. Enforced here, not
    # only in the form, so no client can buy a pass while skipping them.
    if row.gender is None:
        missing_fields.append("Gender")
    if row.food_preference is None:
        missing_fields.append("Meal Preference")

    if missing_fields:
        raise ValidationFailed(
            f"Please complete all mandatory attendee details before paying: {', '.join(missing_fields)}.",
            code="MANDATORY_DETAILS_MISSING",
            details={"missingFields": missing_fields},
        )

    # The fee is always read from the database category row. A request body is
    # never used to decide the amount.
    amount = int(category.fee_paise)
    row.fee_paise = amount
    row.category_name = category.name
    row.category_code = category.code

    from app.services.editions import current_policy
    from app.services.payments import attach_gateway_order, calculate_platform_fee

    try:
        policy = await current_policy(db, edition.id)
    except NotFound:
        policy = None
    platform_fee, total_amount = calculate_platform_fee(amount, policy)

    existing_order = await db.get(PaymentOrder, row.order_id) if row.order_id else None
    if (
        existing_order is not None
        and existing_order.status == "created"
        and existing_order.amount_paise == total_amount
        and int(getattr(existing_order, "platform_fee_paise", 0) or 0) == platform_fee
        and existing_order.purpose == "college_registration"
    ):
        order = existing_order
        await attach_gateway_order(db, order)
    else:
        # The order being replaced must stop being payable. It kept a live
        # gateway order id, so an attendee with the old checkout still open (or a
        # bookmark) could pay it, and that capture then rolled the whole webhook
        # back on an amount mismatch - an endless retry with the money missing.
        if existing_order is not None and existing_order.status in ("created", "pending"):
            existing_order.status = "expired"
        order = PaymentOrder(
            edition_id=edition.id,
            user_id=user.id,
            purpose="college_registration",
            amount_paise=total_amount,
            platform_fee_paise=platform_fee,
            status="created",
            linked_record_id=row.id,
        )
        db.add(order)
        await db.flush()
        row.order_id = order.id
        await attach_gateway_order(db, order)
    row.submitted_at = datetime.now(UTC)
    await db.flush()
    await record(
        db,
        request,
        actor_id=user.id,
        actor_role="participant",
        action="college_registration.payment_started",
        resource_type="college_registration",
        resource_id=str(row.id),
        after={"category": category.code, "amountPaise": amount, "orderId": str(order.id)},
    )
    return row, order


async def _record_late_refund(
    db: AsyncSession, row: CollegeRegistration, order: PaymentOrder, why: str
) -> None:
    """Record money that arrived after the registration was already closed.

    The old behaviour logged a warning and returned, so the payment existed only
    in ``payment_transactions`` and on the gateway. A pending refund row puts it
    in the finance ledger, and the attendee is told what will happen.
    """
    already_committed = (
        (
            await db.execute(
                select(func.coalesce(func.sum(Refund.amount_paise), 0)).where(
                    Refund.order_id == order.id,
                    Refund.status.in_(["pending", "processing", "processed"]),
                )
            )
        )
        .scalars()
        .one()
    ) or 0
    available = int(order.amount_paise) - int(already_committed)
    if available > 0:
        db.add(
            Refund(
                order_id=order.id,
                amount_paise=available,
                reason_code="late_payment",
                reason_note=f"Payment captured after the registration was closed: {why}",
                status="pending",
            )
        )
    if row.refund_status == "not_initiated":
        row.refund_status = "initiated"
    logger.warning(
        "late_payment_recorded registration=%s order=%s refund=%s",
        row.id,
        order.id,
        row.refund_status,
    )
    await db.flush()
    await notify(
        db,
        row,
        "refund_initiated",
        title="Payment received after your registration was closed",
        values={
            "amountPaise": order.amount_paise,
            "category": row.category_name,
            "reason": why,
        },
    )


async def finalize_paid(
    db: AsyncSession, order: PaymentOrder, transaction_id: str | None = None
) -> CollegeRegistration | None:
    """Called exactly once per successful payment by the payment service."""
    row = await db.get(CollegeRegistration, order.linked_record_id) if order.linked_record_id else None
    if row is None:
        row = (
            await db.execute(
                select(CollegeRegistration).where(CollegeRegistration.order_id == order.id)
            )
        ).scalar_one_or_none()
    if row is None:
        return None
    # A rejected registration keeps its rejection even when money arrives later.
    # The desk closed it (and its open order) for a reason; the payment is
    # recorded and queued for a refund instead of being dropped on the floor.
    if row.verification_status == "rejected":
        await _record_late_refund(db, row, order, "registration rejected before payment arrived")
        return row
    # A refunded (or refund-in-progress) registration must never be revived by
    # a late/replayed payment callback.
    if row.refund_status in {"initiated", "processing", "completed"} or row.payment_status == "refunded":
        await _record_late_refund(db, row, order, "registration already refunded")
        return row
    if row.verification_status != "payment_pending" and row.payment_status == "paid":
        # `mark_order_paid` already returns early for a settled order, so reaching
        # here with money paid means a *second* order for the same registration
        # was charged. That is new money, not a replay: park it for refund.
        await _record_late_refund(
            db, row, order, "duplicate payment for an already paid registration"
        )
        return row
    order_base = int(order.amount_paise) - int(getattr(order, "platform_fee_paise", 0) or 0)
    if order_base != row.fee_paise:
        # Raising here rolled back the paid order, the transaction row and the
        # webhook, so a captured payment for a replaced/edited order could never
        # be recorded and Razorpay retried forever. The money is real: park it.
        await _record_late_refund(
            db, row, order, "the paid amount no longer matches the registration fee"
        )
        return row
    row.payment_status = "paid"
    row.paid_at = datetime.now(UTC)
    row.transaction_id = transaction_id or order.gateway_order_id or f"pay_{uuid.uuid4().hex[:12]}"
    row.payment_details = {
        "orderId": str(order.id),
        "gatewayOrderId": order.gateway_order_id,
        "amountPaise": order.amount_paise,
        "platformFeePaise": int(getattr(order, "platform_fee_paise", 0) or 0),
        "currency": order.currency,
        "mock": not get_settings().payments_enabled,
        "transactionId": row.transaction_id,
    }
    if not row.registration_number:
        row.registration_number = await _unique_registration_number(db)
    row.verification_status = "pending_verification"
    row.submitted_at = row.submitted_at or datetime.now(UTC)

    # The college registration IS the attendee's convention pass. Mirror the paid
    # registration into the pass/ticket tables so event selection, the entry
    # ticket and team registration unlock without a second purchase.
    #
    # A pass that cannot be created is a paid attendee who cannot enter, so this
    # is not swallowed silently any more: the caller is told to retry. The
    # webhook path catches it below (``finalize_paid`` callers decide), and the
    # order stays paid so a retry is safe.
    from app.services.editions import current_policy
    from app.services.passes import activate_pass_for_registration

    policy = await current_policy(db, row.edition_id)
    try:
        await activate_pass_for_registration(
            db, row.user_id, row.edition_id, policy, row.fee_paise
        )
    except Exception as exc:
        logger.exception("pass_activation_failed registration=%s", row.id)
        raise AppError(
            "Payment received, but the convention pass could not be created. "
            "The desk has been notified; retry the payment confirmation.",
            code="PASS_ACTIVATION_FAILED",
            status_code=500,
        ) from exc

    # The purchase form is the single place an attendee fills these details, so
    # mirror them into the account profile instead of leaving the profile empty.
    try:
        from app.models.user import ParticipantProfile

        user = await db.get(User, row.user_id)
        if user is not None:
            if row.full_name and row.full_name != user.full_name:
                user.full_name = row.full_name
            if row.phone:
                user.phone_e164 = row.phone
            profile = (
                await db.execute(
                    select(ParticipantProfile).where(
                        ParticipantProfile.user_id == row.user_id
                    )
                )
            ).scalar_one_or_none()
            if profile is None:
                profile = ParticipantProfile(user_id=row.user_id)
                db.add(profile)
            profile.college_name = row.college_name or profile.college_name
            profile.course = row.course or profile.course
            profile.branch = row.branch or profile.branch
            if row.year_of_study:
                try:
                    profile.year_of_study = int(str(row.year_of_study).strip()[:1])
                except (TypeError, ValueError):
                    pass
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "profile_sync_failed registration=%s error=%s", row.id, exc
        )

    await db.flush()
    await notify(
        db,
        row,
        "payment_success",
        title="Payment received",
        values={"amountPaise": row.fee_paise, "category": row.category_name},
    )
    await notify(
        db,
        row,
        "submitted",
        title="Registration submitted for verification",
        values={"category": row.category_name},
    )
    cache_delete_pattern("admin:dashboard:*")
    cache_delete_pattern("public:*")
    return row


async def _unique_registration_number(db: AsyncSession) -> str:
    for _ in range(10):
        candidate = f"PX-{datetime.now(UTC).strftime('%y')}-{secrets.token_hex(3).upper()}"
        exists = (
            await db.execute(
                select(CollegeRegistration.id).where(
                    CollegeRegistration.registration_number == candidate
                )
            )
        ).scalar_one_or_none()
        if exists is None:
            return candidate
    return f"PX-{uuid.uuid4().hex[:8].upper()}"


async def verify_checkout_payment(
    db: AsyncSession,
    request: Request,
    user: User,
    edition_id: uuid.UUID,
    *,
    order_id: uuid.UUID,
    payment_id: str,
    signature: str,
) -> CollegeRegistration:
    settings = get_settings()
    row = await registration_for_user(db, user.id, edition_id)
    if row is None or row.order_id != order_id:
        raise NotFound("Payment order not found.")
    order = await db.get(PaymentOrder, order_id)
    if order is None:
        raise NotFound("Payment order not found.")

    # Idempotency check: if already verified or marked paid by webhook/previous call, return safely
    if row.payment_status == "paid" or order.status == "paid":
        return row
    from app.services.payments import (
        fetch_gateway_payment,
        mark_order_paid,
        verify_checkout_signature,
    )

    if not settings.payments_enabled:
        raise AppError(
            "Online payment verification is not available in this environment.",
            code="PAYMENTS_DISABLED",
            status_code=400,
        )
    if not verify_checkout_signature(order.gateway_order_id or "", payment_id, signature):
        raise AppError(
            "The payment signature could not be verified.",
            code="PAYMENT_SIGNATURE_INVALID",
            status_code=400,
        )
    gateway_payment = await fetch_gateway_payment(payment_id)
    if (
        gateway_payment.get("order_id") != order.gateway_order_id
        or int(gateway_payment.get("amount") or 0) != order.amount_paise
        or gateway_payment.get("status") not in {"captured", "authorized"}
    ):
        raise AppError(
            "The payment could not be confirmed with the gateway.",
            code="PAYMENT_NOT_CONFIRMED",
            status_code=409,
        )
    await mark_order_paid(db, order, transaction_id=payment_id)
    refreshed = await db.get(CollegeRegistration, row.id)
    assert refreshed is not None
    await record(
        db,
        request,
        actor_id=user.id,
        actor_role="participant",
        action="college_registration.payment_verified",
        resource_type="college_registration",
        resource_id=str(refreshed.id),
        after={"transactionId": payment_id, "amountPaise": order.amount_paise},
    )

    try:
        from app.services.telegram import send_telegram_registration, track_telegram_task
        category = await db.get(RegistrationCategory, row.category_id)
        track_telegram_task(
            send_telegram_registration(
                full_name=row.full_name or user.full_name or "Attendee",
                email=row.email or user.email or "",
                phone=row.phone or "",
                college=row.college_name or "College Student",
                tier_name=category.name if category else "Pass Tier",
                amount_paid=f"₹{order.amount_paise / 100:.2f}",
                # CollegeRegistration has no reference_number; the registration
                # number is what the desk and the attendee recognise.
                reference=row.registration_number,
            ),
            name="parallax-registration-telegram-alert",
        )
    except Exception:
        pass

    return refreshed


async def resubmit(
    db: AsyncSession, request: Request, user: User, edition_id: uuid.UUID
) -> CollegeRegistration:
    row = await registration_for_user(db, user.id, edition_id)
    if row is None:
        raise NotFound("Registration not found.")
    db_settings = await settings_for(db, edition_id, create=True)
    if not db_settings.allow_resubmission:
        raise Conflict("Resubmission is disabled for this edition.", code="RESUBMISSION_DISABLED")
    if row.payment_status != "paid":
        raise Conflict("Complete the payment before requesting verification.")
    if row.refund_status in {"initiated", "processing", "completed"}:
        if not await _cancel_parked_refunds(db, row):
            raise Conflict(
                "A refund is already in progress or completed for this registration.",
                code="REFUND_IN_PROGRESS",
            )
    if row.verification_status not in {"rejected", "resubmission_required"}:
        raise Conflict("Only a rejected registration can be resubmitted.")
    category = await db.get(RegistrationCategory, row.category_id)
    documents = list(
        (
            await db.execute(
                select(RegistrationDocument).where(
                    RegistrationDocument.registration_id == row.id
                )
            )
        ).scalars()
    )
    missing = _missing_documents(category, documents) if category else []
    if missing:
        raise ValidationFailed(
            "Upload the corrected mandatory documents first.",
            code="DOCUMENTS_MISSING",
            details={"missing": missing},
        )
    row.verification_status = "pending_verification"
    row.rejection_reason = None
    row.rejection_code = None
    row.requested_documents = []
    row.resubmission_count += 1
    row.resubmission_requested_at = None
    row.decided_at = None
    row.decided_by = None
    _clear_compliance(row)
    for document in documents:
        document.status = "pending"
        document.review_note = None
    await db.flush()
    await notify(
        db,
        row,
        "submitted",
        title="Re-verification requested",
        values={"category": row.category_name},
    )
    await record(
        db,
        request,
        actor_id=user.id,
        actor_role="participant",
        action="college_registration.resubmitted",
        resource_type="college_registration",
        resource_id=str(row.id),
        after={"resubmissionCount": row.resubmission_count},
    )
    return row


async def request_category_change(
    db: AsyncSession,
    request: Request,
    user: User,
    edition_id: uuid.UUID,
    category_id: uuid.UUID,
    note: str | None,
) -> RegistrationCategoryChange:
    row = await registration_for_user(db, user.id, edition_id)
    if row is None:
        raise NotFound("Registration not found.")
    if row.payment_status != "paid":
        raise Conflict("Category can be changed directly before payment.")
    if row.verification_status == "rejected":
        raise Conflict(
            "A rejected registration cannot change category.",
            code="ALREADY_REJECTED",
        )
    if row.refund_status in {"initiated", "processing", "completed"}:
        raise Conflict("A refunded registration cannot change category.")
    target = await category_for(db, edition_id, category_id)
    if not target.enabled:
        raise ValidationFailed("That registration category is disabled.")
    if target.id == row.category_id:
        raise ValidationFailed("That is already your registration category.")
    # One change at a time, including one that is approved but not paid yet.
    outstanding = await awaiting_change(db, row.id)
    if outstanding is not None or row.category_change_status == "awaiting_payment":
        raise Conflict(
            "A category change is already approved and waiting for its payment. "
            "Pay or cancel it before requesting another.",
            code="CATEGORY_CHANGE_OUTSTANDING",
        )
    pending = (
        await db.execute(
            select(RegistrationCategoryChange).where(
                RegistrationCategoryChange.registration_id == row.id,
                RegistrationCategoryChange.status == "pending",
            )
        )
    ).scalar_one_or_none()
    if pending is not None:
        raise Conflict("A category change request is already pending review.")
    change = RegistrationCategoryChange(
        registration_id=row.id,
        from_category_id=row.category_id,
        to_category_id=target.id,
        from_fee_paise=row.fee_paise,
        to_fee_paise=target.fee_paise,
        settlement_type="pending_review",
        settlement_amount_paise=abs(target.fee_paise - row.fee_paise),
        status="pending",
        note=note,
    )
    db.add(change)
    row.category_change_status = "pending"
    row.requested_category_id = target.id
    try:
        # The pending check above is a select, so two simultaneous requests can
        # both pass it. The partial unique index on pending changes turns the
        # loser into a clean conflict instead of a duplicate row.
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise Conflict(
            "A category change request is already pending review.",
            code="CATEGORY_CHANGE_OUTSTANDING",
        ) from None
    await record(
        db,
        request,
        actor_id=user.id,
        actor_role="participant",
        action="college_registration.category_change_requested",
        resource_type="college_registration",
        resource_id=str(row.id),
        before={"category": row.category_code, "feePaise": row.fee_paise},
        after={"category": target.code, "feePaise": target.fee_paise},
    )
    return change


# --------------------------------------------------------------------------- #
# Admin decisions
# --------------------------------------------------------------------------- #


async def add_note(
    db: AsyncSession,
    request: Request,
    row: CollegeRegistration,
    note: str,
    actor: User,
    actor_role: str,
) -> None:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    line = f"[{stamp}] {actor.full_name or actor.email}: {note.strip()}"
    row.admin_notes = f"{row.admin_notes}\n{line}" if row.admin_notes else line
    await record(
        db,
        request,
        actor_id=actor.id,
        actor_role=actor_role,
        action="college_registration.note_added",
        resource_type="college_registration",
        resource_id=str(row.id),
        after={"note": note.strip()},
    )
    await db.flush()


async def admin_update_details(
    db: AsyncSession,
    request: Request,
    row: CollegeRegistration,
    payload: dict[str, Any],
    actor: User,
    actor_role: str,
) -> CollegeRegistration:
    """Allow an authorized admin to correct participant details without disrupting auth or passes."""
    before = {
        "fullName": row.full_name,
        "phone": row.phone,
        "collegeName": row.college_name,
        "course": row.course,
        "branch": row.branch,
        "yearOfStudy": row.year_of_study,
        "city": row.city,
        "state": row.state,
        "gender": row.gender,
        "foodPreference": row.food_preference,
        "needsAccommodation": row.needs_accommodation,
    }

    row.full_name = payload["full_name"].strip()
    row.college_name = payload["college_name"].strip()
    for field in ("phone", "course", "branch", "year_of_study", "date_of_birth", "city", "state"):
        if field in payload:
            val = payload.get(field)
            setattr(row, field, val.strip() if isinstance(val, str) else val)

    if "gender" in payload:
        code = encode_gender(payload.get("gender"))
        if code is not None or row.payment_status not in ("paid", "refunded"):
            row.gender = code
    if "food_preference" in payload:
        code = encode_food(payload.get("food_preference"))
        if code is not None or row.payment_status not in ("paid", "refunded"):
            row.food_preference = code
    if "needs_accommodation" in payload:
        row.needs_accommodation = bool(payload.get("needs_accommodation"))

    # Keep User and ParticipantProfile in sync without touching auth email.
    user = await db.get(User, row.user_id)
    if user is not None:
        user.full_name = row.full_name
        if row.phone:
            user.phone_e164 = row.phone

    profile = (
        await db.execute(
            select(ParticipantProfile).where(ParticipantProfile.user_id == row.user_id)
        )
    ).scalar_one_or_none()
    if profile is not None:
        profile.college_name = row.college_name
        profile.course = row.course
        profile.branch = row.branch
        profile.city = row.city
        profile.state = row.state
        profile.gender = row.gender
        profile.food_preference = row.food_preference
        profile.needs_accommodation = row.needs_accommodation
        if row.year_of_study:
            try:
                yr = int(str(row.year_of_study).strip()[:1])
                if 1 <= yr <= 6:
                    profile.year_of_study = yr
            except ValueError:
                pass

    await record(
        db,
        request,
        actor_id=actor.id,
        actor_role=actor_role,
        action="college_registration.details_updated",
        resource_type="college_registration",
        resource_id=str(row.id),
        before=before,
        after={
            "fullName": row.full_name,
            "collegeName": row.college_name,
            "branch": row.branch,
            "yearOfStudy": row.year_of_study,
        },
    )
    await db.flush()
    return row


async def _close_open_orders(
    db: AsyncSession, user_id: uuid.UUID, edition_id: uuid.UUID
) -> int:
    """Expire every checkout this attendee has not paid yet.

    Used whenever the attendee loses the right to pay: a rejection. Without it
    the still-open Razorpay order stayed payable and the payment then revived
    the registration it was supposed to close.
    """
    from app.models.commerce import PaymentOrder

    orders = list(
        (
            await db.execute(
                select(PaymentOrder).where(
                    PaymentOrder.user_id == user_id,
                    PaymentOrder.edition_id == edition_id,
                    PaymentOrder.status == "created",
                )
            )
        ).scalars()
    )
    for order in orders:
        order.status = "expired"
    if orders:
        await db.flush()
    return len(orders)


async def _cancel_parked_refunds(db: AsyncSession, row: CollegeRegistration) -> bool:
    """Withdraw a refund that was only *requested* (no money moved yet).

    A rejection parks the pass money as a pending ledger row when the operator
    cannot or will not refund on the spot. Reinstating the registration - by
    approving it or by accepting a resubmission - must withdraw that request,
    otherwise the parked row blocks the desk forever.
    """
    if row.refund_status != "initiated":
        return False
    parked = list(
        (
            await db.execute(
                select(Refund).where(
                    Refund.order_id.in_(await _refund_order_ids(db, row)),
                    Refund.status == "pending",
                )
            )
        ).scalars()
    )
    if not parked:
        return False
    for request_row in parked:
        request_row.status = "cancelled"
        note_suffix = "Cancelled: registration reinstated."
        request_row.reason_note = (
            request_row.reason_note + chr(10) + note_suffix
            if request_row.reason_note
            else note_suffix
        )
    row.refund_status = "not_initiated"
    row.refund_id = None
    row.refund_amount_paise = 0
    await db.flush()
    return True


async def approve(
    db: AsyncSession,
    request: Request,
    row: CollegeRegistration,
    actor: User,
    actor_role: str,
    notes: str | None = None,
) -> CollegeRegistration:
    if row.payment_status != "paid":
        raise Conflict("Only a paid registration can be approved.", code="PAYMENT_REQUIRED")
    if row.refund_status in {"completed", "processing", "initiated", "failed"}:
        if not await _cancel_parked_refunds(db, row):
            raise Conflict("A registration under refund cannot be approved.")
    if row.verification_status == "approved":
        # Approving twice used to re-notify the attendee and re-run the pass
        # reactivation (a second "approved" email for one decision).
        return row
    category = await db.get(RegistrationCategory, row.category_id)
    # The desk can withdraw a category while applications are still open, so
    # an approval must not land in a category that is no longer offered.
    if category is not None and not category.enabled:
        raise Conflict(
            "This category has been withdrawn. Move the registration to an open category first.",
            code="CATEGORY_DISABLED",
        )
    documents = list(
        (
            await db.execute(
                select(RegistrationDocument).where(
                    RegistrationDocument.registration_id == row.id
                )
            )
        ).scalars()
    )
    missing = _missing_documents(category, documents) if category else []
    if missing:
        raise Conflict(
            "Mandatory documents are still missing: " + ", ".join(missing),
            code="DOCUMENTS_MISSING",
        )
    if category is not None and category.code == "iste_member":
        iste = next((doc for doc in documents if doc.doc_type == "iste_card"), None)
        if iste is None:
            raise Conflict(
                "An ISTE membership card must be on file before approving this category.",
                code="ISTE_PROOF_REQUIRED",
            )
    row.verification_status = "approved"
    row.decided_at = datetime.now(UTC)
    row.decided_by = actor.id
    row.rejection_code = None
    row.rejection_reason = None
    row.requested_documents = []
    _clear_compliance(row)
    if notes and notes.strip():
        stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        line = f"[{stamp}] {actor.full_name or actor.email} (approval): {notes.strip()}"
        row.admin_notes = f"{row.admin_notes}\n{line}" if row.admin_notes else line
    for document in documents:
        document.status = "verified"
    await db.flush()
    # Approving a previously rejected registration cancelled its pass; make
    # the pass and entry ticket active again explicitly instead of waiting
    # for the portal's self-heal to notice on the next visit.
    from app.services.editions import current_policy
    from app.services.passes import activate_pass_for_registration
    try:
        await activate_pass_for_registration(
            db, row.user_id, row.edition_id, await current_policy(db, row.edition_id), row.fee_paise
        )
    except Exception as exc:
        # An approval without a pass is a paid attendee who cannot enter, so the
        # desk must see it instead of a green toast. The transaction rolls back,
        # leaving the registration approved-pending a retry.
        logger.exception("approve_pass_reactivation_failed reg=%s", row.id)
        raise AppError(
            "Registration approved, but the convention pass could not be activated. "
            "Retry the approval or contact support.",
            code="PASS_ACTIVATION_FAILED",
            status_code=500,
        ) from exc
    # Rejecting cancelled every included event seat. Approving brings the pass
    # back, so the seats the attendee still sees as selected must come back
    # with it - otherwise the door pass works but the event desk says "not
    # registered" for events the portal still lists.
    from app.services.passes import selections_for, sync_included_registrations

    user_pass = (
        await db.execute(
            select(ConventionPass)
            .where(
                ConventionPass.user_id == row.user_id,
                ConventionPass.edition_id == row.edition_id,
            )
            .order_by(ConventionPass.created_at.desc())
            .limit(1)
        )
    ).scalars().first()
    if user_pass is not None and user_pass.status == "active":
        try:
            await sync_included_registrations(
                db, user_pass, await selections_for(db, user_pass.id)
            )
        except Exception as exc:
            logger.warning("approve_selection_resync_failed reg=%s err=%s", row.id, exc)
    await notify(
        db,
        row,
        "approved",
        title="Registration approved",
        values={"category": row.category_name},
    )
    await record(
        db,
        request,
        actor_id=actor.id,
        actor_role=actor_role,
        action="college_registration.approved",
        resource_type="college_registration",
        resource_id=str(row.id),
        after={"decidedBy": str(actor.id), "decidedAt": row.decided_at.isoformat()},
    )
    return row


async def _void_pass_and_documents(
    db: AsyncSession, row: CollegeRegistration
) -> None:
    """Close open orders, mark documents rejected, and cancel/revoke the pass."""
    await _close_open_orders(db, row.user_id, row.edition_id)
    documents = list(
        (
            await db.execute(
                select(RegistrationDocument).where(
                    RegistrationDocument.registration_id == row.id
                )
            )
        ).scalars()
    )
    for document in documents:
        document.status = "rejected"
    await db.flush()

    from app.models.commerce import ConventionPass
    from app.services.tickets import revoke_for_pass

    user_pass = (
        await db.execute(
            select(ConventionPass)
            .where(
                ConventionPass.user_id == row.user_id,
                ConventionPass.edition_id == row.edition_id,
            )
            .order_by(ConventionPass.created_at.desc())
            .limit(1)
        )
    ).scalars().first()
    if user_pass is not None:
        user_pass.status = "cancelled"
        await revoke_for_pass(db, user_pass.id)


async def _refund_or_park_pass(
    db: AsyncSession,
    request: Request | None,
    row: CollegeRegistration,
    actor: User | None,
    actor_role: str | None,
    *,
    reason_code: str,
    full_reason: str,
    try_gateway: bool,
) -> None:
    """Initiate a gateway pass refund or park a pending refund request."""
    if row.payment_status != "paid":
        return
    if try_gateway:
        try:
            await initiate_refund(
                db,
                request,
                row,
                actor,
                actor_role,
                amount_paise=await _refundable_paise(db, row),
                note=f"Automatic refund on cancellation: {full_reason}",
            )
            return
        except Exception as exc:
            if row.refund_status not in {"processing", "completed"}:
                row.refund_status = "failed"
            await db.flush()
            await notify(
                db,
                row,
                "refund_failed",
                title="Refund could not be started",
                values={"reason": str(exc)[:200]},
            )
            return

    pending_amount = await _refundable_paise(db, row)
    if row.order_id is not None and pending_amount > 0:
        existing_request = (
            await db.execute(
                select(Refund).where(
                    Refund.order_id == row.order_id,
                    Refund.status.in_(["pending", "processing", "processed"]),
                )
            )
        ).scalars().first()
        if existing_request is None:
            db.add(
                Refund(
                    order_id=row.order_id,
                    amount_paise=pending_amount,
                    reason_code=reason_code,
                    reason_note=f"Rejection refund request: {full_reason[:200]}",
                    status="pending",
                    requested_by=actor.id if actor else None,
                )
            )
            row.refund_status = "initiated"
            await db.flush()
            await notify(
                db,
                row,
                "refund_initiated",
                title="Refund requested",
                values={"amountPaise": pending_amount, "category": row.category_name},
            )


async def reject(
    db: AsyncSession,
    request: Request,
    row: CollegeRegistration,
    actor: User,
    actor_role: str,
    *,
    reason_code: str | None,
    reason: str | None,
    notes: str | None,
    initiate_refund_workflow: bool,
    refund_events: bool = True,
    can_initiate_refund: bool = True,
) -> CollegeRegistration:
    code = (reason_code or "").strip() or "other"
    custom = (reason or "").strip()
    if code == "other" and len(custom) < 5:
        raise ValidationFailed("Give a custom rejection explanation.")
    label = REJECTION_REASONS.get(code) or code.replace("_", " ")
    full_reason = f"{label}: {custom}" if custom and code != "other" else (custom or label)
    if row.verification_status == "approved":
        raise Conflict("An approved registration cannot be rejected.", code="ALREADY_APPROVED")
    if row.verification_status == "rejected":
        # A second Reject click re-ran the whole cascade: another pass teardown,
        # another "Registration cancelled" email and possibly a second refund
        # row for the same money.
        raise Conflict("This registration is already rejected.", code="ALREADY_REJECTED")
    row.verification_status = "rejected"
    row.decided_at = datetime.now(UTC)
    row.decided_by = actor.id
    row.rejection_code = code
    row.rejection_reason = full_reason[:2000]
    row.resubmission_requested_at = datetime.now(UTC)
    _clear_compliance(row)
    if notes and notes.strip():
        stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        line = f"[{stamp}] {actor.full_name or actor.email} (rejection): {notes.strip()}"
        row.admin_notes = f"{row.admin_notes}\n{line}" if row.admin_notes else line

    await _void_pass_and_documents(db, row)

    # Free event seats, optionally refund paid add-on orders, and purge from teams with fair leader handover
    from app.services.passes import release_event_entitlements
    await release_event_entitlements(
        db,
        user_id=row.user_id,
        edition_id=row.edition_id,
        reason=f"Convention pass rejected: {full_reason[:200]}",
        refund_paid_events=bool(refund_events),
        # Money only moves if this operator may move it; otherwise the add-on
        # refunds are parked for the finance desk like the pass refund below.
        try_gateway=bool(refund_events and can_initiate_refund),
        actor_id=actor.id,
    )

    await notify(
        db,
        row,
        "rejected",
        title="Registration cancelled",
        values={"reason": full_reason, "category": row.category_name},
    )
    if initiate_refund_workflow:
        await _refund_or_park_pass(
            db,
            request,
            row,
            actor,
            actor_role,
            reason_code=code,
            full_reason=full_reason,
            try_gateway=bool(can_initiate_refund),
        )

    await record(
        db,
        request,
        actor_id=actor.id,
        actor_role=actor_role,
        action="college_registration.rejected",
        resource_type="college_registration",
        resource_id=str(row.id),
        after={
            "reasonCode": code,
            "reason": full_reason,
            "refundPass": bool(initiate_refund_workflow),
            "refundEvents": bool(refund_events),
            "refundStatus": row.refund_status,
            "decidedBy": str(actor.id),
        },
    )
    return row


async def request_documents(
    db: AsyncSession,
    request: Request,
    row: CollegeRegistration,
    actor: User,
    actor_role: str,
    documents: list[str],
    message: str,
    *,
    refund_pass_on_expiry: bool = True,
    refund_events_on_expiry: bool = True,
) -> CollegeRegistration:
    # Requesting documents on a rejected or refunded registration would
    # silently flip it back to "resubmission_required", un-rejecting it while
    # its pass stays cancelled. Reject -> approve (or refund) is the only
    # valid way out of a rejection.
    if row.verification_status == "rejected":
        raise Conflict(
            "A rejected registration cannot go back to document correction. "
            "Approve it instead if the rejection was a mistake.",
            code="ALREADY_REJECTED",
        )
    if row.verification_status == "approved":
        # Asking an approved attendee for new documents demoted them while their
        # pass, ticket and credential stayed live: the door admitted them and
        # their credential page said "pending verification". Rejection or a
        # refund is the way back.
        raise Conflict(
            "This registration is already approved. Refund or reject it before asking for new documents.",
            code="ALREADY_APPROVED",
        )
    if row.payment_status == "refunded" or row.refund_status in {
        "completed",
        "processing",
        "initiated",
    }:
        raise Conflict("A refunded registration cannot be asked for documents.")
    row.verification_status = "resubmission_required"
    row.requested_documents = [doc for doc in documents if doc in DOC_DEFINITIONS]
    row.rejection_reason = message
    row.resubmission_requested_at = datetime.now(UTC)
    row.decided_at = datetime.now(UTC)
    row.decided_by = actor.id
    deadline = _set_compliance(row, COMPLIANCE_KIND_DOCUMENTS)
    row.compliance_refund_pass = bool(refund_pass_on_expiry)
    row.compliance_refund_events = bool(refund_events_on_expiry)
    await db.flush()
    await notify(
        db,
        row,
        "documents_correction",
        title="Documents need correction",
        values={
            "reason": message,
            "category": row.category_name,
            "deadline": _deadline_label(deadline),
        },
    )
    await record(
        db,
        request,
        actor_id=actor.id,
        actor_role=actor_role,
        action="college_registration.documents_requested",
        resource_type="college_registration",
        resource_id=str(row.id),
        after={"documents": row.requested_documents, "message": message},
    )
    return row


# --------------------------------------------------------------------------- #
# 24-hour compliance enforcement
# --------------------------------------------------------------------------- #


#: A read-triggered sweep may run at most once per this many seconds in a
#: worker. Opening the events page must not refund on every single request.
LAZY_SWEEP_THROTTLE_SECONDS = 10
_lazy_sweep_clock: dict[str, datetime] = {}


def lazy_sweep_due(key: str, *, seconds: int = LAZY_SWEEP_THROTTLE_SECONDS) -> bool:
    """Cheap in-process throttle for read paths (no DB round-trip)."""
    now = datetime.now(UTC)
    last = _lazy_sweep_clock.get(key)
    if last is not None and (now - last).total_seconds() < seconds:
        return False
    _lazy_sweep_clock[key] = now
    return True


async def maybe_enforce_lapsed_compliance(
    db: AsyncSession,
    *,
    edition_id: uuid.UUID,
    request: Request | None = None,
    limit: int = 10,
    try_gateway: bool = True,
) -> dict[str, int]:
    """Run the sweep only when this edition actually has a lapsed row.

    Used by reads (event catalogue, seat counts, event selection) so a fresh
    visitor sees the seat that an expired attendee was holding. The throttled
    existence check keeps the common case to one indexed query.
    """
    if not lazy_sweep_due(f"edition:{edition_id}"):
        return {
            "checked": 0,
            "enforced": 0,
            "documents": 0,
            "categoryPayment": 0,
            "seatsReleased": 0,
            "refunded": 0,
            "refundsQueued": 0,
        }
    due = (
        await db.execute(
            select(CollegeRegistration.id)
            .where(
                CollegeRegistration.edition_id == edition_id,
                CollegeRegistration.compliance_kind.is_not(None),
                CollegeRegistration.compliance_deadline_at.is_not(None),
                CollegeRegistration.compliance_deadline_at <= datetime.now(UTC),
                CollegeRegistration.compliance_enforced_at.is_(None),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if due is None:
        return {
            "checked": 0,
            "enforced": 0,
            "documents": 0,
            "categoryPayment": 0,
            "seatsReleased": 0,
            "refunded": 0,
            "refundsQueued": 0,
        }
    return await enforce_lapsed_compliance(
        db,
        edition_id=edition_id,
        limit=limit,
        request=request,
        try_gateway=try_gateway,
    )


async def lazy_enforce_for_read(
    db: AsyncSession,
    *,
    edition_id: uuid.UUID,
    request: Request | None = None,
) -> dict[str, int]:
    """Sweep before a seat/event read and persist anything it changed.

    Only commits when enforcement actually ran; a plain read keeps its normal
    transaction handling.
    """
    summary = await maybe_enforce_lapsed_compliance(
        db, edition_id=edition_id, request=request
    )
    if summary.get("enforced"):
        await db.commit()
    return summary


async def enforce_lapsed_compliance(
    db: AsyncSession,
    *,
    edition_id: uuid.UUID | None = None,
    limit: int = 25,
    request: Request | None = None,
    try_gateway: bool = True,
) -> dict[str, int]:
    """Enforce desk requests whose 24-hour window has expired.

    This is deliberately lazy: it runs when someone opens the event catalogue
    or the event-selection page (the read path that shows seats) and when a
    registration is submitted/edited, plus the maintenance sweep. Each
    registration is enforced exactly once through ``compliance_enforced_at``;
    a failed row is logged and retried on the next sweep instead of blocking
    the caller's own transaction.
    """
    now = datetime.now(UTC)
    stmt = select(CollegeRegistration).where(
        CollegeRegistration.compliance_kind.is_not(None),
        CollegeRegistration.compliance_deadline_at.is_not(None),
        CollegeRegistration.compliance_deadline_at <= now,
        CollegeRegistration.compliance_enforced_at.is_(None),
    )
    if edition_id is not None:
        stmt = stmt.where(CollegeRegistration.edition_id == edition_id)
    rows = list(
        (
            await db.execute(
                stmt.order_by(CollegeRegistration.compliance_deadline_at).limit(limit)
            )
        ).scalars()
    )
    summary = {
        "checked": len(rows),
        "enforced": 0,
        "documents": 0,
        "categoryPayment": 0,
        "seatsReleased": 0,
        "refunded": 0,
        "refundsQueued": 0,
    }
    for row in rows:
        # The attendee may have answered between the query and this loop.
        if row.compliance_kind == COMPLIANCE_KIND_DOCUMENTS:
            if row.verification_status != "resubmission_required":
                _clear_compliance(row)
                continue
        elif row.compliance_kind == COMPLIANCE_KIND_CATEGORY_PAYMENT:
            if row.category_change_status != "awaiting_payment":
                _clear_compliance(row)
                continue
        else:
            # Unknown legacy value: close it rather than hammering the sweep.
            _clear_compliance(row)
            continue
        try:
            async with db.begin_nested():
                # Claim the row atomically. Two workers (a read sweep and the
                # cron) can pick the same expiry; only the one whose UPDATE
                # matches an unenforced row does the release/refund work.
                claimed = await db.execute(
                    update(CollegeRegistration)
                    .where(
                        CollegeRegistration.id == row.id,
                        CollegeRegistration.compliance_enforced_at.is_(None),
                    )
                    .values(compliance_enforced_at=datetime.now(UTC))
                    .execution_options(synchronize_session=False)
                )
                if not claimed.rowcount:
                    continue
                result = await _enforce_compliance_row(
                    db, row, request=request, try_gateway=try_gateway
                )
        except Exception:  # noqa: BLE001 - one bad row must not block the rest
            logger.exception(
                "compliance_enforcement_failed registration=%s kind=%s",
                row.id,
                row.compliance_kind,
            )
            continue
        summary["enforced"] += 1
        if row.compliance_kind == COMPLIANCE_KIND_DOCUMENTS:
            summary["documents"] += 1
        else:
            summary["categoryPayment"] += 1
        summary["seatsReleased"] += result.get("seats", 0)
        summary["refunded"] += result.get("refunded", 0)
        summary["refundsQueued"] += result.get("queued", 0)
    if rows:
        await db.flush()
        cache_delete_pattern("public:*")
        cache_delete_pattern("admin:dashboard:*")
    return summary


async def _enforce_compliance_row(
    db: AsyncSession,
    row: CollegeRegistration,
    *,
    request: Request | None = None,
    try_gateway: bool = True,
) -> dict[str, int]:
    """Enforce desk requests whose 24-hour window has expired.

    For ``COMPLIANCE_KIND_DOCUMENTS``, expiration performs the same pass
    revocation as a rejection (marking ``rejected``, cancelling the pass and
    revoking its ticket, releasing event seats and transferring team
    leadership), while respecting the admin's ``compliance_refund_pass`` and
    ``compliance_refund_events`` choices.
    """
    from app.services.passes import release_event_entitlements

    kind = row.compliance_kind
    if kind == COMPLIANCE_KIND_DOCUMENTS:
        reason = "24-hour document-correction window expired"
        refund_pass = bool(row.compliance_refund_pass)
        refund_events = bool(row.compliance_refund_events)

        row.verification_status = "rejected"
        row.decided_at = datetime.now(UTC)
        row.rejection_code = "resubmission_expired"
        row.rejection_reason = reason
        await _void_pass_and_documents(db, row)

        result = await release_event_entitlements(
            db,
            user_id=row.user_id,
            edition_id=row.edition_id,
            reason=reason,
            refund_paid_events=refund_events,
            try_gateway=bool(refund_events and try_gateway),
        )
        if refund_pass:
            await _refund_or_park_pass(
                db,
                request,
                row,
                None,
                "system",
                reason_code="resubmission_expired",
                full_reason=reason,
                try_gateway=try_gateway,
            )
    else:
        reason = "24-hour category-change payment window expired"
        result = await release_event_entitlements(
            db,
            user_id=row.user_id,
            edition_id=row.edition_id,
            reason=reason,
            refund_paid_events=True,
            try_gateway=try_gateway,
        )
    row.compliance_enforced_at = datetime.now(UTC)
    await notify(
        db,
        row,
        "compliance_enforced",
        title="24-hour deadline passed",
        values={
            "reason": reason,
            "category": row.category_name,
            "registrationId": row.registration_number,
        },
    )
    await record(
        db,
        request,
        actor_id=None,
        actor_role="system",
        action="college_registration.compliance_enforced",
        resource_type="college_registration",
        resource_id=str(row.id),
        after={
            "kind": kind,
            "deadlineAt": aware(row.compliance_deadline_at).isoformat()
            if row.compliance_deadline_at
            else None,
            "seatsReleased": result.get("seats", 0),
            "refunded": result.get("refunded", 0),
            "refundsQueued": result.get("queued", 0),
        },
    )
    await db.flush()
    return result


# --------------------------------------------------------------------------- #
# Refunds
# --------------------------------------------------------------------------- #


async def refund_for(
    db: AsyncSession, registration_id: uuid.UUID
) -> Refund | None:
    row = await db.get(CollegeRegistration, registration_id)
    if row is None or row.refund_id is None:
        return None
    return await db.get(Refund, row.refund_id)


async def _processed_refund_total(db: AsyncSession, order_id: uuid.UUID) -> int:
    """How much of this order has actually gone back to the payer."""
    total = (
        (
            await db.execute(
                select(func.coalesce(func.sum(Refund.amount_paise), 0)).where(
                    Refund.order_id == order_id,
                    Refund.status == "processed",
                )
            )
        )
        .scalars()
        .one()
    ) or 0
    return int(total)


async def _committed_refund_total(db: AsyncSession, order_id: uuid.UUID) -> int:
    """How much of this order is already refunded or queued/in-flight for refund."""
    total = (
        (
            await db.execute(
                select(func.coalesce(func.sum(Refund.amount_paise), 0)).where(
                    Refund.order_id == order_id,
                    Refund.status.in_(("pending", "processing", "processed")),
                )
            )
        )
        .scalars()
        .one()
    ) or 0
    return int(total)


async def _cancel_outstanding_category_change(
    db: AsyncSession, row: CollegeRegistration, *, reason: str
) -> None:
    """Close an approved-but-unpaid category change and its delta order."""
    change = await awaiting_change(db, row.id)
    if change is None:
        return
    if change.order_id is not None:
        order = await db.get(PaymentOrder, change.order_id)
        if order is not None and order.status == "created":
            order.status = "expired"
    change.status = "rejected"
    change.admin_note = f"{change.admin_note or ''}\n{reason}".strip()
    row.category_change_status = "rejected"
    row.requested_category_id = None
    _clear_compliance(row)
    await db.flush()


async def _delta_orders(db: AsyncSession, row: CollegeRegistration) -> list[PaymentOrder]:
    """Paid category-change orders that carry extra money for this registration."""
    return list(
        (
            await db.execute(
                select(PaymentOrder).where(
                    PaymentOrder.linked_record_id == row.id,
                    PaymentOrder.purpose == "college_registration_delta",
                    PaymentOrder.status.in_(("paid", "refunded")),
                )
            )
        ).scalars()
    )


async def _refund_order_ids(db: AsyncSession, row: CollegeRegistration) -> list[uuid.UUID]:
    """Every order that holds money for this registration, newest money first.

    Refund totals used to be summed on ``row.order_id`` alone, so money paid for
    a category upgrade (a separate order) was invisible: the registration could
    never be considered fully refunded and its pass stayed alive.

    The order matters: refunding "the last money in" first means a category
    downgrade returns the upgrade and leaves the pass payment alone, and a full
    refund still covers the base order once the extra money is gone.
    """
    ids: list[uuid.UUID] = []
    for order in sorted(
        await _delta_orders(db, row), key=lambda item: item.created_at, reverse=True
    ):
        ids.append(order.id)
    if row.order_id and row.order_id not in ids:
        ids.append(row.order_id)
    return ids


async def _processed_refund_total_for(db: AsyncSession, row: CollegeRegistration) -> int:
    total = 0
    for order_id in await _refund_order_ids(db, row):
        total += await _processed_refund_total(db, order_id)
    return total


async def _committed_refund_total_for(db: AsyncSession, row: CollegeRegistration) -> int:
    total = 0
    for order_id in await _refund_order_ids(db, row):
        total += await _committed_refund_total(db, order_id)
    return total


async def _collected_paise(db: AsyncSession, row: CollegeRegistration) -> int:
    """Money actually captured for this pass.

    ``fee_paise`` is rewritten by a downgrade, so it is not a safe proxy for
    what was paid: the pass order amount plus any captured category-change
    delta is. Using the fee capped refunds too low after two downgrades and
    made the "is this a full refund?" test wrong.
    """
    order = await db.get(PaymentOrder, row.order_id) if row.order_id else None
    base = int(order.amount_paise) if order is not None else int(row.fee_paise or 0)
    # Upgrade money is read from the delta orders themselves: the
    # ``additional_paid_paise`` mirror is a display value and must not decide
    # how much of the registration has been refunded.
    for delta in await _delta_orders(db, row):
        base += int(delta.amount_paise)
    return base


async def _refundable_paise(db: AsyncSession, row: CollegeRegistration) -> int:
    """What is still owed on this registration: collected minus committed/refunded."""
    if row.order_id is None:
        return 0
    committed = await _committed_refund_total_for(db, row)
    return max(0, await _collected_paise(db, row) - committed)


async def _refund_plan(
    db: AsyncSession, row: CollegeRegistration, requested: int
) -> list[tuple[PaymentOrder, int]]:
    """Split a registration refund across the orders that still hold money."""
    plan: list[tuple[PaymentOrder, int]] = []
    remaining_request = int(requested)
    for order_id in await _refund_order_ids(db, row):
        order = await db.get(PaymentOrder, order_id)
        if order is None:
            continue
        left = int(order.amount_paise) - await _committed_refund_total(db, order_id)
        if left <= 0:
            continue
        slice_paise = min(left, remaining_request)
        if slice_paise <= 0:
            break
        plan.append((order, slice_paise))
        remaining_request -= slice_paise
        if remaining_request <= 0:
            break
    return plan


async def initiate_refund(
    db: AsyncSession,
    request: Request | None,
    row: CollegeRegistration,
    actor: User | None,
    actor_role: str | None,
    *,
    amount_paise: int,
    note: str | None,
) -> Refund:
    # Two operators refunding at the same time both read "nothing refunded yet"
    # and could take more than was collected. The row lock serialises them.
    locked = await db.execute(
        select(CollegeRegistration)
        .where(CollegeRegistration.id == row.id)
        .with_for_update()
    )
    row = locked.scalars().first() or row

    if row.payment_status != "paid":
        raise Conflict("Only a paid registration can be refunded.", code="PAYMENT_REQUIRED")
    if row.order_id is None:
        raise Conflict("This registration has no payment order.")
    existing = await refund_for(db, row.id)
    if existing is not None and existing.status in {"pending", "processing"}:
        raise Conflict("A refund is already in progress for this registration.")
    order = await db.get(PaymentOrder, row.order_id)
    if order is None:
        raise Conflict("Payment order not found.")
    # A partial refund that already completed must still be finishable: cap by
    # what is left of the paid total, not by the full fee. Without this the
    # remaining money could never be returned (a processed refund blocked
    # every later attempt). The total spans the base order *and* any paid
    # category-change delta, because both are money on this registration.
    already_refunded = await _processed_refund_total_for(db, row)
    already_committed = await _committed_refund_total_for(db, row)
    refundable = await _collected_paise(db, row) - already_committed
    if refundable <= 0:
        raise Conflict("This registration has already been refunded in full.")
    requested = int(amount_paise)
    if requested <= 0:
        raise ValidationFailed("The refund amount must be greater than zero.")
    # Never silently shrink the operator's number: asking for more than is left
    # refunded the maximum and reported success, which hides a mistyped amount
    # and the fact that the rest of the fee was never collected.
    if requested > refundable:
        raise ValidationFailed(
            f"Only INR {refundable / 100:.2f} of this registration is still refundable.",
            code="REFUND_EXCEEDS_COLLECTED",
        )
    amount = requested
    # A gateway refund happens per captured payment, and a registration can own
    # two of them (the pass order and an upgrade order). The money is split
    # across those orders so a single desk action can still return the whole
    # amount instead of silently stopping at the base order.
    plan = await _refund_plan(db, row, amount)
    if not plan:
        raise Conflict("This registration has already been refunded in full.")
    settings = get_settings()
    registration_status = "initiated"
    refunds: list[Refund] = []
    gateway_refund_id: str | None = None
    for paid_order, slice_paise in plan:
        transaction = (
            await db.execute(
                select(PaymentTransaction)
                .where(PaymentTransaction.order_id == paid_order.id)
                .order_by(PaymentTransaction.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        refund_status = "pending"
        order_gateway_refund_id = None
        failed_gateway_exc = None
        if settings.payments_enabled and transaction is not None:
            from app.services.payments import gateway_refund

            try:
                order_gateway_refund_id = await gateway_refund(
                    transaction.gateway_payment_id, slice_paise
                )
                # Razorpay accepting a refund is not the same as money arriving. The
                # status stays processing until a refund.processed webhook or the
                # finance desk confirms it.
                refund_status = "processing"
                registration_status = "processing"
            except Exception as exc:
                logger.warning("gateway_refund failed: %s", exc)
                refund_status = "failed"
                registration_status = "failed"
                failed_gateway_exc = exc
        refund = Refund(
            order_id=paid_order.id,
            transaction_id=transaction.id if transaction else None,
            amount_paise=slice_paise,
            reason_code=row.rejection_code or "registration_rejected",
            reason_note=note,
            status=refund_status,
            requested_by=actor.id if actor else None,
            approved_by=actor.id if actor else None,
            gateway_refund_id=order_gateway_refund_id,
        )
        db.add(refund)
        await db.flush()
        refunds.append(refund)
        if order_gateway_refund_id:
            gateway_refund_id = order_gateway_refund_id
    # The first slice is the registration's headline refund; later slices are
    # the remaining money on other orders for the same registration.
    refund = refunds[0]
    row.refund_id = refund.id
    row.refund_status = registration_status
    # refund_amount_paise is the running total of *processed* refunds; the
    # completion branch recomputes it. Writing this slice here showed a partial
    # amount as if the whole refund had landed.
    row.refund_amount_paise = already_refunded
    if row.verification_status == "rejected":
        row.verification_status = "rejected"
    # An approved category change that is still waiting for its payment would
    # otherwise stay payable against a registration that is being refunded.
    await _cancel_outstanding_category_change(
        db, row, reason="Registration is under refund"
    )
    await db.flush()
    if failed_gateway_exc is not None:
        raise failed_gateway_exc
    await notify(
        db,
        row,
        "refund_initiated",
        title="Refund initiated",
        values={
            "amountPaise": amount,
            "category": row.category_name,
            "reason": note or "registration review",
        },
    )
    if request is not None or actor is not None:
        await record(
            db,
            request,
            actor_id=actor.id if actor else None,
            actor_role=actor_role,
            action="college_registration.refund_initiated",
            resource_type="college_registration",
            resource_id=str(row.id),
            after={
                "refundId": str(refund.id),
                "amountPaise": amount,
                "refundStatus": registration_status,
                "gatewayRefundId": gateway_refund_id,
                "mode": "gateway" if gateway_refund_id else "manual",
            },
        )
    cache_delete_pattern("admin:dashboard:*")
    return refund


async def _settle_refund_side_effects(db: AsyncSession, refund: Refund) -> None:
    """Undo whatever a settled refund paid for.

    A refunded category-change delta must give the registration its old
    category back; otherwise the desk kept showing the upgrade (and counted the
    returned money as paid) while the payment screen showed it refunded.
    """
    order = await db.get(PaymentOrder, refund.order_id)
    if order is None:
        return
    if order.purpose == "college_registration_delta" and order.linked_record_id:
        row = await db.get(CollegeRegistration, order.linked_record_id)
        if row is None:
            return
        change = (
            await db.execute(
                select(RegistrationCategoryChange)
                .where(
                    RegistrationCategoryChange.registration_id == row.id,
                    RegistrationCategoryChange.order_id == order.id,
                )
                .order_by(RegistrationCategoryChange.created_at.desc())
            )
        ).scalars().first()
        settled = await _processed_refund_total(db, order.id)
        partial = settled < int(order.amount_paise)
        if change is not None and change.completed_at is not None and not partial:
            previous = await db.get(RegistrationCategory, change.from_category_id)
            if previous is not None:
                row.category_id = previous.id
                row.category_code = previous.code
                row.category_name = previous.name
                row.fee_paise = previous.fee_paise
            change.status = "reversed"
            note_line = "Refunded: upgrade reversed."
            change.admin_note = (
                f"{change.admin_note}\n{note_line}" if change.admin_note else note_line
            ).strip()
            row.category_change_status = "reversed"
        await db.flush()
        await _sync_additional_paid(db, row)


async def _sync_additional_paid(db: AsyncSession, row: CollegeRegistration) -> None:
    """Recompute the display mirror for upgrade money that is still kept.

    ``additional_paid_paise`` is shown to the desk and added to the fee on the
    receipts screen. It used to be written once and never corrected, so a
    refunded upgrade still looked paid.
    """
    net = 0
    for delta in await _delta_orders(db, row):
        refunded = await _processed_refund_total(db, delta.id)
        net += max(0, int(delta.amount_paise) - refunded)
    row.additional_paid_paise = net
    await db.flush()


async def _revoke_pass_for_registration(
    db: AsyncSession, row: CollegeRegistration
) -> None:
    """Remove the pass entitlement when a registration is fully refunded."""
    from app.models.commerce import ConventionPass
    from app.services.passes import release_event_entitlements
    from app.services.tickets import revoke_for_pass

    user_pass = (
        await db.execute(
            select(ConventionPass)
            .where(
                ConventionPass.user_id == row.user_id,
                ConventionPass.edition_id == row.edition_id,
            )
            .order_by(ConventionPass.created_at.desc())
            .limit(1)
        )
    ).scalars().first()
    # Refunded is terminal: a pass that was suspended when the money went back
    # used to stay "suspended", and un-suspending the account re-activated it
    # with a brand new entry ticket.
    if user_pass is not None and user_pass.status != "refunded":
        user_pass.status = "refunded"
        await revoke_for_pass(db, user_pass.id)

    # Cancel every event registration the attendee still holds, remove them
    # from team rosters and return the money for their paid add-on events.
    # Manual and gateway refunds behave identically.
    await release_event_entitlements(
        db,
        user_id=row.user_id,
        edition_id=row.edition_id,
        reason="Convention pass refunded",
    )


async def refund_action(
    db: AsyncSession,
    request: Request,
    row: CollegeRegistration,
    actor: User,
    actor_role: str,
    *,
    action: str,
    amount_paise: int | None,
    note: str | None,
    gateway_refund_id: str | None,
) -> Refund:
    refund = await refund_for(db, row.id)
    if action == "initiate":
        return await initiate_refund(
            db,
            request,
            row,
            actor,
            actor_role,
            amount_paise=min(
                amount_paise or row.refund_amount_paise or row.fee_paise,
                await _refundable_paise(db, row),
            ),
            note=note,
        )
    if refund is None:
        # "Mark completed" used to fall through to initiate_refund, so a desk
        # operator recording a manual bank transfer instead started a real
        # gateway refund of the whole amount - the opposite of the request.
        raise Conflict(
            "There is no refund on this registration to update. Start one first.",
            code="REFUND_NOT_FOUND",
        )
    if action == "retry" and refund.status != "failed":
        # Retry used to reopen any row, including a settled one, and reset a
        # completed refund to "pending" with nothing left to refund.
        raise Conflict(
            "Only a failed refund can be retried.", code="REFUND_NOT_FAILED"
        )
    if action == "completed" and refund.status == "processed":
        raise Conflict(
            "This refund is already completed.", code="REFUND_ALREADY_COMPLETED"
        )
    if action == "processing":
        if refund.status == "processed":
            raise Conflict("This refund is already completed.")
        refund.status = "processing"
        if gateway_refund_id:
            refund.gateway_refund_id = gateway_refund_id
        row.refund_status = "processing"
        settled = await _processed_refund_total_for(db, row)
        in_flight = (
            await db.execute(
                select(func.coalesce(func.sum(Refund.amount_paise), 0)).where(
                    Refund.order_id.in_(await _refund_order_ids(db, row)),
                    Refund.status.in_(["pending", "processing"]),
                )
            )
        ).scalar() or 0
        if settled + in_flight >= await _collected_paise(db, row):
            # The whole payment is leaving. Keeping the pass alive until the
            # gateway answers let the attendee use the convention while their
            # money was already on its way back.
            await _revoke_pass_for_registration(db, row)
        await notify(
            db,
            row,
            "refund_initiated",
            title="Refund processing",
            values={"amountPaise": refund.amount_paise, "category": row.category_name},
        )
    elif action == "completed":
        reference = (gateway_refund_id or "").strip()
        if not reference and refund.gateway_refund_id:
            # A gateway refund ID alone is not proof of settlement. Ask the
            # gateway for the authoritative status before reporting completion.
            if get_settings().payments_enabled:
                from app.services.payments import fetch_gateway_refund

                remote = await fetch_gateway_refund(refund.gateway_refund_id)
                if remote.get("status") != "processed":
                    raise Conflict(
                        "The payment gateway has not confirmed this refund yet.",
                        code="REFUND_NOT_CONFIRMED",
                    )
            reference = refund.gateway_refund_id
        if not reference:
            raise ValidationFailed(
                "Enter the gateway refund ID or manual transfer reference before marking a refund complete.",
                code="REFUND_REFERENCE_REQUIRED",
            )
        refund.status = "processed"
        refund.gateway_refund_id = reference
        refund.processed_at = datetime.now(UTC)
        row.refund_status = "completed"
        await db.flush()
        await _settle_refund_side_effects(db, refund)
        total_refunded = await _processed_refund_total_for(db, row)
        row.refund_amount_paise = total_refunded
        if total_refunded >= await _collected_paise(db, row):
            row.payment_status = "refunded"
            for order_id in await _refund_order_ids(db, row):
                order = await db.get(PaymentOrder, order_id)
                if order is not None and order.status == "paid":
                    order.status = "refunded"
            await _revoke_pass_for_registration(db, row)
        else:
            # Partial refund: the money went back but the pass stays valid, so
            # the attendee keeps the entitlement they were not refunded for.
            await notify(
                db,
                row,
                "partial_refund",
                title="Partial refund recorded",
                values={"amountPaise": refund.amount_paise, "category": row.category_name},
            )
        await notify(
            db,
            row,
            "refund_completed",
            title="Refund completed",
            values={"amountPaise": refund.amount_paise, "category": row.category_name},
        )
    elif action == "failed":
        refund.status = "failed"
        row.refund_status = "failed"
        await notify(
            db,
            row,
            "refund_failed",
            title="Refund failed",
            values={"reason": note or "the payment gateway rejected it"},
        )
    elif action == "retry":
        refund.status = "pending"
        row.refund_status = "initiated"
    else:
        raise ValidationFailed("Unknown refund action.")
    if note:
        refund.reason_note = f"{refund.reason_note or ''}\n{note}".strip()
    await db.flush()
    await record(
        db,
        request,
        actor_id=actor.id if actor else None,
        actor_role=actor_role,
        action=f"college_registration.refund_{action}",
        resource_type="college_registration",
        resource_id=str(row.id),
        after={
            "refundId": str(refund.id),
            "status": refund.status,
            "registrationRefundStatus": row.refund_status,
        },
    )
    cache_delete_pattern("admin:dashboard:*")
    return refund


async def sync_gateway_refund(
    db: AsyncSession, gateway_refund_id: str, *, failed: bool = False
) -> None:
    """Apply one gateway refund event.

    Razorpay retries webhooks and the same event can arrive twice, so a settled
    refund is a no-op here: re-running the completion produced duplicate
    "refund completed" notifications for money that had already gone back.
    """
    refund = (
        await db.execute(
            select(Refund).where(Refund.gateway_refund_id == gateway_refund_id)
        )
    ).scalar_one_or_none()
    if refund is None:
        return
    if failed and refund.status == "processed":
        # A duplicate or out-of-order refund.failed must not erase a completed
        # refund: doing so let the desk start a second refund of the same money.
        logger.warning(
            "ignored_refund_failed_for_processed refund=%s", refund.id
        )
        return
    if not failed and refund.status == "processed":
        logger.info("ignored_duplicate_refund_processed refund=%s", refund.id)
        return
    refund.status = "failed" if failed else "processed"
    refund.processed_at = datetime.now(UTC)
    # A registration keeps only the *latest* refund id, so a webhook for an
    # earlier refund on the same order used to find nothing and leave the
    # registration untouched while the ledger said "processed".
    row = (
        await db.execute(
            select(CollegeRegistration)
            .where(CollegeRegistration.order_id == refund.order_id)
            .order_by(CollegeRegistration.created_at.desc())
        )
    ).scalars().first()
    if row is None:
        # A category-change delta order is not the registration's ``order_id``;
        # its money still belongs to that registration, and without this the
        # webhook settled the delta without reversing the upgrade or noticing
        # that the registration is now fully refunded.
        delta_order = await db.get(PaymentOrder, refund.order_id)
        if (
            delta_order is not None
            and delta_order.purpose == "college_registration_delta"
            and delta_order.linked_record_id
        ):
            row = await db.get(CollegeRegistration, delta_order.linked_record_id)
    if row is None:
        return
    if failed:
        settled = await _processed_refund_total(db, refund.order_id)
        if settled > 0 or row.payment_status == "refunded":
            # Another refund on this registration did settle; a failed slice
            # must not undo it.
            logger.warning(
                "ignored_refund_failed_for_registration registration=%s status=%s",
                row.id,
                row.refund_status,
            )
            return
        row.refund_status = "failed"
        # The money never left, so the order is payable (and refundable) again
        # instead of looking settled on the finance screen.
        order = await db.get(PaymentOrder, refund.order_id)
        if order is not None and order.status == "refunded":
            order.status = "paid"
        if row.payment_status == "refunded":
            row.payment_status = "paid"
        await notify(db, row, "refund_failed", title="Refund failed")
    else:
        row.refund_status = "completed"
        await db.flush()
        await _settle_refund_side_effects(db, refund)
        total_refunded = await _processed_refund_total_for(db, row)
        row.refund_amount_paise = total_refunded
        if total_refunded >= await _collected_paise(db, row):
            row.payment_status = "refunded"
            order = await db.get(PaymentOrder, refund.order_id)
            if order is not None and order.status == "paid":
                order.status = "refunded"
            await _revoke_pass_for_registration(db, row)
        await notify(
            db,
            row,
            "refund_completed",
            title="Refund completed",
            values={"amountPaise": refund.amount_paise},
        )
    await db.flush()


# --------------------------------------------------------------------------- #
# Category changes
# --------------------------------------------------------------------------- #


async def pending_change(
    db: AsyncSession, registration_id: uuid.UUID
) -> RegistrationCategoryChange | None:
    return (
        await db.execute(
            select(RegistrationCategoryChange)
            .where(
                RegistrationCategoryChange.registration_id == registration_id,
                RegistrationCategoryChange.status == "pending",
            )
            .order_by(RegistrationCategoryChange.created_at.desc())
        )
    ).scalar_one_or_none()


async def awaiting_change(
    db: AsyncSession, registration_id: uuid.UUID
) -> RegistrationCategoryChange | None:
    return (
        await db.execute(
            select(RegistrationCategoryChange)
            .where(
                RegistrationCategoryChange.registration_id == registration_id,
                RegistrationCategoryChange.status == "approved",
                RegistrationCategoryChange.order_id.is_not(None),
                RegistrationCategoryChange.completed_at.is_(None),
            )
            .order_by(RegistrationCategoryChange.created_at.desc())
        )
    ).scalar_one_or_none()


async def decide_category_change(
    db: AsyncSession,
    request: Request,
    row: CollegeRegistration,
    change: RegistrationCategoryChange,
    actor: User,
    actor_role: str,
    *,
    approve_change: bool,
    note: str | None,
    settlement: str | None,
) -> dict:
    if change.status != "pending":
        raise Conflict("This category change has already been decided.")
    # A rejected or refunded registration cannot change category: approving
    # would mutate the fee/category of a dead registration (and possibly
    # trigger a refund chain on top of an existing one).
    if row.verification_status == "rejected":
        raise Conflict(
            "A rejected registration cannot change category.",
            code="ALREADY_REJECTED",
        )
    if row.payment_status == "refunded" or row.refund_status in {
        "completed",
        "processing",
        "initiated",
    }:
        raise Conflict("A refunded registration cannot change category.")
    target = await category_for(db, row.edition_id, change.to_category_id)
    if not approve_change:
        change.status = "rejected"
        change.admin_note = note
        change.decided_by = actor.id
        change.decided_at = datetime.now(UTC)
        row.category_change_status = "rejected"
        row.requested_category_id = None
        await db.flush()
        await notify(
            db,
            row,
            "rejected",
            title="Category change declined",
            values={"reason": note or "category change declined by the registration desk"},
        )
        await record(
            db,
            request,
            actor_id=actor.id,
            actor_role=actor_role,
            action="college_registration.category_change_rejected",
            resource_type="college_registration",
            resource_id=str(row.id),
            after={"toCategory": target.code, "note": note},
        )
        return {"status": "rejected"}

    if not target.enabled:
        raise Conflict("The requested category is now disabled.")
    documents = list(
        (
            await db.execute(
                select(RegistrationDocument).where(
                    RegistrationDocument.registration_id == row.id
                )
            )
        ).scalars()
    )
    missing = _missing_documents(target, documents)
    if missing:
        raise Conflict(
            "The requested category still needs: " + ", ".join(missing),
            code="DOCUMENTS_MISSING",
        )
    change.to_fee_paise = target.fee_paise
    diff = target.fee_paise - row.fee_paise
    change.settlement_amount_paise = abs(diff)
    change.admin_note = note
    change.decided_by = actor.id
    change.decided_at = datetime.now(UTC)
    change.status = "approved"
    row.category_change_status = "approved"
    row.requested_category_id = None

    if diff > 0:
        if change.order_id is None:
            from app.services.editions import current_policy
            from app.services.payments import attach_gateway_order, calculate_platform_fee

            try:
                policy = await current_policy(db, row.edition_id)
            except NotFound:
                policy = None
            platform_fee, total_delta = calculate_platform_fee(diff, policy)
            order = PaymentOrder(
                edition_id=row.edition_id,
                user_id=row.user_id,
                purpose="college_registration_delta",
                amount_paise=total_delta,
                platform_fee_paise=platform_fee,
                status="created",
                linked_record_id=row.id,
                notes={"categoryChangeId": str(change.id), "registrationId": str(row.id)},
            )
            db.add(order)
            await db.flush()
            await attach_gateway_order(db, order)
            change.order_id = order.id
        change.settlement_type = "additional_payment"
        row.category_change_status = "awaiting_payment"
        deadline = _set_compliance(row, COMPLIANCE_KIND_CATEGORY_PAYMENT)
        await db.flush()
        await notify(
            db,
            row,
            "category_change_approved",
            title="Additional payment required for your category change",
            values={
                "category": target.name,
                "amountPaise": diff,
                "deadline": _deadline_label(deadline),
            },
        )
        await record(
            db,
            request,
            actor_id=actor.id,
            actor_role=actor_role,
            action="college_registration.category_change_approved",
            resource_type="college_registration",
            resource_id=str(row.id),
            before={"category": row.category_code, "feePaise": row.fee_paise},
            after={
                "toCategory": target.code,
                "additionalPaise": diff,
                "settlement": "additional_payment",
            },
        )
        return {
            "status": "awaiting_payment",
            "settlementType": "additional_payment",
            "amountPaise": diff,
            "orderId": str(change.order_id),
        }

    if diff < 0:
        change.settlement_type = "refund"
        row.category_id = target.id
        row.category_code = target.code
        row.category_name = target.name
        row.fee_paise = target.fee_paise
        # A changed category changes the required proof, so it must be
        # re-verified even though the registration was previously approved.
        if row.verification_status == "approved":
            row.verification_status = "pending_verification"
        await db.flush()
        try:
            await initiate_refund(
                db,
                request,
                row,
                actor,
                actor_role,
                amount_paise=-diff,
                note=note or f"Category change from {change.from_fee_paise} to {target.fee_paise} paise",
            )
        except Exception as exc:
            # The category change is already recorded; a failed refund stays
            # visible and can be retried from the finance desk.
            row.refund_status = "failed"
            await db.flush()
            await notify(
                db,
                row,
                "refund_failed",
                title="Category change refund could not be started",
                values={"reason": str(exc)[:200]},
            )
    else:
        change.settlement_type = "none"
        row.category_id = target.id
        row.category_code = target.code
        row.category_name = target.name
        row.fee_paise = target.fee_paise
        if row.verification_status == "approved":
            row.verification_status = "pending_verification"
        change.completed_at = datetime.now(UTC)
        await db.flush()
        await notify(
            db,
            row,
            "approved",
            title="Category changed",
            values={"category": target.name},
        )
    await record(
        db,
        request,
        actor_id=actor.id,
        actor_role=actor_role,
        action="college_registration.category_change_approved",
        resource_type="college_registration",
        resource_id=str(row.id),
        before={"category": row.category_code, "feePaise": row.fee_paise},
        after={"toCategory": target.code, "settlement": change.settlement_type},
    )
    return {
        "status": "approved",
        "settlementType": change.settlement_type,
        "amountPaise": abs(diff),
        "orderId": str(change.order_id) if change.order_id else None,
    }


async def apply_paid_category_change(
    db: AsyncSession, order: PaymentOrder
) -> None:
    change_id = (order.notes or {}).get("categoryChangeId")
    if not change_id:
        return
    change = await db.get(RegistrationCategoryChange, uuid.UUID(change_id))
    if change is None or change.status != "approved" or change.completed_at:
        return
    row = await db.get(CollegeRegistration, change.registration_id)
    target = await db.get(RegistrationCategory, change.to_category_id)
    if row is None or target is None:
        return
    # Paying the difference for a registration that is already under refund (or
    # refunded) would take money for an entitlement that is gone.
    if row.refund_status != "not_initiated" or row.payment_status == "refunded" or row.verification_status == "rejected":
        logger.warning(
            "category_delta_ignored_closed_registration registration=%s refund=%s payment=%s",
            row.id,
            row.refund_status,
            row.payment_status,
        )
        if order.status == "paid":
            _committed = (
                (
                    await db.execute(
                        select(func.coalesce(func.sum(Refund.amount_paise), 0)).where(
                            Refund.order_id == order.id,
                            Refund.status.in_(["pending", "processing", "processed"]),
                        )
                    )
                )
                .scalars()
                .one()
            ) or 0
            _avail = int(order.amount_paise) - int(_committed)
            if _avail > 0:
                db.add(
                    Refund(
                        order_id=order.id,
                        amount_paise=_avail,
                        reason_code="category_change_closed",
                        reason_note="Category change paid after the registration was closed",
                        status="pending",
                    )
                )
        return
    row.category_id = target.id
    row.category_code = target.code
    row.category_name = target.name
    row.fee_paise = target.fee_paise
    row.additional_paid_paise = (row.additional_paid_paise or 0) + order.amount_paise
    row.category_change_status = "completed"
    change.completed_at = datetime.now(UTC)
    _clear_compliance(row)
    if row.verification_status == "approved":
        row.verification_status = "pending_verification"
    await db.flush()
    await notify(
        db,
        row,
        "approved",
        title="Category change completed",
        values={"category": target.name},
    )


# --------------------------------------------------------------------------- #
# Configuration writes
# --------------------------------------------------------------------------- #


def _diff(before: dict, after: dict) -> dict:
    return {
        key: {"from": before.get(key), "to": after.get(key)}
        for key in set(before) | set(after)
        if before.get(key) != after.get(key)
    }


async def update_config(
    db: AsyncSession,
    request: Request,
    edition_id: uuid.UUID,
    actor: User,
    actor_role: str,
    *,
    settings_update: dict | None,
    category_updates: dict[str, dict],
) -> dict:
    db_settings = await settings_for(db, edition_id, create=True)
    assert db_settings is not None
    edition = await db.get(ConventionEdition, edition_id)
    if edition is None:
        raise NotFound("Edition not found.")

    changed_categories: list[str] = []
    for code, values in (category_updates or {}).items():
        row = (
            await db.execute(
                select(RegistrationCategory).where(
                    RegistrationCategory.edition_id == edition_id,
                    RegistrationCategory.code == code,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise NotFound(f"Registration category '{code}' not found.")
        before = category_payload(row)
        if "required_documents" in values and values["required_documents"] is not None:
            docs = [doc.model_dump() if hasattr(doc, "model_dump") else doc for doc in values["required_documents"]]
            seen = set()
            for doc in docs:
                if doc.get("type") not in DOC_DEFINITIONS:
                    raise ValidationFailed(f"Unknown document type '{doc.get('type')}'")
                if doc["type"] in seen:
                    raise ValidationFailed("Each document type may appear only once")
                seen.add(doc["type"])
            row.required_documents = docs
        for field in ("name", "description", "fee_paise", "enabled", "display_order"):
            if field in values and values[field] is not None:
                setattr(row, field, values[field])
        after = category_payload(row)
        diff = _diff(before, after)
        if diff:
            changed_categories.append(code)
            await record(
                db,
                request,
                actor_id=actor.id,
                actor_role=actor_role,
                action="college_registration.config_category_updated",
                resource_type="registration_category",
                resource_id=str(row.id),
                before=before,
                after=after,
            )

    settings_diff: dict = {}
    if settings_update:
        before = settings_payload(db_settings)
        if "opens_at" in settings_update and "closes_at" in settings_update:
            opens = settings_update.get("opens_at")
            closes = settings_update.get("closes_at")
            if opens and closes and closes <= opens:
                raise ValidationFailed("Registration must close after it opens.")
        if (
            settings_update.get("max_upload_bytes") is not None
            and not 1024 <= int(settings_update["max_upload_bytes"]) <= MAX_DOCUMENT_BYTES
        ):
            raise ValidationFailed("Upload size must be between 1 KB and 20 MB.")
        field_map = {
            "registration_enabled": "registration_enabled",
            "opens_at": "opens_at",
            "closes_at": "closes_at",
            "accepted_formats": "accepted_formats",
            "max_upload_bytes": "max_upload_bytes",
            "allow_resubmission": "allow_resubmission",
            "allow_drive_links": "allow_drive_links",
            "broadcast_url": "broadcast_url",
            "helpdesk_phone": "helpdesk_phone",
            "payment_instructions": "payment_instructions",
            "refund_policy": "refund_policy",
            "approval_message": "approval_message",
            "rejection_message": "rejection_message",
            "notification_templates": "notification_templates",
        }
        for key, attr in field_map.items():
            if key in settings_update:
                setattr(db_settings, attr, settings_update[key])
        db_settings.updated_by = actor.id
        after = settings_payload(db_settings)
        settings_diff = _diff(before, after)
        if settings_diff:
            await record(
                db,
                request,
                actor_id=actor.id,
                actor_role=actor_role,
                action="college_registration.config_updated",
                resource_type="registration_settings",
                resource_id=str(db_settings.id),
                before=before,
                after=after,
            )
    await db.flush()
    cache_delete_pattern("public:*")
    cache_delete_pattern("admin:dashboard:*")
    return {
        "changedCategories": changed_categories,
        "settingsChanged": bool(settings_diff),
        "settingsDiff": settings_diff,
    }


# --------------------------------------------------------------------------- #
# Admin listing
# --------------------------------------------------------------------------- #


async def admin_rows(
    db: AsyncSession,
    edition_id: uuid.UUID,
    *,
    category: str | None = None,
    verification_status: str | None = None,
    payment_status: str | None = None,
    refund_status: str | None = None,
    state: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict], int, dict]:
    stmt = select(CollegeRegistration, User).join(
        User, CollegeRegistration.user_id == User.id
    ).where(CollegeRegistration.edition_id == edition_id)
    if category:
        stmt = stmt.where(CollegeRegistration.category_code == category)
    if verification_status:
        stmt = stmt.where(CollegeRegistration.verification_status == verification_status)
    if payment_status:
        stmt = stmt.where(CollegeRegistration.payment_status == payment_status)
    if refund_status:
        stmt = stmt.where(CollegeRegistration.refund_status == refund_status)
    if state == "refund_pending":
        stmt = stmt.where(CollegeRegistration.refund_status == "initiated")
    elif state == "refund_failed":
        stmt = stmt.where(CollegeRegistration.refund_status == "failed")
    elif state == "refund_processing":
        stmt = stmt.where(CollegeRegistration.refund_status == "processing")
    elif state == "refunded":
        stmt = stmt.where(CollegeRegistration.refund_status == "completed")
    elif state == "partially_refunded":
        stmt = stmt.where(
            CollegeRegistration.refund_status == "completed",
            CollegeRegistration.payment_status == "paid",
        )
    elif state == "compliance_due":
        stmt = stmt.where(
            CollegeRegistration.compliance_kind.is_not(None),
            CollegeRegistration.compliance_enforced_at.is_(None),
            CollegeRegistration.compliance_deadline_at > datetime.now(UTC),
        )
    elif state == "compliance_overdue":
        stmt = stmt.where(
            CollegeRegistration.compliance_kind.is_not(None),
            CollegeRegistration.compliance_enforced_at.is_(None),
            CollegeRegistration.compliance_deadline_at <= datetime.now(UTC),
        )
    elif state == "compliance_enforced":
        stmt = stmt.where(CollegeRegistration.compliance_enforced_at.is_not(None))
    elif state:
        stmt = stmt.where(CollegeRegistration.verification_status == state)
    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(CollegeRegistration.full_name).like(term),
                func.lower(CollegeRegistration.email).like(term),
                func.lower(CollegeRegistration.phone).like(term),
                func.lower(CollegeRegistration.registration_number).like(term),
                func.lower(CollegeRegistration.college_name).like(term),
            )
        )
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0
    rows = list(
        (
            await db.execute(
                stmt.order_by(CollegeRegistration.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    counts = {
        "total": total,
        "pendingVerification": 0,
        "approved": 0,
        "rejected": 0,
        "refundPending": 0,
        "refundFailed": 0,
        "complianceDue": 0,
        "complianceOverdue": 0,
        "polytechnic": 0,
        "isteMember": 0,
        "nonIste": 0,
    }
    now = datetime.now(UTC)
    for key, condition in (
        ("pendingVerification", CollegeRegistration.verification_status == "pending_verification"),
        ("approved", CollegeRegistration.verification_status == "approved"),
        ("rejected", CollegeRegistration.verification_status == "rejected"),
        ("refundPending", CollegeRegistration.refund_status.in_(["initiated", "processing"])),
        ("refundFailed", CollegeRegistration.refund_status == "failed"),
        (
            "complianceDue",
            CollegeRegistration.compliance_kind.is_not(None)
            & CollegeRegistration.compliance_enforced_at.is_(None)
            & (CollegeRegistration.compliance_deadline_at > now),
        ),
        (
            "complianceOverdue",
            CollegeRegistration.compliance_kind.is_not(None)
            & CollegeRegistration.compliance_enforced_at.is_(None)
            & (CollegeRegistration.compliance_deadline_at <= now),
        ),
        ("polytechnic", CollegeRegistration.category_code == "polytechnic"),
        ("isteMember", CollegeRegistration.category_code == "iste_member"),
        ("nonIste", CollegeRegistration.category_code == "non_iste"),
    ):
        counts[key] = (
            await db.execute(
                select(func.count(CollegeRegistration.id)).where(
                    CollegeRegistration.edition_id == edition_id, condition
                )
            )
        ).scalar() or 0
    # The ID card studio builds a card from one of these rows, so the passport
    # photo has to come with the list. One query for the page instead of one per
    # attendee keeps the desk list cheap.
    photo_documents: dict[uuid.UUID, uuid.UUID] = {}
    photo_doc_urls: dict[uuid.UUID, str | None] = {}
    registration_ids = [row.id for row, _ in rows]
    if registration_ids:
        for registration_id, document_id, external_url in (
            await db.execute(
                select(
                    RegistrationDocument.registration_id,
                    RegistrationDocument.id,
                    RegistrationDocument.external_url,
                ).where(
                    RegistrationDocument.registration_id.in_(registration_ids),
                    RegistrationDocument.doc_type == "photo",
                )
            )
        ).all():
            photo_documents[registration_id] = document_id
            photo_doc_urls[registration_id] = external_url
    # The QR a linked studio card prints is the attendee's own entry payload, so
    # a scan takes the normal ticket path instead of giving a badge its own
    # rights. Batched: one pass query and one ticket query for the whole page.
    entry_qr: dict[uuid.UUID, str] = {}
    base_url = ticket_service.entry_base_url()
    if base_url:
        passes_by_user: dict[uuid.UUID, ConventionPass] = {}
        paid_ids = [
            row.user_id
            for row, _ in rows
            if row.payment_status in {"paid", "completed"} and row.registration_number
        ]
        if paid_ids:
            for user_pass in (
                await db.execute(
                    select(ConventionPass)
                    .where(
                        ConventionPass.edition_id == edition_id,
                        ConventionPass.user_id.in_(paid_ids),
                    )
                    .order_by(ConventionPass.created_at.desc())
                )
            ).scalars():
                passes_by_user.setdefault(user_pass.user_id, user_pass)
        ticket_by_pass: dict[uuid.UUID, Ticket] = {}
        if passes_by_user:
            for ticket in (
                await db.execute(
                    select(Ticket).where(
                        Ticket.pass_id.in_([p.id for p in passes_by_user.values()]),
                        Ticket.status.in_(["active", "valid"]),
                    )
                )
            ).scalars():
                ticket_by_pass[ticket.pass_id] = ticket
        for row, _ in rows:
            user_pass = passes_by_user.get(row.user_id)
            entry_qr[row.id] = ticket_service.entry_payload(
                row,
                ticket=ticket_by_pass.get(user_pass.id) if user_pass else None,
                base_url=base_url,
            )
    return [
        {
            "id": str(row.id),
            "registrationNumber": row.registration_number,
            # What the attendee's own pass QR contains; None until one is issued.
            "entryQr": entry_qr.get(row.id),
            "fullName": row.full_name,
            "email": row.email,
            "phone": row.phone,
            "collegeName": row.college_name,
            "course": row.course,
            "branch": row.branch,
            "yearOfStudy": row.year_of_study,
            # Collected for the desk; the ID card never prints it.
            "dateOfBirth": row.date_of_birth.isoformat() if row.date_of_birth else None,
            # Logistics the desk and the ID card read off the row.
            "gender": decode_gender(row.gender),
            "foodPreference": decode_food(row.food_preference),
            "needsAccommodation": bool(row.needs_accommodation),
            "photoDocumentId": (
                str(photo_documents[row.id]) if row.id in photo_documents else None
            ),
            "photoExternalUrl": photo_doc_urls.get(row.id),
            "categoryCode": row.category_code,
            "categoryName": row.category_name,
            "feePaise": row.fee_paise,
            "additionalPaidPaise": row.additional_paid_paise or 0,
            "totalPaidPaise": row.fee_paise + (row.additional_paid_paise or 0),
            "paymentStatus": row.payment_status,
            "verificationStatus": row.verification_status,
            "refundStatus": row.refund_status,
            "refundAmountPaise": row.refund_amount_paise or 0,
            "state": overall_state(row),
            "compliance": compliance_payload(row),
            "complianceKind": row.compliance_kind,
            "complianceDeadlineAt": aware(row.compliance_deadline_at).isoformat()
            if row.compliance_deadline_at
            else None,
            "transactionId": row.transaction_id,
            "rejectionReason": row.rejection_reason,
            "createdAt": aware(row.created_at).isoformat() if row.created_at else None,
            "submittedAt": aware(row.submitted_at).isoformat() if row.submitted_at else None,
            "decidedAt": aware(row.decided_at).isoformat() if row.decided_at else None,
            "userName": user.full_name,
            "userEmail": user.email,
        }
        for row, user in rows
    ], total, counts


async def admin_detail(
    db: AsyncSession, edition_id: uuid.UUID, registration_id: uuid.UUID
) -> dict:
    row = await registration_by_id(db, edition_id, registration_id)
    payload = await serialize_registration(
        db, row, include_documents=True, include_notifications=True
    )
    change = (
        await db.execute(
            select(RegistrationCategoryChange)
            .where(RegistrationCategoryChange.registration_id == row.id)
            .order_by(RegistrationCategoryChange.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    refund = await refund_for(db, row.id)
    payload["adminNotes"] = row.admin_notes
    payload["decision"] = {
        "decidedAt": payload.get("decidedAt"),
        "rejectionCode": row.rejection_code,
        "rejectionReason": row.rejection_reason,
        "requestedDocuments": row.requested_documents or [],
    }
    payload["refund"] = (
        {
            "id": str(refund.id),
            "status": refund.status,
            "amountPaise": refund.amount_paise,
            "reasonCode": refund.reason_code,
            "reasonNote": refund.reason_note,
            "gatewayRefundId": refund.gateway_refund_id,
            "createdAt": aware(refund.created_at).isoformat() if refund.created_at else None,
            "processedAt": aware(refund.processed_at).isoformat()
            if refund.processed_at
            else None,
        }
        if refund
        else None
    )
    payload["categoryChange"] = (
        {
            **(payload.get("categoryChange") or {}),
            "settlementType": change.settlement_type,
            "status": change.status,
            "adminNote": change.admin_note,
            "fromFeePaise": change.from_fee_paise,
            "toFeePaise": change.to_fee_paise,
            "toCategoryId": str(change.to_category_id),
        }
        if change
        else None
    )
    payload["documentReview"] = [
        {
            "id": str(doc.id),
            "type": doc.doc_type,
            "status": doc.status,
            "reviewNote": doc.review_note,
        }
        for doc in (
            await db.execute(
                select(RegistrationDocument).where(
                    RegistrationDocument.registration_id == row.id
                )
            )
        ).scalars()
    ]
    return payload


async def document_for_admin(
    db: AsyncSession,
    edition_id: uuid.UUID,
    registration_id: uuid.UUID,
    document_id: uuid.UUID,
) -> RegistrationDocument:
    document = await db.get(RegistrationDocument, document_id)
    if document is None or document.registration_id != registration_id:
        raise NotFound("Document not found.")
    registration = await db.get(CollegeRegistration, registration_id)
    if registration is None or registration.edition_id != edition_id:
        raise NotFound("Document not found.")
    return document


__all__ = [
    "DOC_DEFINITIONS",
    "REJECTION_REASONS",
    "add_note",
    "admin_detail",
    "admin_rows",
    "approve",
    "apply_paid_category_change",
    "awaiting_change",
    "categories_for",
    "category_for",
    "category_payload",
    "create_or_update_profile",
    "decide_category_change",
    "document_for_admin",
    "document_for_user",
    "document_payload",
    "enforce_lapsed_compliance",
    "finalize_paid",
    "initiate_refund",
    "lazy_enforce_for_read",
    "lazy_sweep_due",
    "maybe_enforce_lapsed_compliance",
    "notification_payload",
    "notifications_for",
    "notify",
    "overall_state",
    "pending_change",
    "public_config",
    "refund_action",
    "refund_for",
    "registration_by_id",
    "registration_config_payload",
    "registration_for_user",
    "reject",
    "request_category_change",
    "request_documents",
    "resubmit",
    "save_document",
    "serialize_registration",
    "settings_for",
    "settings_payload",
    "submit_for_payment",
    "sync_gateway_refund",
    "update_config",
    "validate_document",
    "verify_checkout_payment",
    "window_state",
]
