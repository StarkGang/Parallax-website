"""Ticket generation, QR codes and validation.

Tickets never store the raw credential. The scannable token is derived from the
ticket id with an HMAC, so it can be recomputed for display and verified at the
door without keeping a plaintext secret at rest.
"""

import re
import uuid
from datetime import UTC, datetime
from typing import Any

import qrcode
import qrcode.image.svg

QR_PALETTES: dict[str, dict[str, str]] = {
    "cyan": {
        "fg1": "#38bdf8",
        "fg2": "#818cf8",
        "bg": "#070b14",
        "border": "#38bdf8",
        "accent": "#38bdf8",
    },
    "violet": {
        "fg1": "#c084fc",
        "fg2": "#a855f7",
        "bg": "#0d0716",
        "border": "#c084fc",
        "accent": "#c084fc",
    },
    "amber": {
        "fg1": "#fbbf24",
        "fg2": "#f59e0b",
        "bg": "#140c04",
        "border": "#fbbf24",
        "accent": "#fbbf24",
    },
    "orange": {
        "fg1": "#fb923c",
        "fg2": "#f97316",
        "bg": "#140804",
        "border": "#fb923c",
        "accent": "#fb923c",
    },
    "lime": {
        "fg1": "#a3e635",
        "fg2": "#4ade80",
        "bg": "#071207",
        "border": "#a3e635",
        "accent": "#a3e635",
    },
    "rose": {
        "fg1": "#fb7185",
        "fg2": "#f43f5e",
        "bg": "#14060b",
        "border": "#fb7185",
        "accent": "#fb7185",
    },
    "ice": {
        "fg1": "#7dd3fc",
        "fg2": "#06b6d4",
        "bg": "#050e17",
        "border": "#7dd3fc",
        "accent": "#7dd3fc",
    },
    "light": {
        "fg1": "#0f172a",
        "fg2": "#1e293b",
        "bg": "#ffffff",
        "border": "#94a3b8",
        "accent": "#0f172a",
    },
}

PARALLAX_VECTOR_PATH = (
    "M3625,990H3490L3330,819,3173,988H3046l220-238L3033,506h132l165,173,109-115h126L3396,747Z"
    "M2498,821c31.63-184.255,209-186,209-186h155c-8.87-55.755-63-62-63-62l-83-82h99c146.13,13.745,148,156,148,156l1,330H2627C2492.62,953.245,2498,821,2498,821Z"
    "M2350,272l131,79v784l-131-88V272Zm-200-24,131,79v784l-131-88V248Z"
    "M1655,821c31.62-184.255,209-186,209-186h155c-8.88-55.755-63-62-63-62l-83-82h99c146.12,13.745,148,156,148,156l1,330H1784C1649.63,953.245,1655,821,1655,821Zm-79-183-1,230L1429,990V444l68,38,48,45c51-53.753,144-46,144-46v98C1592.5,553.747,1576,638,1576,638Z"
    "M923,821c31.625-184.255,209-186,209-186h155c-8.87-55.755-63-62-63-62l-83-82h99c146.13,13.745,148,156,148,156l1,330H1052C917.625,953.245,923,821,923,821Z"
    "M779,712H630V904l-166,98,2-300,86-44c7.792-7.755,76-67,76-67H789c87.292-22.755,73-109,73-109,11.292-82.255-385-239-385-239V166L833,301c143.125,46.453,147,191,147,191C976.125,697.453,779,712,779,712Z"
    "m508,17V872H1105s-67.87-3.255-71-65c0,0,2.62-54.255,63-73Z"
    "m732,0V872H1837s-67.87-3.255-71-65c0,0,2.62-54.255,63-73Z"
    "m843,0V872H2680s-67.88-3.255-71-65c0,0,2.62-54.255,63-73Z"
)
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


def public_registration_code(registration_number: str) -> str:
    """Signed code for the public credential URL.

    A bare registration number is short enough to guess; the signature means
    only a link this server issued resolves to a participant, so the public
    verification page cannot be used to enumerate attendees.
    """
    number = (registration_number or "").strip().upper()
    signature = hash_token(f"public-registration:{number}")[:12].upper()
    return f"{number}.{signature}"


def public_registration_number(raw: str) -> str | None:
    value = (raw or "").strip().upper()
    if "." not in value:
        return None
    number, signature = value.rsplit(".", 1)
    expected = hash_token(f"public-registration:{number}")[:12].upper()
    if not number or not constant_compare(signature, expected):
        return None
    return number


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


async def issue_for_registration(db: AsyncSession, reg: Registration) -> Ticket | None:
    if reg.status not in ("confirmed", "reserved"):
        return None
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


async def revoke_for_registration(db: AsyncSession, registration_id: uuid.UUID) -> int:
    rows = list(
        (
            await db.execute(
                select(Ticket).where(
                    Ticket.registration_id == registration_id,
                    Ticket.status.in_(["active", "valid"]),
                )
            )
        ).scalars()
    )
    for t in rows:
        t.status = "revoked"
        t.revoked_at = datetime.now(UTC)
    await db.flush()
    return len(rows)


async def revoke_for_pass(db: AsyncSession, pass_id: uuid.UUID) -> int:
    rows = list(
        (
            await db.execute(
                select(Ticket).where(
                    Ticket.pass_id == pass_id,
                    Ticket.status.in_(["active", "valid"]),
                )
            )
        ).scalars()
    )
    for t in rows:
        t.status = "revoked"
        t.revoked_at = datetime.now(UTC)
    await db.flush()
    return len(rows)


def qr_svg(token: str, accent: str = "cyan") -> str:
    """A production-ready, scannable SVG QR code customized to the Parallax theme."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2,
        image_factory=qrcode.image.svg.SvgPathFillImage,
    )
    qr.add_data(token)
    qr.make(fit=True)
    img = qr.make_image(attrib={"class": "parallax-ticket-qr"})
    raw = img.to_string().decode("utf-8")

    pal = QR_PALETTES.get(accent.lower(), QR_PALETTES["cyan"])
    vb_match = re.search(r'viewBox="([^"]+)"', raw)
    vb = vb_match.group(1) if vb_match else "0 0 33 33"
    parts = [float(p) for p in vb.split()]
    w = parts[2] if len(parts) >= 3 else 33.0
    h = parts[3] if len(parts) >= 4 else 33.0

    path_match = re.search(r'\bd="([^"]+)"', raw)
    d = path_match.group(1) if path_match else ""

    badge_w = w * 0.44
    logo_w = badge_w * 0.82
    logo_h = logo_w / 3.262
    badge_h = logo_h + (badge_w * 0.18)
    badge_x = (w - badge_w) / 2
    badge_y = (h - badge_h) / 2
    logo_x = (w - logo_w) / 2
    logo_y = (h - logo_h) / 2

    # Return branded, scannable cybernetic SVG with official Parallax vector logo
    return (
        f'<svg class="parallax-ticket-qr" width="100%" height="100%" viewBox="{vb}" xmlns="http://www.w3.org/2000/svg">\n'
        f"  <defs>\n"
        f'    <linearGradient id="qrGrad" x1="0%" y1="0%" x2="100%" y2="100%">\n'
        f'      <stop offset="0%" stop-color="{pal["fg1"]}" />\n'
        f'      <stop offset="100%" stop-color="{pal["fg2"]}" />\n'
        f"    </linearGradient>\n"
        f'    <filter id="badgeGlow" x="-20%" y="-20%" width="140%" height="140%">\n'
        f'      <feDropShadow dx="0" dy="0" stdDeviation="0.35" flood-color="{pal["border"]}" flood-opacity="0.3" />\n'
        f"    </filter>\n"
        f"  </defs>\n"
        f'  <rect width="100%" height="100%" rx="2.5" fill="{pal["bg"]}" />\n'
        f'  <rect x="0.4" y="0.4" width="{w - 0.8:.2f}" height="{h - 0.8:.2f}" rx="2" fill="none" stroke="{pal["border"]}" stroke-width="0.35" stroke-opacity="0.35" />\n'
        f'  <path d="{d}" fill="url(#qrGrad)" />\n'
        f'  <!-- Center Parallax Logo Shield -->\n'
        f'  <rect x="{badge_x:.2f}" y="{badge_y:.2f}" width="{badge_w:.2f}" height="{badge_h:.2f}" rx="1.0" fill="{pal["bg"]}" stroke="{pal["border"]}" stroke-width="0.35" filter="url(#badgeGlow)" />\n'
        f'  <svg x="{logo_x:.2f}" y="{logo_y:.2f}" width="{logo_w:.2f}" height="{logo_h:.2f}" viewBox="0 0 3161 969">\n'
        f'    <path fill="{pal["accent"]}" d="{PARALLAX_VECTOR_PATH}" transform="translate(-464 -166)" />\n'
        f"  </svg>\n"
        f"</svg>"
    )


def plain_qr_svg(token: str) -> str:
    """Standard square QR code: black modules on white with a quiet zone.

    Used for the printed pass, where any gradient, rounded module or centre logo
    only hurts scan reliability.
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(token)
    qr.make(fit=True)
    image = qr.make_image(
        image_factory=qrcode.image.svg.SvgPathFillImage,
        attrib={"class": "parallax-pass-qr"},
    )
    return image.to_string().decode("utf-8")


def id_card_qr_svg(token: str) -> str:
    """A custom, scannable QR code matching the PARALLAX ID Card Design specifications:
    - Error correction: Level H
    - Shape: rounded dot modules (near black #0a0a0c) on off-white #f4f2ee panel
    - Eyes (corner markers): rounded squares with violet #7c5cff outer ring and coral #ff6b57 inner dot
    - Parallax effect: faint violet ghost copy of QR offset behind it at 20% opacity
    - Center: small PARALLAX 'P' shield badge in a circle (<= 15% area)
    - High contrast, ultra-crisp scannability
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2,
    )
    qr.add_data(token)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    n = len(matrix)
    b = 2

    eyes = [
        (b + 3.5, b + 3.5),
        (n - b - 3.5, b + 3.5),
        (b + 3.5, n - b - 3.5),
    ]

    def in_eye(r: int, c: int) -> bool:
        for cx, cy in eyes:
            if abs(c + 0.5 - cx) <= 3.5 and abs(r + 0.5 - cy) <= 3.5:
                return True
        return False

    center = n / 2.0
    r_center = n * 0.12

    def in_center(r: int, c: int) -> bool:
        return ((c + 0.5 - center) ** 2 + (r + 0.5 - center) ** 2) <= (r_center ** 2)

    parts = [
        f'<svg class="parallax-idcard-qr" viewBox="0 0 {n} {n}" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">',
        f'  <rect width="{n}" height="{n}" rx="2" fill="#f4f2ee" />',
    ]

    ghost_dots = []
    real_dots = []
    for r in range(n):
        for c in range(n):
            if matrix[r][c] and not in_eye(r, c) and not in_center(r, c):
                ghost_dots.append(
                    f'  <circle cx="{c + 0.65:.2f}" cy="{r + 0.65:.2f}" r="0.38" fill="#7c5cff" fill-opacity="0.22" />'
                )
                real_dots.append(
                    f'  <circle cx="{c + 0.5:.2f}" cy="{r + 0.5:.2f}" r="0.38" fill="#0a0a0c" />'
                )
    parts.extend(ghost_dots)
    parts.extend(real_dots)

    for cx, cy in eyes:
        parts.append(
            f'  <rect x="{cx - 3.2:.2f}" y="{cy - 3.2:.2f}" width="6.4" height="6.4" rx="1.6" fill="none" stroke="#7c5cff" stroke-width="0.85" />'
        )
        parts.append(
            f'  <rect x="{cx - 1.5:.2f}" y="{cy - 1.5:.2f}" width="3.0" height="3.0" rx="0.75" fill="#ff6b57" />'
        )

    badge_radius = r_center
    parts.append(
        f'  <circle cx="{center:.2f}" cy="{center:.2f}" r="{badge_radius:.2f}" fill="#f4f2ee" stroke="#7c5cff" stroke-width="0.5" />'
    )
    p_w = badge_radius * 1.15
    p_h = p_w * (836.0 / 516.0)
    p_x = center - (p_w / 2.0)
    p_y = center - (p_h / 2.0)
    parts.append(
        f'  <svg x="{p_x:.2f}" y="{p_y:.2f}" width="{p_w:.2f}" height="{p_h:.2f}" viewBox="0 0 520 840">\n'
        f'    <path fill="#7c5cff" d="M779,712H630V904l-166,98,2-300,86-44c7.792-7.755,76-67,76-67H789c87.292-22.755,73-109,73-109,11.292-82.255-385-239-385-239V166L833,301c143.125,46.453,147,191,147,191C976.125,697.453,779,712,779,712Z" transform="translate(-464 -166)"/>\n'
        f'  </svg>'
    )
    parts.append('</svg>')
    return "\n".join(parts)


async def ticket_payload(db: AsyncSession, ticket: Ticket) -> dict[str, Any]:
    kind = "pass" if ticket.pass_id else "registration"
    title = "Convention Entry Pass"
    reg_num = "PASS"
    starts_at = None
    ends_at = None
    venue_room = None
    if ticket.registration_id:
        reg = await db.get(Registration, ticket.registration_id)
        if reg:
            reg_num = reg.registration_number
            event = await db.get(Event, reg.event_id)
            if event:
                title = event.title
                starts_at = event.starts_at.isoformat() if event.starts_at else None
                ends_at = event.ends_at.isoformat() if event.ends_at else None
                venue_room = event.venue_room

    return {
        "id": str(ticket.id),
        "token": ticket_token_for(ticket.id),
        "status": ticket.status,
        "issuedAt": ticket.issued_at.isoformat() if ticket.issued_at else None,
        "kind": kind,
        "title": title,
        "registrationNumber": reg_num,
        "startsAt": starts_at,
        "endsAt": ends_at,
        "venueRoom": venue_room,
        "attendedDays": [],
    }


async def resolve(db: AsyncSession, raw: str, edition_id: uuid.UUID) -> Ticket:
    token_str = (raw or "").strip()
    if "/c/" in token_str:
        token_str = token_str.split("/c/")[-1].split("?")[0].strip()

    ticket_id = parse_ticket_token(token_str)
    if ticket_id is not None:
        ticket = await db.get(Ticket, ticket_id)
        if ticket and ticket.edition_id == edition_id and token_is_valid(token_str, ticket.id):
            if ticket.status not in ("active", "valid"):
                raise NotFound("This ticket is no longer valid.")
            return ticket

    # Fallback: resolve by a signed public code, a scanned registration number
    # or an ID card credential.
    from app.models.registration import CollegeRegistration

    lookup_code = public_registration_number(token_str) or token_str
    col_reg = (
        await db.execute(
            select(CollegeRegistration).where(
                (CollegeRegistration.registration_number == lookup_code)
                | (CollegeRegistration.registration_number == lookup_code.upper())
            )
        )
    ).scalars().first()
    if col_reg and col_reg.edition_id == edition_id:
        pass_ticket = (
            await db.execute(
                select(Ticket).where(
                    Ticket.user_id == col_reg.user_id,
                    Ticket.edition_id == edition_id,
                    Ticket.status.in_(["active", "valid"]),
                )
            )
        ).scalars().first()
        if pass_ticket:
            return pass_ticket

    raise NotFound("Invalid ticket token or registration code.")


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
    "public_registration_code",
    "public_registration_number",
    "issue_for_pass",
    "issue_for_registration",
    "revoke_for_registration",
    "revoke_for_pass",
    "qr_svg",
    "ticket_payload",
    "resolve",
    "rotate",
]
