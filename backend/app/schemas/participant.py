"""Participant API schemas for passes, selections, teams, tickets, verification."""

import uuid
from datetime import datetime
from pydantic import Field

from app.schemas.common import CamelModel


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
    required_count: int = 0
    up_to: bool = False
    mode: str = "exact"
    cap_inclusive: bool = True
    valid: bool = False
    deadline: datetime | None = None
    locked: bool = False
    message: str | None = None


class PassOrderRequest(CamelModel):
    edition_id: uuid.UUID


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


class SelectionUpdate(CamelModel):
    event_ids: list[uuid.UUID]


class AddonRequest(CamelModel):
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
    status: str
    created_at: datetime
    team_id: uuid.UUID | None = None
    team_name: str | None = None
    reservation_expires_at: datetime | None = None
    order_id: uuid.UUID | None = None


class TeamMemberView(CamelModel):
    user_id: uuid.UUID
    full_name: str
    college_name: str | None = None
    is_leader: bool = False


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
    members: list[TeamMemberView] = []
    invite_code: str | None = None


class TeamCreate(CamelModel):
    event_id: uuid.UUID
    name: str = Field(min_length=2, max_length=100)


class TeamJoin(CamelModel):
    invite_code: str = Field(min_length=4, max_length=32)


class TicketView(CamelModel):
    id: uuid.UUID
    token: str
    status: str
    issued_at: datetime
    kind: str
    title: str
    registration_number: str
    attended_days: list[str] = []


class VerificationSubmit(CamelModel):
    method: str = Field(pattern="^(roster|college_email|document)$")
    institution_email: str | None = None


class VerificationView(CamelModel):
    status: str
    method: str | None = None
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None
    document_name: str | None = None
    can_resubmit: bool = True


class EmailConfirm(CamelModel):
    code: str = Field(min_length=4, max_length=16)


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
    "PassOrderRequest",
    "PassView",
    "SelectionUpdate",
    "AddonRequest",
    "RegistrationView",
    "TeamMemberView",
    "TeamView",
    "TeamCreate",
    "TeamJoin",
    "TicketView",
    "VerificationSubmit",
    "VerificationView",
    "EmailConfirm",
    "PaymentOrderView",
    "CancelRequest",
]

