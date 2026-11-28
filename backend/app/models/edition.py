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
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey


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
    contact_email: Mapped[str | None] = mapped_column(String(320))
    logo_icon_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("icons.id", ondelete="SET NULL"))


class EditionPolicy(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "edition_policies"

    edition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("convention_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    included_event_count: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    lunch_included_days: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    included_value_cap_paise: Mapped[int | None] = mapped_column(Integer)
    cap_inclusive: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # 0 = cheapest first (default), 1 = most expensive first
    allowance_pack_order: Mapped[int] = mapped_column(
        SmallInteger, default=0, server_default=text("0"), nullable=False
    )
    addon_requires_pass: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    team_members_require_pass: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    selection_change_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hold_minutes: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    refund_rules: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    gst_note: Mapped[str | None] = mapped_column(Text)
    platform_fee_bps: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    platform_fee_exempt_under_paise: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text)
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
    # Per-event participation guides. ``description`` sells the event; these
    # explain what a solo entrant and a team actually do and get. Admin-editable
    # prose only - no pricing lives here.
    solo_guide_md: Mapped[str] = mapped_column(Text, default="", nullable=False)
    team_guide_md: Mapped[str] = mapped_column(Text, default="", nullable=False)
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


class Announcement(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "announcements"

    edition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("convention_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    body_html: Mapped[str] = mapped_column(Text, default="", nullable=False)
    audience: Mapped[str] = mapped_column(String(20), default="public", nullable=False)
    banner_url: Mapped[str | None] = mapped_column(String(500))
    cta_label: Mapped[str | None] = mapped_column(String(80))
    cta_url: Mapped[str | None] = mapped_column(String(500))
    show_on_home: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


