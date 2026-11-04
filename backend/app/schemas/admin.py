"""Admin schemas for dashboard, events, policies, verifications, checkin and users."""

import uuid
from datetime import datetime
from pydantic import Field

from app.schemas.common import CamelModel


class Metric(CamelModel):
    label: str
    value: int | float | str
    unit: str | None = None


class DashboardStats(CamelModel):
    edition_id: uuid.UUID
    edition_name: str
    passes_sold: int = 0
    passes_pending: int = 0
    revenue_paise: int = 0
    refunded_paise: int = 0
    registrations_confirmed: int = 0
    registrations_pending: int = 0
    verifications_pending: int = 0
    checked_in: int = 0
    events_published: int = 0
    events_total: int = 0
    seats_capacity: int = 0
    seats_taken: int = 0
    recent_registrations: list[dict] = []
    sales_by_day: list[dict] = []
    category_split: list[dict] = []


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
    selection_change_deadline: datetime | None = None
    addon_requires_pass: bool = True
    team_members_require_pass: bool = True
    team_fee_basis_default: str = "per_participant"
    hold_minutes: int = 15
    refund_rules: dict = {}
    gst_note: str | None = None
    reason: str | None = None
    created_at: datetime
    created_by_name: str | None = None


class PolicyUpdate(CamelModel):
    pass_price_paise: int
    lunch_included_days: list[str] = []
    included_event_count: int
    included_selection_mode: str = Field(default="exact", pattern="^(exact|up_to)$")
    included_value_cap_paise: int | None = None
    cap_inclusive: bool = True
    selection_change_deadline: datetime | None = None
    addon_requires_pass: bool = True
    team_members_require_pass: bool = True
    team_fee_basis_default: str = Field(default="per_participant", pattern="^(per_team|per_participant)$")
    hold_minutes: int = 15
    refund_rules: dict = {}
    gst_note: str | None = None
    reason: str | None = None
    override_price_lock: bool = False


class PolicyCheck(CamelModel):
    ok: bool
    blocking: list[str] = []
    warnings: list[str] = []
    impact: dict = {}


class EventUpsert(CamelModel):
    category_id: uuid.UUID
    slug: str = Field(pattern="^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str
    summary: str
    description_md: str = ""
    rules_md: str = ""
    prizes_md: str = ""
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
    accent: str = Field(default="cyan", pattern="^(cyan|amber|orange|violet|lime|rose|ice)$")
    is_featured: bool = False
    sort_order: int = 0
    status: str = Field(default="draft", pattern="^(draft|published|open|closed|cancelled)$")
    change_reason: str | None = None


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
    price_history: list[dict] = []
    coordinator_names: list[str] = []
    created_at: datetime


class CategoryUpsert(CamelModel):
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
    verification_status: str = "unverified"
    pass_status: str | None = None
    created_at: datetime
    last_login_at: datetime | None = None


class MembershipGrant(CamelModel):
    email: str
    role: str = Field(
        pattern="^(edition_admin|event_coordinator|finance_admin|eligibility_verifier|checkin_staff)$"
    )


class UserStatusUpdate(CamelModel):
    status: str = Field(pattern="^(active|suspended)$")
    reason: str | None = None


class VerificationRow(CamelModel):
    id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    email: str
    college_name: str | None = None
    method: str
    status: str
    document_name: str | None = None
    submitted_at: datetime
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None
    student_identifier: str | None = None


class VerificationDecision(CamelModel):
    decision: str = Field(pattern="^(verified|rejected)$")
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


class RefundCreate(CamelModel):
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


class AnnouncementUpsert(CamelModel):
    title: str
    body_md: str
    audience: str = Field(default="public", pattern="^(public|participants|staff)$")
    event_id: uuid.UUID | None = None
    status: str = Field(default="draft", pattern="^(draft|published)$")


class AnnouncementAdminView(CamelModel):
    id: uuid.UUID
    title: str
    body_md: str
    body_html: str
    audience: str
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


class CheckinRequest(CamelModel):
    token: str
    event_id: uuid.UUID | None = None
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


class EditionUpdate(CamelModel):
    name: str | None = None
    tagline: str | None = None
    venue: str | None = None
    city: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None
    status: str | None = Field(default=None, pattern="^(draft|published|archived)$")
    contact_email: str | None = None
    allowed_email_domains: list[str] | None = None
    branding: dict | None = None


__all__ = [
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
    "VerificationRow",
    "VerificationDecision",
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
]

