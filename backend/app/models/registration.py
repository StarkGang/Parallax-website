"""College event registration: categories, document verification, refunds and settings.

This is deliberately a separate domain from event add-on ``registrations`` and
``convention_passes``. A college registration is the participant's convention
entry: it carries the ISTE / Non-ISTE / Polytechnic category price, the ID
documents staff must verify, and its own payment, verification and refund
state fields. Payment, verification and refund status are tracked separately so
a rejected registration can never look "approved" because money moved.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey, utcnow


class RegistrationSettings(Base, UUIDPrimaryKey, Timestamps):
    """One row per edition. Everything the registration form reads lives here."""

    __tablename__ = "registration_settings"

    edition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("convention_editions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    registration_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_formats: Mapped[list] = mapped_column(
        JSON, default=lambda: ["pdf", "jpg", "jpeg", "png"], nullable=False
    )
    max_upload_bytes: Mapped[int] = mapped_column(Integer, default=5_242_880, nullable=False)
    allow_resubmission: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    helpdesk_phone: Mapped[str | None] = mapped_column(String(40), default="+91 94460 00000")
    payment_instructions: Mapped[str | None] = mapped_column(Text)
    refund_policy: Mapped[str | None] = mapped_column(Text)
    approval_message: Mapped[str | None] = mapped_column(Text)
    rejection_message: Mapped[str | None] = mapped_column(Text)
    notification_templates: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class RegistrationCategory(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "registration_categories"

    edition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("convention_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    fee_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    required_documents: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    __table_args__ = (
        UniqueConstraint("edition_id", "code", name="uq_registration_category_code"),
    )


class CollegeRegistration(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "college_registrations"

    edition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("convention_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("registration_categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    category_code: Mapped[str] = mapped_column(String(40), nullable=False)
    category_name: Mapped[str] = mapped_column(String(160), nullable=False)

    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(24))
    college_name: Mapped[str] = mapped_column(String(200), nullable=False)
    course: Mapped[str | None] = mapped_column(String(120))
    branch: Mapped[str | None] = mapped_column(String(120))
    year_of_study: Mapped[str | None] = mapped_column(String(40))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))

    # Asked at pass purchase. The desk reads them at the door and the kitchen and
    # hostel teams count from them, so they are real columns, not form metadata.
    # Stored as small integers (0/1) to keep the row narrow; the API and UI speak
    # "male"/"female" and "veg"/"non_veg" through core/attendee.py.
    gender: Mapped[int | None] = mapped_column(SmallInteger)
    food_preference: Mapped[int | None] = mapped_column(SmallInteger)
    needs_accommodation: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    fee_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    additional_paid_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Payment status is owned by money movement only.
    payment_status: Mapped[str] = mapped_column(
        String(24), default="pending", nullable=False, index=True
    )
    # payment_pending | pending_verification | approved | rejected | resubmission_required
    verification_status: Mapped[str] = mapped_column(
        String(32), default="payment_pending", nullable=False, index=True
    )
    # not_initiated | initiated | processing | completed | failed
    refund_status: Mapped[str] = mapped_column(
        String(24), default="not_initiated", nullable=False, index=True
    )
    refund_amount_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    refund_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refunds.id", ondelete="SET NULL")
    )

    registration_number: Mapped[str | None] = mapped_column(String(40), unique=True)
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payment_orders.id", ondelete="SET NULL")
    )
    transaction_id: Mapped[str | None] = mapped_column(String(120))
    payment_details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    rejection_code: Mapped[str | None] = mapped_column(String(60))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    admin_notes: Mapped[str | None] = mapped_column(Text)
    requested_documents: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    resubmission_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resubmission_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_document_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # none | pending | awaiting_payment | approved | rejected
    category_change_status: Mapped[str] = mapped_column(
        String(24), default="none", nullable=False
    )
    requested_category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("registration_categories.id", ondelete="SET NULL")
    )

    # 24-hour compliance window for an admin request that needs the attendee's
    # action (re-upload corrected documents / pay a category-change difference).
    # The deadline is written when the desk flags the registration and a lazy
    # sweep enforces it: seats are released, paid event money is refunded and
    # team rosters are repaired. ``compliance_kind`` stays set after enforcement
    # so both portals can still explain what happened.
    compliance_kind: Mapped[str | None] = mapped_column(String(40))
    compliance_flagged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    compliance_deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    compliance_enforced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    __table_args__ = (
        UniqueConstraint("edition_id", "user_id", name="uq_college_registration_user"),
        Index("ix_college_registration_edition_status", "edition_id", "verification_status"),
        Index(
            "ix_college_registration_compliance_due",
            "compliance_kind",
            "compliance_deadline_at",
        ),
    )


class RegistrationDocument(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "registration_documents"

    registration_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("college_registrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    doc_type: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(300), nullable=False)
    original_name: Mapped[str | None] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(80), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    review_note: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("registration_id", "doc_type", name="uq_registration_document_type"),
    )


class RegistrationCategoryChange(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "registration_category_changes"

    registration_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("college_registrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("registration_categories.id", ondelete="RESTRICT"), nullable=False
    )
    to_category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("registration_categories.id", ondelete="RESTRICT"), nullable=False
    )
    from_fee_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    to_fee_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    settlement_type: Mapped[str] = mapped_column(
        String(24), default="none", nullable=False
    )
    settlement_amount_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    admin_note: Mapped[str | None] = mapped_column(Text)
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payment_orders.id", ondelete="SET NULL")
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # Two concurrent requests used to create two pending changes for one
        # registration, so the desk saw two different target categories.
        Index(
            "uq_category_change_pending",
            "registration_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
    )


class RegistrationNotification(Base, UUIDPrimaryKey):
    __tablename__ = "registration_notifications"

    edition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("convention_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    registration_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("college_registrations.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


__all__ = [
    "RegistrationSettings",
    "RegistrationCategory",
    "CollegeRegistration",
    "RegistrationDocument",
    "RegistrationCategoryChange",
    "RegistrationNotification",
]
