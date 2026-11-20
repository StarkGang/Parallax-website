import pytest
from httpx import AsyncClient
from app.services.telegram import send_telegram_inquiry


@pytest.mark.asyncio
async def test_telegram_skipped_when_not_configured(monkeypatch):
    monkeypatch.setattr("app.services.telegram.get_settings", lambda: type("Settings", (), {
        "effective_telegram_bot_token": None,
        "effective_telegram_chat_id": None,
    })())
    res = await send_telegram_inquiry(
        name="Test Student",
        email="student@test.local",
        category="general",
        message="Hello Parallax team!",
    )
    assert res["sent"] is False
    assert res["reason"] == "not_configured"


@pytest.mark.asyncio
async def test_public_inquiry_endpoint(client: AsyncClient):
    response = await client.post(
        "/api/v1/public/inquiries",
        json={
            "name": "Jane Doe",
            "email": "jane@example.com",
            "category": "pass",
            "message": "Is food included for both days of the pass?",
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["sent"] is True
    assert "received" in data["message"].lower()

