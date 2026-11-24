"""Studio-issued ID cards: stored credentials, printable codes, verifiable tokens.

A custom credential is not a registration and has no user account. It is a row
the organisers create for staff, faculty, sponsors, press or a one-off guest.
The printed ID is the row's ``code``; the QR carries a signed token derived from
the row id, so a scan can only mean something the server actually issued.
"""

import json
import re
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.attendee import decode_food, decode_gender, encode_food, encode_gender
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.security import constant_compare, hash_token
from app.models.credential import CustomCredential

TOKEN_PREFIX = "PXC"
CODE_PREFIX = "PXC"
# No I, O, 0 or 1: the code is read off a card and typed by hand at the desk.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
MAX_CODE_LENGTH = 32
# A card's design is presentation only: a role key, a palette index, a photo URL.
# Capping it stops a malformed client from parking megabytes in the row.
MAX_DESIGN_BYTES = 4096
# Shape of a token this module issues. The desk dispatches on it, so a studio
# card never pays for a wasted ticket lookup, and a ticket can never be
# mistaken for a credential (different prefix).
TOKEN_RE = re.compile(r"^PXC-[0-9A-F]{32}-[0-9A-F]{16}$")


def normalize_code(raw: str | None) -> str:
    return (raw or "").strip().upper().replace(" ", "")


def generate_code() -> str:
    body = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
    return f"{CODE_PREFIX}-{body}"


def token_for(credential_id: uuid.UUID) -> str:
    signature = hash_token(f"custom-credential:{credential_id}")[:16].upper()
    return f"{TOKEN_PREFIX}-{credential_id.hex.upper()}-{signature}"


def looks_like_token(raw: str | None) -> bool:
    """True for a string shaped like ``token_for`` output, without touching the DB."""
    value = (raw or "").strip()
    if "/c/" in value:
        # A phone camera may hand over the verification URL rather than the code.
        value = value.split("/c/")[-1].split("?")[0].strip()
    return bool(TOKEN_RE.match(value.upper()))


def parse_token(raw: str) -> uuid.UUID | None:
    parts = (raw or "").strip().upper().split("-")
    if len(parts) != 3 or parts[0] != TOKEN_PREFIX:
        return None
    try:
        return uuid.UUID(hex=parts[1])
    except ValueError:
        return None


def token_is_valid(raw: str, credential_id: uuid.UUID) -> bool:
    return constant_compare((raw or "").strip().upper(), token_for(credential_id))


def qr_token(credential: CustomCredential) -> str:
    """What the QR must contain. Derived, so a reprinted card keeps working."""
    return token_for(credential.id)


def _clean_text(value: str | None, field: str, *, required: bool, limit: int) -> str | None:
    text = (value or "").strip()
    if required and not text:
        raise ValidationFailed(f"{field} is required.")
    if len(text) > limit:
        raise ValidationFailed(f"{field} must be {limit} characters or fewer.")
    return text or None


def payload(credential: CustomCredential, *, entry_qr: str | None = None) -> dict:
    """Serialised card.

    ``token`` is the card's own credential token, used by unlinked cards
    (staff, faculty, sponsor, press, guest). ``entryQr`` is the linked
    attendee's own entry payload - the string their portal pass prints - and is
    None for every other card.
    """
    return {
        "id": str(credential.id),
        "registrationId": (
            str(credential.registration_id) if credential.registration_id else None
        ),
        "code": credential.code,
        "name": credential.name,
        "role": credential.role,
        "college": credential.college,
        "branch": credential.branch,
        "tier": credential.tier,
        "gender": decode_gender(credential.gender),
        "foodPreference": decode_food(credential.food_preference),
        "needsAccommodation": credential.needs_accommodation,
        "design": credential.design or {},
        "status": credential.status,
        "token": qr_token(credential),
        "entryQr": entry_qr,
        "issuedBy": str(credential.issued_by) if credential.issued_by else None,
        "revokedAt": credential.revoked_at.isoformat() if credential.revoked_at else None,
        "createdAt": credential.created_at.isoformat() if credential.created_at else None,
        "updatedAt": credential.updated_at.isoformat() if credential.updated_at else None,
    }


async def payload_with_entry(
    db: AsyncSession, credential: CustomCredential, *, base_url: str | None = None
) -> dict:
    """A linked card carries the attendee's entry payload; others carry none.

    The card never gets rights of its own: its QR is the attendee's pass, so a
    scan goes through the normal ticket path.
    """
    entry_qr = None
    if credential.registration_id:
        from app.models.registration import CollegeRegistration
        from app.services import tickets as ticket_service

        registration = await db.get(CollegeRegistration, credential.registration_id)
        if registration is not None:
            entry_qr = await ticket_service.registration_entry_payload(
                db, registration, base_url=base_url
            )
    return payload(credential, entry_qr=entry_qr)


def public_payload(credential: CustomCredential) -> dict:
    return {
        "valid": credential.status == "active",
        "kind": "custom_credential",
        "code": credential.code,
        "name": credential.name,
        "role": credential.role,
        "college": credential.college,
        "branch": credential.branch,
        "tier": credential.tier,
        "gender": decode_gender(credential.gender),
        "foodPreference": decode_food(credential.food_preference),
        "needsAccommodation": credential.needs_accommodation,
        "revoked": credential.status != "active",
    }


async def list_for_edition(
    db: AsyncSession, edition_id: uuid.UUID, *, include_revoked: bool = True
) -> list[CustomCredential]:
    stmt = (
        select(CustomCredential)
        .where(CustomCredential.edition_id == edition_id)
        .order_by(CustomCredential.created_at.desc())
    )
    if not include_revoked:
        stmt = stmt.where(CustomCredential.status == "active")
    return list((await db.execute(stmt)).scalars())


async def get_for_edition(
    db: AsyncSession, edition_id: uuid.UUID, credential_id: uuid.UUID
) -> CustomCredential:
    row = await db.get(CustomCredential, credential_id)
    if row is None or row.edition_id != edition_id:
        raise NotFound("That credential does not exist in this edition.")
    return row


async def _assert_not_a_registration(
    db: AsyncSession,
    edition_id: uuid.UUID,
    code: str,
    *,
    allowed_registration_id: uuid.UUID | None = None,
) -> None:
    """A custom card must never shadow a real participant's number.

    The desk resolves a bare number against registrations first, so two people
    typed as the same value would be indistinguishable. The one exception is a
    card that was built from that very registration: the number then points at
    the same person, which is exactly what the printed card claims.
    """
    from sqlalchemy import func

    from app.models.registration import CollegeRegistration

    clash = (
        await db.execute(
            select(CollegeRegistration.id).where(
                CollegeRegistration.edition_id == edition_id,
                func.upper(CollegeRegistration.registration_number) == code,
            )
        )
    ).scalar_one_or_none()
    if clash is None:
        return
    if allowed_registration_id is not None and clash == allowed_registration_id:
        return
    raise Conflict(
        f"{code} belongs to a participant registration. "
        "Load that attendee from \"Registered Attendees\" so the card links to their registration, "
        "or pick a different credential ID.",
        code="CREDENTIAL_CODE_TAKEN",
    )


async def _registration_in_edition(
    db: AsyncSession, edition_id: uuid.UUID, registration_id: uuid.UUID
):
    from app.models.registration import CollegeRegistration

    row = await db.get(CollegeRegistration, registration_id)
    if row is None or row.edition_id != edition_id:
        raise ValidationFailed("That registration does not exist in this edition.")
    return row


async def for_registration(
    db: AsyncSession,
    edition_id: uuid.UUID,
    registration_id: uuid.UUID,
    *,
    include_revoked: bool = False,
) -> CustomCredential | None:
    """The card already issued for a registration, if any."""
    stmt = select(CustomCredential).where(
        CustomCredential.edition_id == edition_id,
        CustomCredential.registration_id == registration_id,
    )
    if not include_revoked:
        stmt = stmt.where(CustomCredential.status == "active")
    return (await db.execute(stmt)).scalars().first()


async def _flush_claiming_code(db: AsyncSession, credential: CustomCredential) -> None:
    """Insert/flush, turning a duplicate printed ID into a clear conflict."""
    try:
        async with db.begin_nested():
            db.add(credential)
            await db.flush()
    except IntegrityError as exc:
        # The savepoint rollback already discards the pending instance.
        if credential in db:
            db.expunge(credential)
        raise Conflict(
            f"Credential ID {credential.code} is already used in this edition. "
            "Pick another ID or leave the field blank to generate one.",
            code="CREDENTIAL_CODE_TAKEN",
        ) from exc


def clean_design(value: object) -> dict:
    """Accept a small JSON object of presentation settings, reject the rest."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValidationFailed("Card design must be an object.")
    try:
        encoded = json.dumps(value, separators=(",", ":")).encode()
    except (TypeError, ValueError) as exc:
        raise ValidationFailed("Card design must be serialisable JSON.") from exc
    if len(encoded) > MAX_DESIGN_BYTES:
        raise ValidationFailed(
            f"Card design is too large ({len(encoded)} bytes, limit {MAX_DESIGN_BYTES})."
        )
    return value


async def create(
    db: AsyncSession,
    edition_id: uuid.UUID,
    data: dict,
    actor_id: uuid.UUID | None,
) -> CustomCredential:
    registration = None
    registration_id = data.get("registration_id")
    if registration_id:
        registration = await _registration_in_edition(db, edition_id, registration_id)
        # One card per attendee: saving the same attendee again must hand back
        # the card (and signed QR) that already exists, not fail on a duplicate.
        # If the previous card was revoked, reactivate it instead of colliding
        # on the unique (edition_id, registration_id) constraint.
        existing = await for_registration(
            db, edition_id, registration.id, include_revoked=True
        )
        if existing is not None:
            if existing.status != "active":
                existing.status = "active"
                existing.revoked_at = None
                existing.revoke_reason = None
            return await update(db, existing, data, actor_id)
    code = normalize_code(data.get("code"))
    if not code and registration is not None:
        # An attendee's printed card carries the number on their registration,
        # so the desk can match the badge to the record it came from.
        code = normalize_code(registration.registration_number)
    code = code or generate_code()
    if len(code) > MAX_CODE_LENGTH:
        raise ValidationFailed(f"Credential ID must be {MAX_CODE_LENGTH} characters or fewer.")
    await _assert_not_a_registration(
        db,
        edition_id,
        code,
        allowed_registration_id=registration.id if registration else None,
    )
    credential = CustomCredential(
        edition_id=edition_id,
        registration_id=registration.id if registration else None,
        code=code,
        name=_clean_text(data.get("name"), "Name", required=True, limit=120),
        role=_clean_text(data.get("role"), "Role", required=True, limit=120),
        college=_clean_text(data.get("college"), "College", required=False, limit=200),
        branch=_clean_text(data.get("branch"), "Branch", required=False, limit=160),
        tier=_clean_text(data.get("tier"), "Tier", required=False, limit=120),
        gender=encode_gender(data.get("gender")),
        food_preference=encode_food(data.get("food_preference")),
        needs_accommodation=bool(data.get("needs_accommodation")),
        design=clean_design(data.get("design")),
        status="active",
        issued_by=actor_id,
        updated_by=actor_id,
    )
    try:
        await _flush_claiming_code(db, credential)
    except Conflict:
        # A concurrent save of the same attendee won the insert; reopen it.
        if registration is not None:
            existing = await for_registration(db, edition_id, registration.id)
            if existing is not None:
                return existing
        raise
    return credential


async def update(
    db: AsyncSession,
    credential: CustomCredential,
    data: dict,
    actor_id: uuid.UUID | None,
) -> CustomCredential:
    if "registration_id" in data:
        next_registration_id = data.get("registration_id")
        if next_registration_id:
            await _registration_in_edition(
                db, credential.edition_id, next_registration_id
            )
        credential.registration_id = next_registration_id
    if "code" in data and data.get("code"):
        code = normalize_code(data["code"])
        if len(code) > MAX_CODE_LENGTH:
            raise ValidationFailed(f"Credential ID must be {MAX_CODE_LENGTH} characters or fewer.")
        await _assert_not_a_registration(
            db,
            credential.edition_id,
            code,
            allowed_registration_id=credential.registration_id,
        )
        credential.code = code
    if "name" in data:
        credential.name = _clean_text(data.get("name"), "Name", required=True, limit=120)
    if "role" in data:
        credential.role = _clean_text(data.get("role"), "Role", required=True, limit=120)
    if "college" in data:
        credential.college = _clean_text(data.get("college"), "College", required=False, limit=200)
    if "branch" in data:
        credential.branch = _clean_text(data.get("branch"), "Branch", required=False, limit=160)
    if "tier" in data:
        credential.tier = _clean_text(data.get("tier"), "Tier", required=False, limit=120)
    if "gender" in data:
        credential.gender = encode_gender(data.get("gender"))
    if "food_preference" in data:
        credential.food_preference = encode_food(data.get("food_preference"))
    if "needs_accommodation" in data:
        credential.needs_accommodation = bool(data.get("needs_accommodation"))
    if "design" in data:
        credential.design = clean_design(data.get("design"))
    credential.updated_by = actor_id
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError as exc:
        # The savepoint rolled the row back; drop the in-memory mutation too so
        # the next commit cannot retry it.
        if credential in db:
            db.expire(credential)
        raise Conflict(
            f"Credential ID {credential.code} is already used in this edition.",
            code="CREDENTIAL_CODE_TAKEN",
        ) from exc
    return credential


async def revoke(
    db: AsyncSession,
    credential: CustomCredential,
    actor_id: uuid.UUID | None,
    reason: str | None = None,
) -> CustomCredential:
    from datetime import UTC, datetime

    credential.status = "revoked"
    credential.revoked_at = datetime.now(UTC)
    credential.revoke_reason = (reason or "").strip() or None
    credential.updated_by = actor_id
    await db.flush()
    return credential


async def resolve(db: AsyncSession, raw: str, edition_id: uuid.UUID) -> CustomCredential:
    """Desk lookup: a scanned token, a scanned /c/ URL or a typed credential ID."""
    value = (raw or "").strip()
    if "/c/" in value:
        value = value.split("/c/")[-1].split("?")[0].strip()

    credential: CustomCredential | None = None
    token_id = parse_token(value)
    if token_id is not None:
        if not token_is_valid(value, token_id):
            raise NotFound("Invalid credential token.")
        credential = await db.get(CustomCredential, token_id)
        if credential is not None and credential.edition_id != edition_id:
            credential = None
    if credential is None:
        code = normalize_code(value)
        if code:
            credential = (
                await db.execute(
                    select(CustomCredential).where(
                        CustomCredential.edition_id == edition_id,
                        CustomCredential.code == code,
                    )
                )
            ).scalars().first()
    if credential is None:
        raise NotFound("Invalid credential token or registration code.")
    if credential.status != "active":
        raise Conflict(
            f"Credential {credential.code} has been revoked by the organisers. Entry denied.",
            code="CREDENTIAL_REVOKED",
        )
    return credential


async def resolve_public(db: AsyncSession, raw: str) -> CustomCredential | None:
    """Public verification: resolve a scanned token or code without an edition."""
    value = (raw or "").strip()
    if "/c/" in value:
        value = value.split("/c/")[-1].split("?")[0].strip()
    token_id = parse_token(value)
    if token_id is not None:
        if not token_is_valid(value, token_id):
            return None
        return await db.get(CustomCredential, token_id)
    code = normalize_code(value)
    if not code:
        return None
    # Codes are unique per edition, not globally, so a bare code that two editions
    # both issued cannot identify one person. Refusing beats showing the wrong one.
    rows = list(
        (
            await db.execute(
                select(CustomCredential)
                .where(CustomCredential.code == code)
                .order_by(CustomCredential.created_at.desc())
                .limit(2)
            )
        ).scalars()
    )
    if not rows:
        return None
    if len(rows) > 1 and rows[0].edition_id != rows[1].edition_id:
        return None
    return rows[0]


__all__ = [
    "CODE_PREFIX",
    "MAX_CODE_LENGTH",
    "TOKEN_PREFIX",
    "TOKEN_RE",
    "MAX_DESIGN_BYTES",
    "clean_design",
    "create",
    "for_registration",
    "generate_code",
    "get_for_edition",
    "list_for_edition",
    "looks_like_token",
    "normalize_code",
    "parse_token",
    "payload",
    "payload_with_entry",
    "public_payload",
    "qr_token",
    "resolve",
    "resolve_public",
    "revoke",
    "token_for",
    "token_is_valid",
    "update",
]
