"""Shared fixture helper for team tests.

Team *creation* requires the caller to already hold a live seat on the event
(``REGISTRATION_REQUIRED`` in ``app/services/teams.py``): a team is a roster over
seats, not a second way to buy one. Tests therefore buy the seat first, through
the same basket -> checkout -> pay path a participant uses.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def buy_seat(client: AsyncClient, edition_id, event_id) -> dict:
    """Hold one seat for ``event_id`` and return the basket payload."""
    edition = str(edition_id)
    event = str(event_id)
    basket = await client.post(
        f"/api/v1/editions/{edition}/basket/events", json={"eventIds": [event]}
    )
    assert basket.status_code == 200, basket.text
    payload = basket.json().get("data") or {}
    quote_id = payload.get("quoteId")
    if not quote_id:
        return payload
    checkout = await client.post(
        f"/api/v1/editions/{edition}/checkout", json={"quoteId": quote_id}
    )
    assert checkout.status_code in (200, 201), checkout.text
    order = (checkout.json().get("data") or {}).get("order")
    if order:
        paid = await client.post(
            f"/api/v1/editions/{edition}/payments/{order['orderId']}/mock"
        )
        assert paid.status_code == 200, paid.text
    return payload


async def buy_seat_reserved(client: AsyncClient, edition_id, event_id) -> tuple[str, dict]:
    """Put one seat in the basket and check out *without* paying.

    Returns ``(order_id, basket_payload)`` so a caller can inspect the reserved
    state before settling it.
    """
    edition = str(edition_id)
    basket = await client.post(
        f"/api/v1/editions/{edition}/basket/events", json={"eventIds": [str(event_id)]}
    )
    assert basket.status_code == 200, basket.text
    payload = basket.json()["data"]
    checkout = await client.post(
        f"/api/v1/editions/{edition}/checkout", json={"quoteId": payload["quoteId"]}
    )
    assert checkout.status_code in (200, 201), checkout.text
    order = (checkout.json().get("data") or {}).get("order") or {}
    return str(order.get("orderId") or ""), payload


def as_uuid(value) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
