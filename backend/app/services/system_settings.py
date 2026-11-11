from datetime import UTC, datetime
from typing import Any
import uuid
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_delete, cache_get, cache_set
from app.core.config import get_settings
from app.core.errors import AppError
from app.models.settings import SystemSetting

UNLOCK_KEY = "registration_unlock_at"
PRICE_KEYS = {
    "isteMemberPaise": "registration_price_iste_member_paise",
    "nonIstePaise": "registration_price_non_iste_paise",
    "polytechnicPaise": "registration_price_polytechnic_paise",
}


def initial_values() -> dict[str, Any]:
    settings = get_settings()
    unlock = settings.registration_unlock_at
    if unlock.tzinfo is None:
        unlock = unlock.replace(tzinfo=UTC)
    return {
        UNLOCK_KEY: unlock.astimezone(UTC).isoformat(),
        **{key: getattr(settings, field) for key, field in PRICE_KEYS.items()},
    }


async def seed_system_settings(db: AsyncSession) -> None:
    """Insert initial env values once; later admin changes remain authoritative."""
    values = initial_values()
    rows = list((await db.execute(select(SystemSetting))).scalars())
    existing = {row.key for row in rows}
    for key, value in values.items():
        if key not in existing:
            db.add(SystemSetting(key=key, value=value))
    await db.flush()
    cache_delete(_SETTINGS_CACHE_KEY)


_SETTINGS_CACHE_KEY = "system:settings"
_SETTINGS_CACHE_TTL = 5.0


async def all_settings(db: AsyncSession) -> dict[str, Any]:
    """Read the authoritative settings once per short window.

    Public endpoints ask for the unlock instant and rates several times in a
    single request; without this each ask was a fresh SELECT. Admin writes
    invalidate the entry, so an edit is visible immediately.
    """
    cached = cache_get(_SETTINGS_CACHE_KEY)
    if isinstance(cached, dict):
        return dict(cached)
    values = initial_values()
    rows = list((await db.execute(select(SystemSetting))).scalars())
    values.update({row.key: row.value for row in rows})
    cache_set(_SETTINGS_CACHE_KEY, values, ttl_seconds=_SETTINGS_CACHE_TTL)
    return values


async def unlock_at(db: AsyncSession) -> datetime:
    value = (await all_settings(db)).get(UNLOCK_KEY)
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


async def registration_is_open(db: AsyncSession, now: datetime | None = None) -> bool:
    current = now or datetime.now(UTC)
    return current.astimezone(UTC) >= await unlock_at(db)


async def require_registration_open(db: AsyncSession) -> None:
    opens_at = await unlock_at(db)
    if datetime.now(UTC) < opens_at:
        local = opens_at.astimezone(ZoneInfo("Asia/Kolkata"))
        raise AppError(
            f"Registrations open on {local.strftime('%d %b %Y, %I:%M %p')} IST.",
            code="REGISTRATION_LOCKED",
            status_code=423,
            details={"opensAt": opens_at.isoformat()},
        )


async def update_settings(
    db: AsyncSession, values: dict[str, Any], actor_id: uuid.UUID
) -> dict[str, Any]:
    for key, value in values.items():
        row = await db.scalar(select(SystemSetting).where(SystemSetting.key == key))
        if row is None:
            row = SystemSetting(key=key, value=value, updated_by=actor_id)
            db.add(row)
        else:
            row.value = value
            row.updated_by = actor_id
    await db.flush()
    cache_delete(_SETTINGS_CACHE_KEY)
    return await all_settings(db)


async def price_for(db: AsyncSession, *, is_iste_member: bool, education_level: str) -> int:
    settings = await all_settings(db)
    # Polytechnic has explicit price precedence, including ISTE members.
    if education_level.casefold() == "polytechnic":
        return int(settings["polytechnicPaise"])
    key = "isteMemberPaise" if is_iste_member else "nonIstePaise"
    return int(settings[key])
