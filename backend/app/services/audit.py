"""Audit rows are written in the same transaction as the privileged write."""

import uuid
from typing import Any
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import request_id_ctx
from app.models.commerce import AuditLog

SENSITIVE_KEYS = {
    "phone",
    "email",
    "studentIdentifier",
    "full_name",
    "student_identifier",
    "fullName",
}


def redact(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    return {
        k: ("[REDACTED]" if k in SENSITIVE_KEYS else v)
        for k, v in payload.items()
    }


async def record(
    db: AsyncSession,
    request: Request | None,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
    action: str = "",
    resource_type: str = "",
    resource_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    from app.core.sessions import ip_prefix

    client_host = request.client.host if (request and request.client) else None
    client_ip = ip_prefix(client_host) if client_host else None
    ua = request.headers.get("user-agent", "")[:255] if request else None

    entry = AuditLog(
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
        before=redact(before),
        after=redact(after),
        ip_prefix=client_ip,
        user_agent=ua,
        request_id=request_id_ctx.get(),
    )
    db.add(entry)


__all__ = ["SENSITIVE_KEYS", "redact", "record"]

