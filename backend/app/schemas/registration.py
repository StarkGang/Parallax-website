"""Request contracts for college registration, verification and configuration."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from app.schemas.common import CamelModel

DOC_CODES = {"photo", "college_id", "iste_card"}


class DocumentRequirement(CamelModel):
    type: str = Field(min_length=2, max_length=40)
    label: str = Field(min_length=2, max_length=160)
    required: bool = True


class RegistrationProfile(CamelModel):
    category_id: uuid.UUID
    full_name: str = Field(min_length=2, max_length=160)
    email: str = Field(max_length=320)
    phone: str | None = Field(default=None, max_length=24)
    college_name: str = Field(min_length=2, max_length=200)
    course: str | None = Field(default=None, max_length=120)
    branch: str | None = Field(default=None, max_length=120)
    year_of_study: str | None = Field(default=None, max_length=40)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("Enter a valid email address")
        return value


class CategoryChangeRequest(CamelModel):
    category_id: uuid.UUID
    note: str | None = Field(default=None, max_length=1000)


class RegistrationDecision(CamelModel):
    decision: Literal["approved", "rejected"]
    reason_code: str | None = Field(default=None, max_length=60)
    reason: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)
    initiate_refund: bool = True


class RequestDocuments(CamelModel):
    documents: list[str] = Field(default_factory=list)
    message: str = Field(min_length=3, max_length=2000)


class RegistrationNote(CamelModel):
    note: str = Field(min_length=1, max_length=2000)


class RefundAction(CamelModel):
    action: Literal["initiate", "processing", "completed", "failed", "retry"]
    amount_paise: int | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=2000)
    gateway_refund_id: str | None = Field(default=None, max_length=120)


class PaymentVerification(CamelModel):
    order_id: uuid.UUID
    razorpay_payment_id: str = Field(min_length=3, max_length=120)
    razorpay_signature: str = Field(min_length=10, max_length=256)


class CategoryChangeDecision(CamelModel):
    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=2000)
    settlement: Literal["additional_payment", "refund", "none"] | None = None


class NotificationTemplates(CamelModel):
    payment_success: str | None = None
    submitted: str | None = None
    approved: str | None = None
    rejected: str | None = None
    documents_correction: str | None = None
    refund_initiated: str | None = None
    refund_completed: str | None = None
    refund_failed: str | None = None


class RegistrationSettingsUpdate(CamelModel):
    registration_enabled: bool | None = None
    opens_at: datetime | None = None
    closes_at: datetime | None = None
    accepted_formats: list[str] | None = None
    max_upload_bytes: int | None = Field(default=None, ge=1024, le=20_971_520)
    allow_resubmission: bool | None = None
    helpdesk_phone: str | None = Field(default=None, max_length=40)
    payment_instructions: str | None = Field(default=None, max_length=4000)
    refund_policy: str | None = Field(default=None, max_length=4000)
    approval_message: str | None = Field(default=None, max_length=2000)
    rejection_message: str | None = Field(default=None, max_length=2000)
    notification_templates: dict | None = None

    @field_validator("accepted_formats")
    @classmethod
    def known_formats(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        allowed = {"pdf", "jpg", "jpeg", "png"}
        cleaned = sorted({item.strip().lower().lstrip(".") for item in value if item.strip()})
        if not cleaned:
            raise ValueError("Accept at least one file format")
        unknown = set(cleaned) - allowed
        if unknown:
            raise ValueError(f"Unsupported file format(s): {', '.join(sorted(unknown))}")
        return cleaned


class RegistrationCategoryUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    fee_paise: int | None = Field(default=None, ge=0, le=10_000_000)
    enabled: bool | None = None
    display_order: int | None = Field(default=None, ge=0, le=999)
    required_documents: list[DocumentRequirement] | None = None

    @field_validator("required_documents")
    @classmethod
    def known_documents(cls, value: list[DocumentRequirement] | None):
        if value is None:
            return None
        seen: set[str] = set()
        for item in value:
            if item.type not in DOC_CODES:
                raise ValueError(f"Unknown document type '{item.type}'")
            if item.type in seen:
                raise ValueError("Each document type may appear only once")
            seen.add(item.type)
        return value


class RegistrationConfigUpdate(CamelModel):
    settings: RegistrationSettingsUpdate | None = None
    categories: dict[str, RegistrationCategoryUpdate] = Field(default_factory=dict)


__all__ = [
    "DocumentRequirement",
    "RegistrationProfile",
    "CategoryChangeRequest",
    "RegistrationDecision",
    "RequestDocuments",
    "RegistrationNote",
    "RefundAction",
    "PaymentVerification",
    "CategoryChangeDecision",
    "NotificationTemplates",
    "RegistrationSettingsUpdate",
    "RegistrationCategoryUpdate",
    "RegistrationConfigUpdate",
]
