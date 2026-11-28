"""Admin schemas for dashboard, events, policies, checkin and users."""

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from app.schemas.common import CamelModel, StrictCamelModel


_GDRIVE_URL_PATTERNS = (
    r"^https?://drive\.google\.com/file/d/([a-zA-Z0-9_-]+)",
    r"^https?://drive\.google\.com/open\?(?:[^#]*&)?id=([a-zA-Z0-9_-]+)",
    r"^https?://drive\.google\.com/uc\?(?:[^#]*&)?id=([a-zA-Z0-9_-]+)",
    r"^https?://drive\.google\.com/thumbnail\?(?:[^#]*&)?id=([a-zA-Z0-9_-]+)",
    r"^https?://drive\.usercontent\.google\.com/download\?(?:[^#]*&)?id=([a-zA-Z0-9_-]+)",
)


def normalize_media_url(value: str | None) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    for pattern in _GDRIVE_URL_PATTERNS:
        match = re.match(pattern, raw, flags=re.IGNORECASE)
        if match:
            return f"https://drive.google.com/thumbnail?id={match.group(1)}&sz=w1600"
    return raw


class Metric(CamelModel):
    label: str
    value: int | float | str
    unit: str | None = None


class DashboardStats(CamelModel):
    edition_id: uuid.UUID
    edition_name: str
    passes_sold: int = 0
    revenue_paise: int = 0
    refunded_paise: int = 0
    net_revenue_paise: int = 0
    pending_refunds_paise: int = 0
    pending_refunds_count: int = 0
    recent_refunds: list[dict] = []
    registrations_confirmed: int = 0
    registrations_pending: int = 0
    registrations_cancelled: int = 0
    checked_in: int = 0
    events_published: int = 0
    events_total: int = 0
    seats_capacity: int = 0
    seats_taken: int = 0
    # Capacity is per event unit, so the totals are reported per unit as well;
    # a single number mixed people and teams.
    capacity_by_unit: dict[str, int] = {}
    seats_taken_by_unit: dict[str, int] = {}
    recent_registrations: list[dict] = []
    sales_by_day: list[dict] = []
    category_split: list[dict] = []
    # Attendee logistics for the desk, kitchen and hostel teams.
    gender_split: list[dict] = []
    food_split: list[dict] = []
    accommodation: dict = {}
    pass_categories: list[dict] = []
    event_registrations: list[dict] = []


class PolicyView(CamelModel):
    id: uuid.UUID
    version: int
    is_current: bool = False
    pass_price_paise: int
    lunch_included_days: list[str] = []
    included_event_count: int
    included_selection_mode: str
    included_value_cap_paise: int | None = None
    cap_inclusive: bool = True
    # 0 = cheapest first, 1 = expensive first
    allowance_pack_order: int = Field(default=0, ge=0, le=1)
    # 0 = cheapest first, 1 = expensive first
    allowance_pack_order: int = Field(default=0, ge=0, le=1)
    selection_change_deadline: datetime | None = None
    addon_requires_pass: bool = True
    team_members_require_pass: bool = True
    team_fee_basis_default: str = "per_participant"
    hold_minutes: int = 15
    refund_rules: dict = {}
    gst_note: str | None = None
    platform_fee_bps: int = 0
    platform_fee_exempt_under_paise: int = 0
    reason: str | None = None
    created_at: datetime
    created_by_name: str | None = None


class PolicyUpdate(StrictCamelModel):
    pass_price_paise: int
    lunch_included_days: list[str] = []
    included_event_count: int
    included_selection_mode: str = Field(default="exact", pattern="^(exact|up_to)$")
    included_value_cap_paise: int | None = None
    cap_inclusive: bool = True
    # 0 = cheapest first, 1 = expensive first
    allowance_pack_order: int = Field(default=0, ge=0, le=1)
    selection_change_deadline: datetime | None = None
    addon_requires_pass: bool = True
    team_members_require_pass: bool = True
    team_fee_basis_default: str = Field(default="per_participant", pattern="^per_participant$")
    hold_minutes: int = 15
    refund_rules: dict = {}
    gst_note: str | None = None
    platform_fee_bps: int = Field(default=0, ge=0, le=2500)
    platform_fee_exempt_under_paise: int = Field(default=0, ge=0)
    reason: str | None = None
    override_price_lock: bool = False


class PolicyCheck(CamelModel):
    ok: bool
    blocking: list[str] = []
    warnings: list[str] = []
    impact: dict = {}


class EventUpsert(StrictCamelModel):
    category_id: uuid.UUID
    slug: str = Field(pattern="^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str
    summary: str
    description_md: str = ""
    rules_md: str = ""
    prizes_md: str = ""
    solo_guide_md: str = ""
    team_guide_md: str = ""
    format: str = Field(pattern="^(individual|team)$")
    team_min_size: int = 1
    team_max_size: int = 1
    base_value_paise: int = 0
    included_eligible: bool = True
    addon_price_paise: int = 0
    addon_charge_basis: str = Field(default="per_participant", pattern="^(per_participant|per_team)$")
    team_fee_basis: str | None = Field(default="per_participant")
    capacity: int = 50
    capacity_unit: str = Field(default="participants", pattern="^(participants|entries)$")
    starts_at: datetime
    ends_at: datetime
    venue_room: str | None = ""
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None
    requires_approval: bool = False
    icon_id: uuid.UUID | None = None
    banner_url: str | None = None
    accent: str = Field(default="cyan", pattern="^(cyan|amber|orange|violet|lime|rose|ice)$")
    is_featured: bool = False
    sort_order: int = 0
    status: str = Field(default="draft", pattern="^(draft|published|open|closed|cancelled)$")
    change_reason: str | None = None

    @field_validator("banner_url", mode="before")
    @classmethod
    def _normalize_banner_url(cls, value: str | None) -> str | None:
        return normalize_media_url(value)


class EventAdminView(CamelModel):
    id: uuid.UUID
    slug: str
    title: str
    summary: str
    category_id: uuid.UUID
    category_name: str
    format: str
    team_min_size: int
    team_max_size: int
    base_value_paise: int
    addon_price_paise: int
    capacity: int
    status: str
    is_featured: bool
    starts_at: datetime
    ends_at: datetime
    venue_room: str | None = None
    banner_url: str | None = None
    price_history: list[dict] = []
    created_at: datetime


class CategoryUpsert(StrictCamelModel):
    name: str
    slug: str = Field(pattern="^[a-z0-9]+(?:-[a-z0-9]+)*$")
    display_order: int = 0
    accent: str = Field(default="cyan", pattern="^(cyan|amber|orange|violet|lime|rose|ice)$")
    icon_id: uuid.UUID | None = None


class AdminUserRow(CamelModel):
    id: uuid.UUID
    full_name: str
    email: str
    email_verified: bool
    status: str
    college_name: str | None = None
    phone: str | None = None
    student_identifier: str | None = None
    roles: list[str] = []
    pass_status: str | None = None
    created_at: datetime
    last_login_at: datetime | None = None


class MembershipGrant(StrictCamelModel):
    email: str
    role: str = Field(
        pattern="^(edition_admin|event_coordinator|finance_admin|checkin_staff)$"
    )


class UserStatusUpdate(StrictCamelModel):
    status: str = Field(pattern="^(active|suspended)$")
    reason: str | None = None


class PaymentRow(CamelModel):
    id: uuid.UUID
    user_name: str
    user_email: str
    purpose: str
    amount_paise: int
    status: str
    gateway_order_id: str | None = None
    created_at: datetime
    paid_at: datetime | None = None


class RefundCreate(StrictCamelModel):
    order_id: uuid.UUID
    amount_paise: int
    reason_code: str
    reason_note: str | None = None


class RefundRow(CamelModel):
    id: uuid.UUID
    order_id: uuid.UUID
    amount_paise: int
    reason_code: str
    reason_note: str | None = None
    status: str
    requested_by_name: str | None = None
    approved_by_name: str | None = None
    created_at: datetime
    processed_at: datetime | None = None


class CustomCredentialUpsert(StrictCamelModel):
    """Studio card payload. The code is optional: blank means "generate one".

    Length caps mirror the columns, and name/role reject blanks: a card printed
    with an empty name fails the one job a badge has, which is identifying
    whoever is wearing it.
    """

    code: str | None = None
    # Set when the card is built for a registered attendee. The server keeps one
    # card per registration, so saving the same attendee again reopens it.
    registration_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=120)
    college: str | None = Field(default=None, max_length=200)
    branch: str | None = Field(default=None, max_length=160)
    tier: str | None = Field(default=None, max_length=120)
    # Logistics printed on the back face and shown at the desk on scan.
    gender: Literal["male", "female"] | None = None
    food_preference: Literal["veg", "non_veg"] | None = None
    needs_accommodation: bool = False
    design: dict = Field(default_factory=dict)

    @field_validator("name", "role", mode="before")
    @classmethod
    def _require_text(cls, value: object) -> object:
        """Whitespace is not a name. Reject it before it reaches the printer."""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                raise ValueError("must not be blank")
            return stripped
        return value


class CustomCredentialRevoke(StrictCamelModel):
    reason: str | None = Field(default=None, max_length=200)


class AnnouncementUpsert(StrictCamelModel):
    title: str
    body_md: str
    audience: str = Field(default="public", pattern="^(public|participants|staff)$")
    banner_url: str | None = None
    cta_label: str | None = Field(default=None, max_length=80)
    cta_url: str | None = Field(default=None, max_length=500)
    show_on_home: bool = False
    event_id: uuid.UUID | None = None
    status: str = Field(default="draft", pattern="^(draft|published)$")

    @field_validator("banner_url", mode="before")
    @classmethod
    def _normalize_banner_url(cls, value: str | None) -> str | None:
        return normalize_media_url(value)


class AnnouncementAdminView(CamelModel):
    id: uuid.UUID
    title: str
    body_md: str
    body_html: str
    audience: str
    banner_url: str | None = None
    cta_label: str | None = Field(default=None, max_length=80)
    cta_url: str | None = Field(default=None, max_length=500)
    show_on_home: bool = False
    status: str
    event_id: uuid.UUID | None = None
    published_at: datetime | None = None
    created_at: datetime


class AuditRow(CamelModel):
    id: uuid.UUID
    actor_id: uuid.UUID | None = None
    actor_name: str | None = None
    actor_role: str | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    before: dict | None = None
    after: dict | None = None
    created_at: datetime


class CheckinRequest(StrictCamelModel):
    token: str
    event_id: uuid.UUID | None = None
    scope: str = Field(default="pass", pattern="^(pass|event|lunch)$")
    day: str | None = None
    device_label: str | None = None


class CheckinResponse(CamelModel):
    result: str
    participant_name: str
    college: str | None = None
    registration_number: str | None = None
    pass_status: str | None = None
    event_title: str | None = None
    checked_in_at: datetime
    message: str | None = None


class AttendanceRow(CamelModel):
    id: uuid.UUID
    participant_name: str
    event_title: str | None = None
    day: str | None = None
    result: str
    checked_in_at: datetime
    checked_in_by_name: str | None = None


class IconView(CamelModel):
    id: uuid.UUID
    name: str
    kind: str
    mime: str
    size_bytes: int
    recolorable: bool
    status: str
    library_key: str | None = None
    url: str


class EditionUpdate(StrictCamelModel):
    name: str | None = None
    tagline: str | None = None
    venue: str | None = None
    city: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None
    status: str | None = Field(
        default=None, pattern="^(draft|published|open|closed|archived|cancelled)$"
    )
    contact_email: str | None = None
    branding: dict | None = None


class AdminForceCancelPayload(StrictCamelModel):
    reason: str = "Removed from event by administration"
    # Inside the cancellation window the desk has to say so explicitly: the
    # attendee-facing rule refuses these cancellations for a reason.
    force: bool = False
    issue_refund: bool = False
    refund_amount_paise: int | None = None
    refund_reason_note: str | None = None


class AdminProcessRefundPayload(StrictCamelModel):
    amount_paise: int | None = None
    reason_note: str | None = None


class AdminManualAttendancePayload(StrictCamelModel):
    user_id: uuid.UUID
    event_id: uuid.UUID | None = None
    day: str | None = None
    note: str | None = None


class DbPlaygroundSeedPayload(StrictCamelModel):
    user_email_or_id: str
    target: str = Field(description="'pass' | 'event' | 'both'")
    event_ids: list[uuid.UUID] = Field(default_factory=list)
    reason: str = Field(min_length=3, description="Justification for manual seed/recovery")
    # The price is taken from the edition policy, never from the request.
    mark_college_reg_approved: bool = True
    payment_reference: str | None = None


__all__ = [
    "AdminForceCancelPayload",
    "AdminProcessRefundPayload",
    "AdminManualAttendancePayload",
    "DbPlaygroundSeedPayload",
    "Metric",
    "DashboardStats",
    "PolicyView",
    "PolicyUpdate",
    "PolicyCheck",
    "EventUpsert",
    "EventAdminView",
    "CategoryUpsert",
    "AdminUserRow",
    "MembershipGrant",
    "UserStatusUpdate",
    "PaymentRow",
    "RefundCreate",
    "RefundRow",
    "AnnouncementUpsert",
    "AnnouncementAdminView",
    "AuditRow",
    "CheckinRequest",
    "CheckinResponse",
    "AttendanceRow",
    "IconView",
    "EditionUpdate",
    "CustomCredentialUpsert",
    "CustomCredentialRevoke",
]

