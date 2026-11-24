"""Custom ID-card credentials issued from the admin studio.

Every row is a card that exists independently of a college registration: staff,
faculty, sponsors, press and one-off guests. The row owns the printed identity
and design, a human code the desk can type, and a signed token the QR carries.
Because the record is stored, the desk can resolve a scan, the admin can list
saved cards, reprint one later and revoke a lost badge.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey


class CustomCredential(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "custom_credentials"

    edition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("convention_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Set when the studio built this card for a registered attendee. The link is
    # what makes "load from registered attendees" reopen the same card (and its
    # signed QR) instead of minting a second ID under the attendee's number.
    registration_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("college_registrations.id", ondelete="SET NULL"), index=True
    )
    # Printed credential ID. Unique per edition so a typed ID resolves one person.
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(120), nullable=False)
    college: Mapped[str | None] = mapped_column(String(200))
    branch: Mapped[str | None] = mapped_column(String(160))
    tier: Mapped[str | None] = mapped_column(String(120))
    # Logistics the desk and the kitchen/accommodation teams read off a scan.
    # Kept on the row (not in ``design``) because they are operational data.
    # 0/1 codes, decoded by core/attendee.py for the API, the card and the desk.
    gender: Mapped[int | None] = mapped_column(SmallInteger)
    food_preference: Mapped[int | None] = mapped_column(SmallInteger)
    needs_accommodation: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    # Presentation only (palette, layout, photo URL, verified flag, accent).
    design: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    issued_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        # The database, not application code, decides who owns an ID. A
        # check-then-insert race would hand two people the same printed code.
        UniqueConstraint("edition_id", "code", name="uq_custom_credential_edition_code"),
        # One studio card per registration: re-saving an attendee's card finds
        # the existing row instead of creating a duplicate identity.
        UniqueConstraint(
            "edition_id", "registration_id", name="uq_custom_credential_edition_registration"
        ),
    )
