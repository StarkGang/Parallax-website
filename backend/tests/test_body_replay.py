"""BUG-005: a replayed chunked body answers every extra read with an empty body."""

import pytest
from starlette.requests import Request

from app.main import BodyLimitMiddleware


@pytest.mark.asyncio
async def test_replayed_body_returns_empty_requests_not_disconnect():
    received: list[dict] = []

    async def inner(scope, receive, send):
        for _ in range(3):
            received.append(await receive())

    middleware = BodyLimitMiddleware(inner)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/test",
        "headers": [],
        "query_string": b"",
    }

    chunks = [
        {"type": "http.request", "body": b"hello ", "more_body": True},
        {"type": "http.request", "body": b"world", "more_body": False},
    ]

    async def receive():
        return chunks.pop(0)

    async def send(message):
        return None

    await middleware(scope, receive, send)

    assert received[0] == {
        "type": "http.request",
        "body": b"hello world",
        "more_body": False,
    }
    assert received[1]["type"] == "http.request"
    assert received[1]["body"] == b""
    assert received[1]["more_body"] is False
    assert received[2]["type"] != "http.disconnect"
