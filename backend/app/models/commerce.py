import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey, utcnow


class ConventionPass(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "convention_passes"

    edition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("convention_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    lunch_days: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payment_orders.id", ondelete="SET NULL"))

    __table_args__ = (
        Index(
            "uq_convention_pass_active",
            "edition_id",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )


class IncludedEventSelection(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "included_event_selections"

    pass_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("convention_passes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    base_value_paise_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    __table_args__ = (UniqueConstraint("pass_id", "event_id", name="uq_pass_event"),)


class Team(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "teams"

    edition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("convention_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    leader_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    invite_code: Mapped[str] = mapped_column(String(16), default="", nullable=False, index=True)
    invite_code_hash: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="forming", nullable=False)
    max_size: Mapped[int] = mapped_column(Integer, default=4, nullable=False)


class TeamMember(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "team_members"

    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    is_leader: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_member"),)


class TeamInvite(Base, UUIDPrimaryKey):
    __tablename__ = "team_invites"

    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    uses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Registration(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "registrations"

    edition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("convention_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    fee_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="confirmed", nullable=False)
    reservation_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registration_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payment_orders.id", ondelete="SET NULL"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaymentOrder(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "payment_orders"

    edition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("convention_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="INR", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="created", nullable=False)
    gateway_order_id: Mapped[str | None] = mapped_column(String(80), unique=True)
    linked_record_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    notes: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaymentTransaction(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "payment_transactions"

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payment_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    gateway_payment_id: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="captured", nullable=False)
    method_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PaymentWebhookEvent(Base, UUIDPrimaryKey):
    __tablename__ = "payment_webhook_events"

    gateway_event_id: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    signature_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Refund(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "refunds"

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payment_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payment_transactions.id", ondelete="SET NULL")
    )
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(40), nullable=False)
    reason_note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    gateway_refund_id: Mapped[str | None] = mapped_column(String(80), unique=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Ticket(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "tickets"

    edition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("convention_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pass_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("convention_passes.id", ondelete="SET NULL"))
    registration_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("registrations.id", ondelete="SET NULL")
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="valid", nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AttendanceRecord(Base, UUIDPrimaryKey):
    __tablename__ = "attendance_records"

    edition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("convention_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tickets.id", ondelete="SET NULL"))
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"))
    day: Mapped[str] = mapped_column(String(20), default="1", nullable=False)
    checked_in_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    checked_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    device_label: Mapped[str | None] = mapped_column(String(80))
    result: Mapped[str] = mapped_column(String(20), default="admitted", nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "event_id", "day", name="uq_attendance"),)


class IdempotencyKey(Base, UUIDPrimaryKey):
    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    route: Mapped[str] = mapped_column(String(160), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (UniqueConstraint("key", "user_id", "route", name="uq_idempotency"),)


class EmailOutbox(Base, UUIDPrimaryKey):
    __tablename__ = "email_outbox"

    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    template: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base, UUIDPrimaryKey):
    """Append-only. The application role has INSERT and SELECT only."""

    __tablename__ = "audit_logs"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_role: Mapped[str | None] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(80))
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)
    ip_prefix: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RateLimitCounter(Base, UUIDPrimaryKey):
    __tablename__ = "rate_limit_counters"

    bucket: Mapped[str] = mapped_column(String(64), nullable=False)
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (UniqueConstraint("bucket", "subject", "window_start", name="uq_rate_limit"),)

