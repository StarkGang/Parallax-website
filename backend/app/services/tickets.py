"""Ticket generation, QR codes and validation.

Tickets never store the raw credential. The scannable token is derived from the
ticket id with an HMAC, so it can be recomputed for display and verified at the
door without keeping a plaintext secret at rest.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import qrcode
import qrcode.image.svg
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.core.security import constant_compare, hash_token
from app.models.commerce import ConventionPass, Registration, Ticket
from app.models.edition import Event

TOKEN_PREFIX = "PX"


def ticket_token_for(ticket_id: uuid.UUID) -> str:
    signature = hash_token(f"ticket-signature:{ticket_id}")[:16].upper()
    return f"{TOKEN_PREFIX}-{ticket_id.hex.upper()}-{signature}"


def parse_ticket_token(raw: str) -> uuid.UUID | None:
    parts = (raw or "").strip().split("-")
    if len(parts) != 3 or parts[0].upper() != TOKEN_PREFIX:
        return None
    try:
        return uuid.UUID(hex=parts[1])
    except ValueError:
        return None


def token_is_valid(raw: str, ticket_id: uuid.UUID) -> bool:
    return constant_compare((raw or "").strip().upper(), ticket_token_for(ticket_id))


async def _existing_for_pass(
    db: AsyncSession, user_id: uuid.UUID, pass_id: uuid.UUID
) -> Ticket | None:
    return (
        await db.execute(
            select(Ticket).where(
                Ticket.user_id == user_id,
                Ticket.pass_id == pass_id,
                Ticket.status.in_(["active", "valid"]),
            )
        )
    ).scalar_one_or_none()


async def _existing_for_reg(
    db: AsyncSession, user_id: uuid.UUID, reg_id: uuid.UUID
) -> Ticket | None:
    return (
        await db.execute(
            select(Ticket).where(
                Ticket.user_id == user_id,
                Ticket.registration_id == reg_id,
                Ticket.status.in_(["active", "valid"]),
            )
        )
    ).scalar_one_or_none()


async def _stamp_token(db: AsyncSession, ticket: Ticket) -> Ticket:
    token = ticket_token_for(ticket.id)
    ticket.token_hash = hash_token(token)
    ticket.token_prefix = token[:16]
    await db.flush()
    return ticket


async def issue_for_pass(db: AsyncSession, user_pass: ConventionPass) -> Ticket:
    ext = await _existing_for_pass(db, user_pass.user_id, user_pass.id)
    if ext:
        return ext
    t = Ticket(
        edition_id=user_pass.edition_id,
        user_id=user_pass.user_id,
        pass_id=user_pass.id,
        token_hash="",
        token_prefix="",
        status="active",
        issued_at=datetime.now(UTC),
    )
    db.add(t)
    await db.flush()
    return await _stamp_token(db, t)


async def issue_for_registration(db: AsyncSession, reg: Registration) -> Ticket:
    ext = await _existing_for_reg(db, reg.user_id, reg.id)
    if ext:
        return ext
    t = Ticket(
        edition_id=reg.edition_id,
        user_id=reg.user_id,
        registration_id=reg.id,
        token_hash="",
        token_prefix="",
        status="active",
        issued_at=datetime.now(UTC),
    )
    db.add(t)
    await db.flush()
    return await _stamp_token(db, t)


def qr_svg(token: str) -> str:
    """A production-ready, scannable SVG QR code carrying the ticket token."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
        image_factory=qrcode.image.svg.SvgPathFillImage,
    )
    qr.add_data(token)
    qr.make(fit=True)
    img = qr.make_image(attrib={"class": "parallax-ticket-qr"})
    return img.to_string().decode("utf-8")


async def ticket_payload(db: AsyncSession, ticket: Ticket) -> dict[str, Any]:
    kind = "pass" if ticket.pass_id else "registration"
    title = "Convention Entry Pass"
    reg_num = "PASS"
    if ticket.registration_id:
        reg = await db.get(Registration, ticket.registration_id)
        if reg:
            reg_num = reg.registration_number
            event = await db.get(Event, reg.event_id)
            if event:
                title = event.title

    return {
        "id": str(ticket.id),
        "token": ticket_token_for(ticket.id),
        "status": ticket.status,
        "issuedAt": ticket.issued_at.isoformat() if ticket.issued_at else None,
        "kind": kind,
        "title": title,
        "registrationNumber": reg_num,
        "attendedDays": [],
    }


async def resolve(db: AsyncSession, raw: str, edition_id: uuid.UUID) -> Ticket:
    ticket_id = parse_ticket_token(raw)
    if ticket_id is None:
        raise NotFound("Invalid ticket token.")
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None or ticket.edition_id != edition_id:
        raise NotFound("Invalid ticket token.")
    if not token_is_valid(raw, ticket.id):
        raise NotFound("Invalid ticket token.")
    if ticket.status not in ("active", "valid"):
        raise NotFound("This ticket is no longer valid.")
    return ticket


async def rotate(db: AsyncSession, ticket: Ticket) -> Ticket:
    # The token is derived, so rotation means revoking the old credential.
    ticket.status = "revoked"
    ticket.revoked_at = datetime.now(UTC)
    await db.flush()
    replacement = Ticket(
        edition_id=ticket.edition_id,
        user_id=ticket.user_id,
        pass_id=ticket.pass_id,
        registration_id=ticket.registration_id,
        token_hash="",
        token_prefix="",
        status="active",
        issued_at=datetime.now(UTC),
    )
    db.add(replacement)
    await db.flush()
    return await _stamp_token(db, replacement)


__all__ = [
    "TOKEN_PREFIX",
    "ticket_token_for",
    "parse_ticket_token",
    "token_is_valid",
    "issue_for_pass",
    "issue_for_registration",
    "qr_svg",
    "ticket_payload",
    "resolve",
    "rotate",
]
