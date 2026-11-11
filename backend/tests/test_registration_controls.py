from datetime import UTC, datetime

import pytest

from app.services.system_settings import price_for, registration_is_open


@pytest.mark.asyncio
async def test_registration_unlock_uses_single_utc_instant(db_session):
    # The stored row is authoritative; patching env settings must not be what
    # decides whether registration is open.
    from support import lock_registration

    unlock = datetime.fromisoformat("2026-11-15T00:00:00+05:30")
    await lock_registration(db_session, unlock)

    before = datetime(2026, 11, 14, 18, 29, 59, tzinfo=UTC)
    at = datetime(2026, 11, 14, 18, 30, 0, tzinfo=UTC)
    assert await registration_is_open(db_session, before) is False
    assert await registration_is_open(db_session, at) is True


@pytest.mark.asyncio
async def test_polytechnic_price_takes_precedence_over_iste(db_session):
    assert await price_for(
        db_session, is_iste_member=True, education_level="Polytechnic"
    ) == 29900
    assert await price_for(
        db_session, is_iste_member=True, education_level="B.Tech"
    ) == 49900
    assert await price_for(
        db_session, is_iste_member=False, education_level="B.Tech"
    ) == 59900
