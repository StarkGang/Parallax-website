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
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any, Iterable

from fastapi import Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_delete_pattern
from app.core.config import get_settings
from app.core.errors import AppError, Conflict, NotFound, ValidationFailed
from app.integrations import email as email_outbox
from app.integrations.storage import (
    get_document_storage,
    registration_document_key,
)
from app.models.commerce import PaymentOrder, PaymentTransaction, Refund
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
    "documents_correction": "Documents for registration {registrationId} need correction: {reason}",
    "refund_initiated": "A refund of ₹{amount} has been initiated for registration {registrationId}. Refund status is tracked separately and is not complete yet.",
    "refund_completed": "The refund of ₹{amount} for registration {registrationId} has been confirmed as completed.",
    "refund_failed": "The refund for registration {registrationId} failed. The finance desk will review it.",
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
}

MAX_DOCUMENT_BYTES = 20_971_520  # 20 MB absolute system ceiling
ATTENDEE_DOCUMENT_BYTES = 512_000  # 500 KB limit for ID card verification uploads


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
        return "refunded"
    if row.refund_status == "processing":
        return "refund_processing"
    if row.refund_status in {"initiated", "failed"}:
        return "refund_pending"
    return row.verification_status


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
        "city": row.city,
        "stateName": row.state,
        "feePaise": row.fee_paise,
        "additionalPaidPaise": row.additional_paid_paise,
        "totalPaidPaise": row.fee_paise + row.additional_paid_paise,
        "paymentStatus": row.payment_status,
        "verificationStatus": row.verification_status,
        "refundStatus": row.refund_status,
        "refundAmountPaise": row.refund_amount_paise,
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


async def create_or_update_profile(
    db: AsyncSession,
    request: Request,
    user: User,
    edition: ConventionEdition,
    payload: dict,
) -> CollegeRegistration:
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
    if row is not None and row.verification_status == "approved":
        # Approved registrations are locked; personal detail changes are not
        # allowed because the verified identity must stay intact.
        raise Conflict("This registration is already approved and cannot be edited.")
    if row is None and not open_now:
        raise Conflict(reason or "Registration is closed.", code="REGISTRATION_CLOSED")

    allowed_after_payment = {
        "phone",
        "course",
        "branch",
        "year_of_study",
        "city",
        "state",
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
            college_name=payload["college_name"],
            course=payload.get("course"),
            branch=payload.get("branch"),
            year_of_study=payload.get("year_of_study"),
            city=payload.get("city"),
            state=payload.get("state"),
            fee_paise=category.fee_paise,
            payment_status="pending",
            verification_status="payment_pending",
            refund_status="not_initiated",
            payment_details={},
        )
        db.add(row)
        await db.flush()
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
        "city",
        "state",
    ):
        if field in payload:
            setattr(row, field, payload.get(field))
    if row.payment_status != "paid":
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
    row = await registration_for_user(db, user.id, edition.id)
    if row is None:
        raise NotFound("Complete your registration details first.")
    db_settings = await settings_for(db, edition.id, create=True)
    open_now, reason = window_state(db_settings, edition)
    if row.payment_status == "paid":
        raise Conflict("This registration has already been paid.", code="ALREADY_PAID")
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

    existing_order = await db.get(PaymentOrder, row.order_id) if row.order_id else None
    if (
        existing_order is not None
        and existing_order.status == "created"
        and existing_order.amount_paise == amount
        and existing_order.purpose == "college_registration"
    ):
        order = existing_order
        from app.services.payments import attach_gateway_order

        await attach_gateway_order(db, order)
    else:
        order = PaymentOrder(
            edition_id=edition.id,
            user_id=user.id,
            purpose="college_registration",
            amount_paise=amount,
            status="created",
            linked_record_id=row.id,
        )
        db.add(order)
        await db.flush()
        row.order_id = order.id
        from app.services.payments import attach_gateway_order

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
    if row.verification_status != "payment_pending" and row.payment_status == "paid":
        return row
    if order.amount_paise != row.fee_paise:
        raise AppError(
            "The payment amount does not match the registration fee.",
            code="PAYMENT_AMOUNT_MISMATCH",
            status_code=409,
        )
    row.payment_status = "paid"
    row.paid_at = datetime.now(UTC)
    row.transaction_id = transaction_id or order.gateway_order_id or f"pay_{uuid.uuid4().hex[:12]}"
    row.payment_details = {
        "orderId": str(order.id),
        "gatewayOrderId": order.gateway_order_id,
        "amountPaise": order.amount_paise,
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
    # ticket and team registration unlock without a second purchase. A failure
    # here must never undo a confirmed payment, so it is logged and swallowed.
    try:
        from app.services.editions import current_policy
        from app.services.passes import activate_pass_for_registration

        policy = await current_policy(db, row.edition_id)
        await activate_pass_for_registration(
            db, row.user_id, row.edition_id, policy, row.fee_paise
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "pass_activation_failed registration=%s error=%s", row.id, exc
        )

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
        from app.services.telegram import send_telegram_registration
        category = await db.get(RegistrationCategory, row.category_id)
        asyncio.create_task(
            send_telegram_registration(
                full_name=row.full_name or user.full_name or "Attendee",
                email=row.email or user.email or "",
                phone=row.phone or "",
                college=row.college_name or "College Student",
                tier_name=category.name if category else "Pass Tier",
                amount_paid=f"₹{order.amount_paise / 100:.2f}",
                reference=row.reference_number,
            )
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
    if row.refund_status == "completed":
        raise Conflict("A refunded registration cannot change category.")
    target = await category_for(db, edition_id, category_id)
    if not target.enabled:
        raise ValidationFailed("That registration category is disabled.")
    if target.id == row.category_id:
        raise ValidationFailed("That is already your registration category.")
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
    await db.flush()
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
    if row.refund_status in {"completed", "processing", "initiated"}:
        raise Conflict("A registration under refund cannot be approved.")
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
    if notes and notes.strip():
        stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        line = f"[{stamp}] {actor.full_name or actor.email} (approval): {notes.strip()}"
        row.admin_notes = f"{row.admin_notes}\n{line}" if row.admin_notes else line
    for document in documents:
        document.status = "verified"
    await db.flush()
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
) -> CollegeRegistration:
    code = (reason_code or "").strip() or "other"
    custom = (reason or "").strip()
    if code == "other" and len(custom) < 5:
        raise ValidationFailed("Give a custom rejection explanation.")
    label = REJECTION_REASONS.get(code) or code.replace("_", " ")
    full_reason = f"{label}: {custom}" if custom and code != "other" else (custom or label)
    if row.verification_status == "approved":
        raise Conflict("An approved registration cannot be rejected.", code="ALREADY_APPROVED")
    row.verification_status = "rejected"
    row.decided_at = datetime.now(UTC)
    row.decided_by = actor.id
    row.rejection_code = code
    row.rejection_reason = full_reason[:2000]
    row.resubmission_requested_at = datetime.now(UTC)
    if notes and notes.strip():
        stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        line = f"[{stamp}] {actor.full_name or actor.email} (rejection): {notes.strip()}"
        row.admin_notes = f"{row.admin_notes}\n{line}" if row.admin_notes else line
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

    # Void convention pass and revoke ticket
    from app.models.commerce import ConventionPass, Registration, PaymentOrder
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

    # Free event seats by cancelling all event registrations for this participant
    event_regs = list(
        (
            await db.execute(
                select(Registration).where(
                    Registration.user_id == row.user_id,
                    Registration.edition_id == row.edition_id,
                    Registration.status.in_(["confirmed", "reserved"]),
                )
            )
        ).scalars()
    )
    addon_orders = []
    for reg in event_regs:
        reg.status = "cancelled"
        reg.cancelled_at = datetime.now(UTC)
        if reg.order_id and reg.fee_paise > 0:
            addon_orders.append((reg.order_id, reg.fee_paise))

    await notify(
        db,
        row,
        "rejected",
        title="Registration cancelled",
        values={"reason": full_reason, "category": row.category_name},
    )
    if initiate_refund_workflow and row.payment_status == "paid":
        try:
            await initiate_refund(
                db,
                request,
                row,
                actor,
                actor_role,
                amount_paise=row.fee_paise + row.additional_paid_paise,
                note=f"Automatic refund on cancellation: {full_reason}",
            )
        except Exception as exc:
            # A gateway outage must not roll back the cancellation itself. The
            # refund is recorded as failed and stays visible for follow-up.
            row.refund_status = "failed"
            await db.flush()
            await notify(
                db,
                row,
                "refund_failed",
                title="Refund could not be started",
                values={"reason": str(exc)[:200]},
            )

        # Also refund any separate paid add-on event orders
        if addon_orders:
            from app.services.payments import refund_order
            for addon_order_id, addon_paise in addon_orders:
                try:
                    addon_order = await db.get(PaymentOrder, addon_order_id)
                    if addon_order and addon_order.status == "paid":
                        await refund_order(
                            db,
                            addon_order,
                            amount_paise=min(addon_paise, addon_order.amount_paise),
                            reason_code=code,
                            reason_note=f"Automatic event refund on pass cancellation: {full_reason}",
                            requested_by_id=actor.id if actor else None,
                        )
                except Exception:
                    pass
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
) -> CollegeRegistration:
    row.verification_status = "resubmission_required"
    row.requested_documents = [doc for doc in documents if doc in DOC_DEFINITIONS]
    row.rejection_reason = message
    row.resubmission_requested_at = datetime.now(UTC)
    row.decided_at = datetime.now(UTC)
    row.decided_by = actor.id
    await db.flush()
    await notify(
        db,
        row,
        "documents_correction",
        title="Documents need correction",
        values={"reason": message, "category": row.category_name},
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
# Refunds
# --------------------------------------------------------------------------- #


async def refund_for(
    db: AsyncSession, registration_id: uuid.UUID
) -> Refund | None:
    row = await db.get(CollegeRegistration, registration_id)
    if row is None or row.refund_id is None:
        return None
    return await db.get(Refund, row.refund_id)


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
    if row.payment_status != "paid":
        raise Conflict("Only a paid registration can be refunded.", code="PAYMENT_REQUIRED")
    if row.order_id is None:
        raise Conflict("This registration has no payment order.")
    existing = await refund_for(db, row.id)
    if existing is not None and existing.status in {"pending", "processing", "processed"}:
        raise Conflict("A refund is already in progress for this registration.")
    amount = max(0, min(int(amount_paise), row.fee_paise + row.additional_paid_paise))
    if amount <= 0:
        raise ValidationFailed("The refund amount must be greater than zero.")
    order = await db.get(PaymentOrder, row.order_id)
    if order is None:
        raise Conflict("Payment order not found.")
    transaction = (
        await db.execute(
            select(PaymentTransaction)
            .where(PaymentTransaction.order_id == order.id)
            .order_by(PaymentTransaction.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    settings = get_settings()
    gateway_refund_id = None
    refund_status = "pending"
    registration_status = "initiated"
    if settings.payments_enabled and transaction is not None:
        from app.services.payments import gateway_refund

        gateway_refund_id = await gateway_refund(
            transaction.gateway_payment_id, amount
        )
        # Razorpay accepting a refund is not the same as money arriving. The
        # status stays processing until a refund.processed webhook or the
        # finance desk confirms it.
        refund_status = "processing"
        registration_status = "processing"
    refund = Refund(
        order_id=order.id,
        transaction_id=transaction.id if transaction else None,
        amount_paise=amount,
        reason_code=row.rejection_code or "registration_rejected",
        reason_note=note,
        status=refund_status,
        requested_by=actor.id if actor else None,
        approved_by=actor.id if actor else None,
        gateway_refund_id=gateway_refund_id,
    )
    db.add(refund)
    await db.flush()
    row.refund_id = refund.id
    row.refund_status = registration_status
    row.refund_amount_paise = amount
    if row.verification_status == "rejected":
        row.verification_status = "rejected"
    await db.flush()
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


async def _revoke_pass_for_registration(
    db: AsyncSession, row: CollegeRegistration
) -> None:
    """Remove the pass entitlement when a registration is fully refunded."""
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
    if user_pass is not None and user_pass.status == "active":
        user_pass.status = "refunded"
        await revoke_for_pass(db, user_pass.id)


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
    if action == "initiate" or refund is None:
        return await initiate_refund(
            db,
            request,
            row,
            actor,
            actor_role,
            amount_paise=amount_paise or row.refund_amount_paise or row.fee_paise,
            note=note,
        )
    if action == "processing":
        if refund.status == "processed":
            raise Conflict("This refund is already completed.")
        refund.status = "processing"
        if gateway_refund_id:
            refund.gateway_refund_id = gateway_refund_id
        row.refund_status = "processing"
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
        row.refund_amount_paise = refund.amount_paise
        if refund.amount_paise >= row.fee_paise + row.additional_paid_paise:
            row.payment_status = "refunded"
            order = await db.get(PaymentOrder, row.order_id) if row.order_id else None
            if order is not None and order.status == "paid":
                order.status = "refunded"
            await _revoke_pass_for_registration(db, row)
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
        actor_id=actor.id,
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
    refund = (
        await db.execute(
            select(Refund).where(Refund.gateway_refund_id == gateway_refund_id)
        )
    ).scalar_one_or_none()
    if refund is None:
        return
    refund.status = "failed" if failed else "processed"
    refund.processed_at = datetime.now(UTC)
    row = (
        await db.execute(
            select(CollegeRegistration).where(CollegeRegistration.refund_id == refund.id)
        )
    ).scalar_one_or_none()
    if row is None:
        return
    if failed:
        row.refund_status = "failed"
        await notify(db, row, "refund_failed", title="Refund failed")
    else:
        row.refund_status = "completed"
        if refund.amount_paise >= row.fee_paise + row.additional_paid_paise:
            row.payment_status = "refunded"
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
            order = PaymentOrder(
                edition_id=row.edition_id,
                user_id=row.user_id,
                purpose="college_registration_delta",
                amount_paise=diff,
                status="created",
                linked_record_id=row.id,
                notes={"categoryChangeId": str(change.id), "registrationId": str(row.id)},
            )
            db.add(order)
            await db.flush()
            from app.services.payments import attach_gateway_order

            await attach_gateway_order(db, order)
            change.order_id = order.id
        change.settlement_type = "additional_payment"
        row.category_change_status = "awaiting_payment"
        await db.flush()
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
    row.category_id = target.id
    row.category_code = target.code
    row.category_name = target.name
    row.fee_paise = target.fee_paise
    row.additional_paid_paise = (row.additional_paid_paise or 0) + order.amount_paise
    row.category_change_status = "completed"
    change.completed_at = datetime.now(UTC)
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
        stmt = stmt.where(CollegeRegistration.refund_status.in_(["initiated", "failed"]))
    elif state == "refund_processing":
        stmt = stmt.where(CollegeRegistration.refund_status == "processing")
    elif state == "refunded":
        stmt = stmt.where(CollegeRegistration.refund_status == "completed")
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
        "polytechnic": 0,
        "isteMember": 0,
        "nonIste": 0,
    }
    for key, condition in (
        ("pendingVerification", CollegeRegistration.verification_status == "pending_verification"),
        ("approved", CollegeRegistration.verification_status == "approved"),
        ("rejected", CollegeRegistration.verification_status == "rejected"),
        ("refundPending", CollegeRegistration.refund_status.in_(["initiated", "processing", "failed"])),
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
    return [
        {
            "id": str(row.id),
            "registrationNumber": row.registration_number,
            "fullName": row.full_name,
            "email": row.email,
            "phone": row.phone,
            "collegeName": row.college_name,
            "course": row.course,
            "branch": row.branch,
            "categoryCode": row.category_code,
            "categoryName": row.category_name,
            "feePaise": row.fee_paise,
            "paymentStatus": row.payment_status,
            "verificationStatus": row.verification_status,
            "refundStatus": row.refund_status,
            "state": overall_state(row),
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
    "finalize_paid",
    "initiate_refund",
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
