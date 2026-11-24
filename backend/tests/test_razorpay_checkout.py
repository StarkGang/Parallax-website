"""The unauthenticated Standard Checkout demo endpoints were removed (PAY-001).

Real payments go through POST /editions/{edition_id}/payments/verify and the
signed Razorpay webhook, both of which price the order server-side.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["/api", "/api/v1"])
async def test_removed_standard_checkout_routes_are_gone(client: AsyncClient, prefix: str):
    create = await client.post(f"{prefix}/create-order", json={"amount": 50000})
    verify = await client.post(f"{prefix}/verify-payment", json={})
    assert create.status_code == 404
    assert verify.status_code == 404
