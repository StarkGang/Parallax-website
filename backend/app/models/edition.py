import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey, utcnow


class ConventionEdition(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "convention_editions"

    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    organizer: Mapped[str] = mapped_column(String(160), nullable=False)
    host: Mapped[str] = mapped_column(String(160), nullable=False)
    venue: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    theme: Mapped[str | None] = mapped_column(String(200))
    hero_headline: Mapped[str | None] = mapped_column(String(240))
    hero_subtitle: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    registration_opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registration_closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    allowed_email_domains: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(320))
    contact_phone: Mapped[str | None] = mapped_column(String(24))
    logo_icon_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("icons.id", ondelete="SET NULL"))
    banner_key: Mapped[str | None] = mapped_column(String(300))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class EditionPolicy(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "edition_policies"

    edition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("convention_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pass_price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    included_event_count: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    lunch_included_days: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    included_selection_mode: Mapped[str] = mapped_column(
        String(12), default="up_to", nullable=False
    )
    included_value_cap_paise: Mapped[int | None] = mapped_column(Integer)
    cap_inclusive: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    addon_requires_pass: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    team_members_require_pass: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    selection_change_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    group_discount_threshold: Mapped[int | None] = mapped_column(Integer)
    group_discount_percent: Mapped[int | None] = mapped_column(Integer)
    allow_free_entry: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_team_addon_split: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    team_fee_basis_default: Mapped[str] = mapped_column(String(20), default="flat_per_team", nullable=False)
    hold_minutes: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    refund_rules: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    gst_note: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (
        Index(
            "uq_edition_policy_current",
            "edition_id",
            unique=True,
            postgresql_where=text("is_current"),
            sqlite_where=text("is_current"),
        ),
        UniqueConstraint("edition_id", "version", name="uq_edition_policy_version"),
    )


class Icon(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "icons"

    edition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("convention_editions.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(12), default="library", nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    library_key: Mapped[str | None] = mapped_column(String(160))
    mime: Mapped[str] = mapped_column(String(60), default="image/svg+xml", nullable=False)
    data: Mapped[bytes | None] = mapped_column(LargeBinary)
    storage_key: Mapped[str | None] = mapped_column(String(300))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))
    recolorable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (Index("ix_icons_edition_sha", "edition_id", "sha256"),)


class EventCategory(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "event_categories"

    edition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("convention_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    icon_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("icons.id", ondelete="SET NULL"))
    banner_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    accent: Mapped[str] = mapped_column(String(24), default="cyan", nullable=False)

    __table_args__ = (UniqueConstraint("edition_id", "slug", name="uq_category_slug"),)


class Event(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "events"

    edition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("convention_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("event_categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    summary: Mapped[str] = mapped_column(String(400), nullable=False)
    description_md: Mapped[str] = mapped_column(Text, default="", nullable=False)
    description_html: Mapped[str] = mapped_column(Text, default="", nullable=False)
    rules_md: Mapped[str] = mapped_column(Text, default="", nullable=False)
    rules_html: Mapped[str] = mapped_column(Text, default="", nullable=False)
    prizes_md: Mapped[str] = mapped_column(Text, default="", nullable=False)
    prizes_html: Mapped[str] = mapped_column(Text, default="", nullable=False)
    format: Mapped[str] = mapped_column(String(12), default="individual", nullable=False)
    team_min_size: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    team_max_size: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    base_value_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    included_eligible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    addon_price_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    addon_charge_basis: Mapped[str] = mapped_column(String(20), default="per_participant", nullable=False)
    team_fee_basis: Mapped[str | None] = mapped_column(String(20))
    capacity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    capacity_unit: Mapped[str] = mapped_column(String(20), default="participants", nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    venue_room: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    registration_opens_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    registration_closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    icon_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("icons.id", ondelete="SET NULL"))
    banner_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    accent: Mapped[str] = mapped_column(String(24), default="cyan", nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class EventPriceHistory(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "event_price_history"

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    old_base_value_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    new_base_value_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    old_addon_price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    new_addon_price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reason: Mapped[str | None] = mapped_column(Text)


class RosterEntry(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "roster_entries"

    edition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("convention_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    college: Mapped[str | None] = mapped_column(String(200))
    student_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    email_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class EligibilityVerification(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "eligibility_verifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    edition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("convention_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    document_key: Mapped[str | None] = mapped_column(String(300))
    document_name: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "edition_id", name="uq_verification_user_edition"),
    )


class VerificationEmailCode(Base, UUIDPrimaryKey):
    __tablename__ = "verification_email_codes"

    verification_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("eligibility_verifications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Announcement(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "announcements"

    edition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("convention_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    body_html: Mapped[str] = mapped_column(Text, default="", nullable=False)
    audience: Mapped[str] = mapped_column(String(20), default="public", nullable=False)
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Certificate(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "certificates"

    edition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("convention_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"))
    number: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    file_key: Mapped[str | None] = mapped_column(String(300))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
