"""Public-facing schemas for catalogue, schedule, editions and config."""

import uuid
from datetime import date, datetime

from app.schemas.common import CamelModel


class PolicyPublic(CamelModel):
    pass_price_paise: int
    lunch_included_days: list[str] = []
    included_event_count: int
    included_selection_mode: str
    included_value_cap_paise: int | None = None
    cap_inclusive: bool
    addon_requires_pass: bool
    team_members_require_pass: bool
    team_fee_basis_default: str
    hold_minutes: int
    selection_change_deadline: datetime | None = None
    policy_version: int
    gst_note: str | None = None


class EditionPublic(CamelModel):
    id: uuid.UUID
    slug: str
    name: str
    tagline: str | None = None
    organizer: str
    host: str
    venue: str
    city: str
    timezone: str
    starts_at: datetime
    ends_at: datetime
    registration_opens_at: datetime
    registration_closes_at: datetime
    status: str
    contact_email: str
    branding: dict
    logo_icon_id: uuid.UUID | None = None
    policy: PolicyPublic | None = None
    registration_open: bool = False


class CategoryPublic(CamelModel):
    id: uuid.UUID
    name: str
    slug: str
    accent: str | None = None
    icon_id: uuid.UUID | None = None
    display_order: int


class EventListItem(CamelModel):
    id: uuid.UUID
    slug: str
    title: str
    summary: str
    category_id: uuid.UUID
    category_name: str
    category_slug: str
    format: str
    team_min_size: int
    team_max_size: int
    starts_at: datetime
    ends_at: datetime
    venue_room: str | None = None
    icon_id: uuid.UUID | None = None
    banner_url: str | None = None
    accent: str | None = None
    base_value_paise: int
    included_eligible: bool
    addon_price_paise: int
    addon_charge_basis: str
    capacity: int
    seats_left: int | None = None
    status: str
    is_featured: bool
    registration_open: bool
    requires_approval: bool


class EventDetail(EventListItem):
    description_html: str | None = None
    rules_html: str | None = None
    prizes_html: str | None = None
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None
    team_fee_basis: str | None = None


class ScheduleItem(CamelModel):
    id: uuid.UUID
    title: str
    slug: str
    room: str | None = None
    starts_at: datetime
    ends_at: datetime
    accent: str | None = None
    icon_id: uuid.UUID | None = None
    category: str | None = None


class ScheduleDay(CamelModel):
    date: date
    label: str
    items: list[ScheduleItem] = []


class AnnouncementPublic(CamelModel):
    id: uuid.UUID
    title: str
    body_html: str
    published_at: datetime | None = None
    audience: str
    event_id: uuid.UUID | None = None


class PublicConfig(CamelModel):
    environment: str
    dev_login: bool
    google_login: bool
    payments_enabled: bool
    edition_slug: str | None = None
    support_email: str | None = None


__all__ = [
    "PolicyPublic",
    "EditionPublic",
    "CategoryPublic",
    "EventListItem",
    "EventDetail",
    "ScheduleItem",
    "ScheduleDay",
    "AnnouncementPublic",
    "PublicConfig",
]

