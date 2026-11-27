"""Participant API schemas for passes, selections, teams, tickets, verification."""

import uuid
from datetime import datetime
from pydantic import Field

from app.schemas.common import CamelModel, StrictCamelModel


class SelectedEvent(CamelModel):
    event_id: uuid.UUID
    slug: str
    title: str
    category: str
    format: str
    base_value_paise: int
    addon_price_paise: int
    starts_at: datetime
    accent: str | None = None
    selected: bool = False
    status: str = "open"
    capacity: int | None = None
    seats_taken: int = 0
    seats_left: int | None = None
    selectable: bool = True


class SelectionState(CamelModel):
    pass_id: uuid.UUID
    pass_status: str
    selections: list[SelectedEvent] = []
    count: int = 0
    value_paise: int = 0
    cap_paise: int | None = None
    remaining_paise: int | None = None
    excess_paise: int = 0
    paid_delta_paise: int = 0
    due_paise: int = 0
    required_count: int = 0
    up_to: bool = False
    mode: str = "exact"
    cap_inclusive: bool = True
    valid: bool = False
    deadline: datetime | None = None
    locked: bool = False
    message: str | None = None


class PassView(CamelModel):
    id: uuid.UUID
    edition_id: uuid.UUID
    price_paise: int
    policy_version: int
    status: str
    lunch_days: list[str] = []
    paid_at: datetime | None = None
    selection: SelectionState | None = None
    created_at: datetime


class SelectionUpdate(StrictCamelModel):
    event_ids: list[uuid.UUID]


class AddonRequest(StrictCamelModel):
    event_ids: list[uuid.UUID]
    idempotency_key: str | None = None


class RegistrationView(CamelModel):
    id: uuid.UUID
    registration_number: str
    event_id: uuid.UUID
    event_title: str
    event_slug: str
    category: str
    kind: str
    fee_paise: int
    price_basis: str | None = None
    status: str
    created_at: datetime
    team_id: uuid.UUID | None = None
    team_name: str | None = None
    reservation_expires_at: datetime | None = None
    order_id: uuid.UUID | None = None
    order_platform_fee_paise: int = 0
    event_starts_at: datetime | None = None
    event_status: str | None = None
    cancelled_at: datetime | None = None
    cancelled_by: str | None = None
    cancellation_reason: str | None = None
    gateway_order_id: str | None = None
    payment_id: str | None = None
    paid_at: datetime | None = None
    payment_status: str | None = None
    refund_status: str | None = None
    refunded_paise: int = 0
    billable: bool = False
    billing_role: str = "self"
    payer_user_id: uuid.UUID | None = None


class TeamMemberView(CamelModel):
    user_id: uuid.UUID
    full_name: str
    college_name: str | None = None
    is_leader: bool = False
    seat_status: str | None = None


class TeamView(CamelModel):
    id: uuid.UUID
    name: str
    event_id: uuid.UUID
    event_title: str
    event_slug: str
    leader_id: uuid.UUID
    is_leader: bool = False
    status: str = "active"
    max_size: int = 4
    fee_basis: str = "per_participant"
    fee_paise: int = 0
    leader_paid: bool = True
    members: list[TeamMemberView] = []
    invite_code: str | None = None
    invite_link: str | None = None
    formation_state: str = "forming"
    min_size: int = 1
    member_count: int = 0


class TeamCreate(StrictCamelModel):
    event_id: uuid.UUID
    name: str = Field(min_length=2, max_length=100)


class TeamJoin(StrictCamelModel):
    invite_code: str = Field(min_length=4, max_length=32)


class QuoteRequest(StrictCamelModel):
    event_ids: list[uuid.UUID]


class CheckoutRequest(StrictCamelModel):
    quote_id: uuid.UUID


class QuoteLineView(CamelModel):
    event_id: uuid.UUID
    title: str
    slug: str = ""
    format: str = "individual"
    base_value_paise: int = 0
    list_paise: int = 0
    covered_paise: int = 0
    due_paise: int = 0
    basis: str = "addon"
    kind: str | None = None
    action: str = "create"


class QuoteView(CamelModel):
    quote_id: uuid.UUID
    lines: list[QuoteLineView] = []
    covered_paise: int = 0
    due_paise: int = 0
    expires_at: datetime


class WorklistRowView(CamelModel):
    event_id: uuid.UUID
    slug: str
    title: str
    summary: str = ""
    format: str
    category: str = "General"
    starts_at: datetime | None = None
    venue: str = ""
    capacity: int | None = None
    price: dict = {}
    state: str = "available"
    seat: dict | None = None
    team: dict | None = None
    actions: list[str] = []


class WorklistView(CamelModel):
    allowance: dict = {}
    totals: dict = {}
    rows: list[WorklistRowView] = []


class TicketView(CamelModel):
    id: uuid.UUID
    token: str
    status: str
    issued_at: datetime
    kind: str
    title: str
    registration_number: str
    attended_days: list[str] = []


class PaymentOrderView(CamelModel):
    id: uuid.UUID
    purpose: str
    amount_paise: int
    status: str
    gateway_order_id: str | None = None
    razorpay_key_id: str | None = None
    mock: bool = False
    linked_record_id: uuid.UUID | None = None
    created_at: datetime


class CancelRequest(CamelModel):
    reason: str | None = None


__all__ = [
    "SelectedEvent",
    "SelectionState",
    "PassView",
    "SelectionUpdate",
    "AddonRequest",
    "RegistrationView",
    "TeamMemberView",
    "TeamView",
    "TeamCreate",
    "TeamJoin",
    "QuoteRequest",
    "CheckoutRequest",
    "QuoteLineView",
    "QuoteView",
    "WorklistRowView",
    "WorklistView",
    "TicketView",
    "PaymentOrderView",
    "CancelRequest",
]

