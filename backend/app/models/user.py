import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey, utcnow


class User(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "users"

    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_normalized: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    picture_url: Mapped[str | None] = mapped_column(String(1024))
    phone_e164: Mapped[str | None] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_users_email_normalized", "email_normalized"),)


class ParticipantProfile(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "participant_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    college_name: Mapped[str | None] = mapped_column(String(200))
    university_name: Mapped[str | None] = mapped_column(String(200))
    course: Mapped[str | None] = mapped_column(String(120))
    branch: Mapped[str | None] = mapped_column(String(120))
    year_of_study: Mapped[int | None] = mapped_column(Integer)
    # The same operational answers the pass form asks: the door, the kitchen and
    # the hostel read them. Stored as 0/1, spoken as names through core/attendee.
    gender: Mapped[int | None] = mapped_column(SmallInteger)
    food_preference: Mapped[int | None] = mapped_column(SmallInteger)
    needs_accommodation: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    student_identifier_enc: Mapped[str | None] = mapped_column(Text)
    student_identifier_last4: Mapped[str | None] = mapped_column(String(8))
    institution_email: Mapped[str | None] = mapped_column(String(320))


class Session(Base, UUIDPrimaryKey):
    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    csrf_secret: Mapped[str] = mapped_column(String(64), nullable=False)
    auth_level: Mapped[str] = mapped_column(String(20), default="basic", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    mfa_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_prefix: Mapped[str | None] = mapped_column(String(64))
    user_agent_hash: Mapped[str | None] = mapped_column(String(64))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(80))


class MfaCredential(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "mfa_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MfaRecoveryCode(Base, UUIDPrimaryKey):
    __tablename__ = "mfa_recovery_codes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StaffInvite(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "staff_invites"

    email_normalized: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    roles: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    edition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("convention_editions.id", ondelete="CASCADE")
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claimed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class EditionMembership(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "edition_memberships"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    edition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("convention_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (UniqueConstraint("user_id", "edition_id", "role", name="uq_membership"),)
