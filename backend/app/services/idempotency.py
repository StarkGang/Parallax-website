"""Idempotency keys for money-moving POSTs: replay the stored response, reject body drift."""

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationFailed
from app.models.commerce import IdempotencyKey


def body_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()


async def replay(
    db: AsyncSession,
    user_id: uuid.UUID,
    route: str,
    key: str | None,
    payload: dict[str, Any],
) -> tuple[int, dict[str, Any]] | None:
    if not key:
        return None
    digest = body_hash(payload)
    existing = await db.scalar(
        select(IdempotencyKey).where(
            IdempotencyKey.key == key,
            IdempotencyKey.user_id == user_id,
            IdempotencyKey.route == route,
        )
    )
    if existing is None:
        return None
    if existing.request_hash != digest:
        raise ValidationFailed(
            "Idempotency key payload does not match previous request."
        )
    return existing.status_code, existing.response_snapshot


async def store(
    db: AsyncSession,
    user_id: uuid.UUID,
    route: str,
    key: str | None,
    payload: dict[str, Any],
    response: dict[str, Any],
    status_code: int = 200,
) -> None:
    if not key:
        return
    db.add(
        IdempotencyKey(
            key=key,
            user_id=user_id,
            route=route,
            request_hash=body_hash(payload),
            response_snapshot=response,
            status_code=status_code,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
    )


async def cleanup(db: AsyncSession) -> None:
    from sqlalchemy import delete

    await db.execute(
        delete(IdempotencyKey).where(IdempotencyKey.expires_at < datetime.now(UTC))
    )


__all__ = ["body_hash", "replay", "store", "cleanup"]

