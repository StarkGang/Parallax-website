"""Regressions for the transient-database failures seen on Vercel/Supabase.

A cold pooler used to turn a read-only portal page into an ASGI 500 because
authenticating the session also performed an UPDATE. These tests pin the two
guarantees that replaced it: the slide cannot break a request, and a statement
timeout answers 503 with Retry-After instead of crashing.
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.user import Session


async def test_statement_timeout_maps_to_503(client, monkeypatch):
    from app.api import deps

    async def boom(*args, **kwargs):
        raise TimeoutError("canceling statement due to statement timeout")

    monkeypatch.setattr(deps, "resolve_session", boom)

    response = await client.get("/api/v1/me")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert response.headers["retry-after"] == "2"


async def test_failed_idle_slide_does_not_break_the_request(
    participant_client, db_session, monkeypatch
):
    row = (
        await db_session.execute(
            select(Session).where(Session.revoked_at.is_(None)).limit(1)
        )
    ).scalar_one_or_none()
    assert row is not None, "the login fixture should have created a session"

    # Make the session stale so resolve_session attempts the idle slide.
    row.last_seen_at = datetime.now(UTC) - timedelta(hours=2)
    await db_session.commit()

    @asynccontextmanager
    async def failing_scope():
        raise TimeoutError("canceling statement due to statement timeout")
        yield  # pragma: no cover - unreachable, keeps this a context manager

    # _slide_idle imports session_scope at call time, so this is the exact seam.
    monkeypatch.setattr("app.db.session.session_scope", failing_scope)

    response = await participant_client.get("/api/v1/me")

    assert response.status_code == 200, response.text
    assert response.json()["data"]["email"]


async def test_fresh_session_performs_no_second_connection(participant_client, monkeypatch):
    """A just-used session must not open an extra transaction to slide itself."""
    calls = {"count": 0}

    @asynccontextmanager
    async def counting_scope():
        calls["count"] += 1
        yield None

    monkeypatch.setattr("app.db.session.session_scope", counting_scope)

    response = await participant_client.get("/api/v1/me")

    assert response.status_code == 200
    assert calls["count"] == 0
