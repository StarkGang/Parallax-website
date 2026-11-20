"""Tests for Razorpay Standard Checkout endpoints."""

import hashlib
import hmac
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

from app.core.config import get_settings


@pytest.mark.asyncio
async def test_create_order_validates_minimum_amount(client: AsyncClient):
    # Amount < 100 paise
    res = await client.post("/api/create-order", json={"amount": 50, "currency": "INR"})
    assert res.status_code == 400
    data = res.json()
    msg = data.get("detail") or data.get("error", {}).get("message", "")
    assert "at least 100 paise" in msg


@pytest.mark.asyncio
async def test_create_order_success(client: AsyncClient):
    with patch("razorpay.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.order.create.return_value = {
            "id": "order_test_12345",
            "amount": 50000,
            "currency": "INR",
            "status": "created",
        }
        mock_client_cls.return_value = mock_client

        res = await client.post(
            "/api/create-order",
            json={"amount": 50000, "currency": "INR", "receipt": "test_rcpt_01"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["order_id"] == "order_test_12345"
        assert data["amount"] == 50000
        assert data["currency"] == "INR"


@pytest.mark.asyncio
async def test_verify_payment_missing_fields(client: AsyncClient):
    # Missing razorpay_signature
    res = await client.post(
        "/api/verify-payment",
        json={"razorpay_order_id": "order_123", "razorpay_payment_id": "pay_123"},
    )
    assert res.status_code == 400
    data = res.json()
    msg = data.get("detail") or data.get("error", {}).get("message", "")
    assert "Missing required fields" in msg


@pytest.mark.asyncio
async def test_verify_payment_signature_mismatch(client: AsyncClient):
    res = await client.post(
        "/api/verify-payment",
        json={
            "razorpay_order_id": "order_123",
            "razorpay_payment_id": "pay_123",
            "razorpay_signature": "invalid_signature_hex",
        },
    )
    assert res.status_code == 400
    data = res.json()
    msg = data.get("detail") or data.get("error", {}).get("message", "")
    assert "signature verification failed" in msg


@pytest.mark.asyncio
async def test_verify_payment_success(client: AsyncClient):
    settings = get_settings()
    key_secret = settings.razorpay_key_secret or "08U2DCXQgcTBjb6pQOHCjaDj"
    order_id = "order_test_abc"
    payment_id = "pay_test_xyz"
    valid_sig = hmac.new(
        key_secret.encode("utf-8"),
        f"{order_id}|{payment_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    res = await client.post(
        "/api/verify-payment",
        json={
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": valid_sig,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["order_id"] == order_id
    assert data["payment_id"] == payment_id
